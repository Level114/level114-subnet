"""
Level114 Subnet - Validator Runner

Integration module for the Level114 subnet validator that combines
collector reports, scoring system, and Bittensor weight updates.
"""

import asyncio
import time
import traceback
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List
from collections import deque
import bittensor as bt
import numpy as np

from .scoring import (
    ServerReport, MinerContext, calculate_miner_score,
    apply_score_smoothing,
    DEBUG_SCORING,
    MAX_REPORT_HISTORY,
)
from ..api.collector_center_api import CollectorCenterAPI
from ..base.utils.weight_utils import process_weights_for_netuid


@dataclass
class ScoreCacheEntry:
    """In-memory score cache entry."""

    score: int
    raw_score: int
    components: Dict[str, float]
    updated_at: float


class Level114ValidatorRunner:
    """
    Main validator runner that integrates scoring with Bittensor
    """
    
    def __init__(
        self,
        config,
        subtensor,
        metagraph,
        wallet,
        collector_api: CollectorCenterAPI,
    ):
        """
        Initialize validator runner
        
        Args:
            config: Bittensor configuration
            subtensor: Subtensor connection
            metagraph: Network metagraph
            wallet: Validator wallet
            collector_api: Collector Center API client
        """
        self.config = config
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.wallet = wallet
        self.collector_api = collector_api

        # Scoring state
        self.replay_protection = None
        self.last_weights_update = 0
        self.score_cache: Dict[str, ScoreCacheEntry] = {}
        self.hotkey_to_server_id: Dict[str, str] = {}
        self.server_id_to_hotkey: Dict[str, str] = {}
        self.server_ids_last_fetch: float = 0.0
        # Rate limit: /servers/ids endpoint allows 5 req/min (~12s interval)
        self.server_ids_min_refresh_interval: float = 12.5
        self.report_fetch_limit: int = 25
        self.last_weight_update_attempt = 0
        self.next_weight_update_time = 0
        self._last_committed_weights = None
        self._last_committed_uids = None
        validator_cfg = getattr(self.config, 'validator', None)

        def _coerce_interval(value, fallback):
            try:
                if value is None:
                    raise ValueError
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise ValueError
                return max(numeric, 0.0)
            except (TypeError, ValueError):
                return float(fallback)

        default_retry = _coerce_interval(
            getattr(validator_cfg, 'weight_retry_interval', None) if validator_cfg else None,
            60
        )
        default_update = _coerce_interval(
            getattr(validator_cfg, 'weight_update_interval', None) if validator_cfg else None,
            300
        )

        self.weight_retry_interval = max(default_retry, 10.0)
        self.weight_update_interval = max(default_update, 10.0)
        
        # Performance tracking
        self.cycle_count = 0
        self.last_cleanup = time.time()
        
        bt.logging.info("Level114 Validator Runner initialized")
    
    async def run_scoring_cycle(self) -> Dict[str, any]:
        """
        Run one complete scoring cycle
        
        Returns:
            Dictionary with cycle results and statistics
        """
        cycle_start = time.time()
        stats = {
            'cycle_id': self.cycle_count,
            'timestamp': cycle_start,
            'servers_processed': 0,
            'scores_updated': 0,
            'errors': 0,
            'total_time': 0.0,
            'weights_updated': False
        }
        
        try:
            bt.logging.info(f"🔄 Starting scoring cycle {self.cycle_count}")
            
            # 1. Get all active servers from metagraph
            active_hotkeys = [axon.hotkey for axon in self.metagraph.axons]
            
            # 2. Map hotkeys to server IDs
            server_mappings = await self._get_server_mappings(active_hotkeys)
            stats['servers_found'] = len(server_mappings)
            
            if not server_mappings:
                bt.logging.warning("No server mappings found for active hotkeys")
                return stats
            
            # 3. Score each server
            scoring_results = {}
            for hotkey, server_id in server_mappings.items():
                try:
                    result = await self._score_server(server_id)
                    if result:
                        scoring_results[hotkey] = result
                        stats['scores_updated'] += 1
                    
                    stats['servers_processed'] += 1
                    
                except Exception as e:
                    bt.logging.error(f"Error scoring server {server_id}: {e}")
                    if DEBUG_SCORING:
                        bt.logging.debug(traceback.format_exc())
                    stats['errors'] += 1
            
            # 4. Update weights if needed
            if self._should_update_weights():
                try:
                    await self._update_weights(scoring_results)
                    stats['weights_updated'] = True
                except Exception as e:
                    bt.logging.error(f"Error updating weights: {e}")
                    stats['errors'] += 1
            
            # 5. Cleanup old data periodically
            if time.time() - self.last_cleanup > 3600:  # Every hour
                self._cleanup_old_data()
                self.last_cleanup = time.time()
            
        except Exception as e:
            bt.logging.error(f"Critical error in scoring cycle: {e}")
            if DEBUG_SCORING:
                bt.logging.debug(traceback.format_exc())
            stats['errors'] += 1
        
        finally:
            stats['total_time'] = time.time() - cycle_start
            self.cycle_count += 1
            
            bt.logging.info(
                f"✅ Cycle {stats['cycle_id']} complete: "
                f"{stats['servers_processed']} servers, "
                f"{stats['scores_updated']} scores updated, "
                f"{stats['errors']} errors, "
                f"{stats['total_time']:.1f}s"
            )
        
        return stats
    
    async def _get_server_mappings(self, hotkeys: List[str]) -> Dict[str, str]:
        """
        Get mapping of hotkeys to server IDs

        Args:
            hotkeys: List of hotkeys to look up

        Returns:
            Dictionary mapping hotkey -> server_id
        """
        mappings: Dict[str, str] = {}

        if not hotkeys:
            return mappings

        now = time.time()
        should_refresh = (
            not self.hotkey_to_server_id
            or (now - self.server_ids_last_fetch) >= self.server_ids_min_refresh_interval
        )

        # Use cached entries while deciding whether to refresh
        for hotkey in hotkeys:
            server_id = self.hotkey_to_server_id.get(hotkey)
            if server_id:
                mappings[hotkey] = server_id

        missing_hotkeys = [hk for hk in hotkeys if hk not in mappings]
        if missing_hotkeys:
            # Force refresh if we are missing entries for requested hotkeys
            should_refresh = True

        if not should_refresh:
            return mappings

        try:
            status, server_list = self.collector_api.get_validator_server_ids(hotkeys)

            if 200 <= status < 300 and server_list:
                response_hotkeys = set()
                for server_info in server_list:
                    hotkey = server_info.hotkey
                    server_id = server_info.id
                    if not hotkey or not server_id:
                        continue

                    mappings[hotkey] = server_id
                    self.hotkey_to_server_id[hotkey] = server_id
                    self.server_id_to_hotkey[server_id] = hotkey
                    response_hotkeys.add(hotkey)

                active_hotkeys = set(hotkeys)
                stale_hotkeys = [
                    hk for hk in active_hotkeys
                    if hk not in response_hotkeys and hk in self.hotkey_to_server_id
                ]

                for hotkey in stale_hotkeys:
                    server_id = self.hotkey_to_server_id.pop(hotkey, None)
                    if server_id:
                        self.server_id_to_hotkey.pop(server_id, None)
                        self.score_cache.pop(server_id, None)

                self.server_ids_last_fetch = now
                bt.logging.info(f"Found {len(mappings)} server mappings from collector")

            else:
                bt.logging.error(
                    f"Collector server ID lookup failed with status {status}; using cached mappings"
                )
                # Fall back to cached data if available
                mappings = {
                    hotkey: self.hotkey_to_server_id[hotkey]
                    for hotkey in hotkeys
                    if hotkey in self.hotkey_to_server_id
                }

        except Exception as e:
            bt.logging.error(f"Error getting server mappings: {e}")
            mappings = {
                hotkey: self.hotkey_to_server_id[hotkey]
                for hotkey in hotkeys
                if hotkey in self.hotkey_to_server_id
            }

        return mappings
    
    async def _score_server(self, server_id: str) -> Optional[Dict[str, any]]:
        """
        Score a single server

        Args:
            server_id: Server to score

        Returns:
            Scoring result dictionary or None
        """
        if not server_id:
            return None

        try:
            status, reports = self.collector_api.get_server_reports(
                server_id,
                limit=self.report_fetch_limit,
            )

            if status != 200:
                bt.logging.debug(
                    f"Collector returned status {status} for server {server_id}; reports={len(reports)}"
                )

            if not reports:
                previous_entry = self.score_cache.get(server_id)
                if previous_entry and previous_entry.score > 0:
                    bt.logging.warning(
                        f"Collector returned no reports for server {server_id}; downgrading score to 0"
                    )
                    zero_components = {
                        'infrastructure': 0.0,
                        'participation': 0.0,
                        'reliability': 0.0,
                    }
                    zero_entry = ScoreCacheEntry(
                        score=0,
                        raw_score=0,
                        components=zero_components,
                        updated_at=time.time(),
                    )
                    self.score_cache[server_id] = zero_entry

                    return {
                        'server_id': server_id,
                        'score': 0,
                        'raw_score': 0,
                        'components': zero_components,
                        'latency': 0.0,
                        'compliance': False,
                        'reports_count': 0,
                    }

                bt.logging.debug(f"No reports available for server {server_id}")
                return None

            parsed_reports: List[ServerReport] = []
            for report_dict in reports:
                try:
                    parsed_reports.append(ServerReport.from_dict(report_dict))
                except Exception as parse_err:
                    bt.logging.debug(f"Failed to parse report for server {server_id}: {parse_err}")

            if not parsed_reports:
                bt.logging.debug(f"No valid reports parsed for server {server_id}")
                return None

            latest_report = parsed_reports[0]
            history = deque(reversed(parsed_reports), maxlen=MAX_REPORT_HISTORY)

            context = MinerContext(
                report=latest_report,
                http_latency_s=0.0,
                history=history,
            )

            new_score, components = calculate_miner_score(context)

            previous_entry = self.score_cache.get(server_id)
            previous_score = previous_entry.score if previous_entry else None
            smoothed_score = apply_score_smoothing(new_score, previous_score)

            self.score_cache[server_id] = ScoreCacheEntry(
                score=smoothed_score,
                raw_score=new_score,
                components=components,
                updated_at=time.time(),
            )

            if DEBUG_SCORING:
                bt.logging.debug(
                    f"Scored server {server_id}: {smoothed_score} (raw: {new_score}) using {len(history)} reports"
                )

            return {
                'server_id': server_id,
                'score': smoothed_score,
                'raw_score': new_score,
                'components': components,
                'latency': 0.0,
                'compliance': True,
                'reports_count': len(history),
            }

        except Exception as e:
            bt.logging.error(f"Error scoring server {server_id}: {e}")
            if DEBUG_SCORING:
                bt.logging.debug(traceback.format_exc())
            return None
    
    def _should_update_weights(self) -> bool:
        """Check if weights should be updated"""
        now = time.time()
        if now < self.next_weight_update_time:
            return False
        if self.last_weights_update:
            if now - self.last_weights_update < self.weight_update_interval:
                return False
        return True

    async def _update_weights(self, scoring_results: Dict[str, Dict]) -> None:
        """
        Update Bittensor weights based on scores
        
        Args:
            scoring_results: Dictionary mapping hotkey -> scoring result
        """
        try:
            bt.logging.info("🏋️ Updating blockchain weights...")
            self.last_weight_update_attempt = time.time()
            
            # 1. Prepare weights for all UIDs
            all_uids = list(range(self.metagraph.n.item()))
            raw_weights = np.zeros(len(all_uids))
            
            # 2. Map hotkeys to UIDs and assign weights
            hotkey_to_uid = {axon.hotkey: uid for uid, axon in enumerate(self.metagraph.axons)}
            
            total_weight = 0
            weights_assigned = 0
            
            for hotkey, result in scoring_results.items():
                if hotkey in hotkey_to_uid:
                    uid = hotkey_to_uid[hotkey]
                    score = result['score']
                    
                    # Convert score (0-1000) to weight (0-1)
                    weight = score / 1000.0
                    raw_weights[uid] = weight
                    # Track total only for logging; do not normalize by it
                    total_weight += weight
                    weights_assigned += 1
            
            # 3. Preserve raw magnitudes (no sum-normalization)
            # Ensure weights are within [0,1] bounds
            raw_weights = np.clip(raw_weights, 0.0, 1.0)
            
            # 4. Process weights according to subnet limitations
            processed_uids, processed_weights = process_weights_for_netuid(
                uids=np.array(all_uids),
                weights=raw_weights,  # Keep as numpy array
                netuid=self.config.netuid,
                subtensor=self.subtensor,
                metagraph=self.metagraph
            )
            
            # 5. Set weights on blockchain
            if len(processed_weights) > 0 and np.sum(processed_weights) > 0:
                # Skip commit if nothing changed since last successful update
                if (
                    self._last_committed_uids is not None
                    and np.array_equal(processed_uids, self._last_committed_uids)
                    and np.allclose(processed_weights, self._last_committed_weights)
                ):
                    bt.logging.debug("Weights unchanged since last commit, skipping update")
                    self.next_weight_update_time = self.last_weights_update + self.weight_update_interval if self.last_weights_update else time.time() + self.weight_update_interval
                    return

                result = self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=self.config.netuid,
                    uids=processed_uids,
                    weights=processed_weights,
                    wait_for_inclusion=True,
                    wait_for_finalization=True
                )
                
                if result:
                    self.last_weights_update = time.time()
                    self.next_weight_update_time = self.last_weights_update + self.weight_update_interval
                    self._last_committed_uids = np.copy(processed_uids)
                    self._last_committed_weights = np.copy(processed_weights)
                    bt.logging.info(
                        f"✅ Weights updated for {weights_assigned} miners "
                        f"(total weight: {sum(processed_weights):.3f})"
                    )
                else:
                    bt.logging.error("❌ Failed to set weights on blockchain")
                    self.next_weight_update_time = max(
                        self.last_weight_update_attempt + self.weight_retry_interval,
                        time.time() + self.weight_retry_interval
                    )
            else:
                bt.logging.warning("No weights to set")
                self.next_weight_update_time = max(
                    self.last_weight_update_attempt + self.weight_retry_interval,
                    time.time() + self.weight_retry_interval
                )
                
        except Exception as e:
            bt.logging.error(f"Error updating weights: {e}")
            self.next_weight_update_time = max(
                self.last_weight_update_attempt + self.weight_retry_interval,
                time.time() + self.weight_retry_interval
            )
            raise

    def _cleanup_old_data(self):
        """Clean up cached data to prevent memory growth"""
        try:
            bt.logging.info("🧹 Cleaning up old data...")
            
            # Clean up replay protection
            if self.replay_protection:
                self.replay_protection.cleanup_old_entries(max_age_hours=168)
            
            # Clear old score cache
            current_time = time.time()
            old_keys = [
                server_id
                for server_id, entry in self.score_cache.items()
                if current_time - entry.updated_at > 3600  # 1 hour
            ]
            for key in old_keys:
                self.score_cache.pop(key, None)
            
            bt.logging.info("✅ Cleanup complete")
            
        except Exception as e:
            bt.logging.error(f"Error during cleanup: {e}")
    
    def get_status(self) -> Dict[str, any]:
        """Get current validator status"""
        return {
            'cycle_count': self.cycle_count,
            'last_weights_update': self.last_weights_update,
            'next_weight_update': self.next_weight_update_time,
            'last_weight_attempt': self.last_weight_update_attempt,
            'cached_scores': len(self.score_cache),
            'cached_mappings': len(self.hotkey_to_server_id),
            'replay_protection_active': bool(self.replay_protection),
            'config': {
                'netuid': self.config.netuid,
                'weight_update_interval': self.weight_update_interval,
                'weight_retry_interval': self.weight_retry_interval
            }
        }

    def get_server_id_for_hotkey(self, hotkey: str) -> Optional[str]:
        """Helper to retrieve cached server ID for a given hotkey."""
        return self.hotkey_to_server_id.get(hotkey)

    def get_cached_score(self, server_id: str) -> Optional[ScoreCacheEntry]:
        """Helper to retrieve cached score entry for a server."""
        return self.score_cache.get(server_id)


# Integration with existing validator base class
async def integrate_scoring_system(validator_instance):
    """
    Integration function to add scoring to existing validator
    
    Args:
        validator_instance: Your existing validator instance
    """
    try:
        # Initialize collector API
        collector_config = getattr(validator_instance.config, 'collector', None)
        if not collector_config:
            bt.logging.error("No collector configuration found")
            return
        
        collector_api = CollectorCenterAPI(
            base_url=collector_config.url,
            api_key=collector_config.api_key,
            timeout_seconds=getattr(collector_config, 'timeout', 30.0)
        )

        # Create runner
        runner = Level114ValidatorRunner(
            config=validator_instance.config,
            subtensor=validator_instance.subtensor,
            metagraph=validator_instance.metagraph,
            wallet=validator_instance.wallet,
            collector_api=collector_api,
        )
        
        # Add to validator instance
        validator_instance.scoring_runner = runner
        
        bt.logging.info("✅ Scoring system integrated successfully")
        
        return runner
        
    except Exception as e:
        bt.logging.error(f"Failed to integrate scoring system: {e}")
        raise


# Example usage in validator main loop
async def enhanced_validator_loop(validator_instance):
    """
    Example enhanced validator loop with integrated scoring
    
    Args:
        validator_instance: Your validator instance
    """
    try:
        # Initialize scoring system
        runner = await integrate_scoring_system(validator_instance)
        
        while True:
            try:
                # Run scoring cycle
                cycle_stats = await runner.run_scoring_cycle()
                
                # Log cycle results
                bt.logging.info(
                    f"Cycle complete: {cycle_stats['servers_processed']} servers, "
                    f"{cycle_stats['scores_updated']} scores, "
                    f"{cycle_stats['total_time']:.1f}s"
                )
                
                # Wait before next cycle (default 60 seconds)
                cycle_interval = getattr(validator_instance.config, 'cycle_interval', 60)
                await asyncio.sleep(cycle_interval)
                
            except KeyboardInterrupt:
                bt.logging.info("Validator stopped by user")
                break
            except Exception as e:
                bt.logging.error(f"Error in validator loop: {e}")
                await asyncio.sleep(10)  # Brief pause before retry
        
    except Exception as e:
        bt.logging.error(f"Fatal error in validator: {e}")
        raise
