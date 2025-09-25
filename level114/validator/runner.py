"""
Level114 Subnet - Validator Runner

Integration module for the Level114 subnet validator that combines
collector reports, scoring system, and Bittensor weight updates.
"""

import asyncio
import time
import traceback
import math
from typing import List, Dict, Optional, Tuple
from collections import deque
import bittensor as bt
import numpy as np

from .scoring import (
    ServerReport, MinerContext, calculate_miner_score,
    apply_score_smoothing,
    DEBUG_SCORING
)
from .storage import ValidatorStorage, get_storage
from ..api.collector_center_api import CollectorCenterAPI
from ..base.utils.weight_utils import process_weights_for_netuid


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
        storage: Optional[ValidatorStorage] = None
    ):
        """
        Initialize validator runner
        
        Args:
            config: Bittensor configuration
            subtensor: Subtensor connection
            metagraph: Network metagraph
            wallet: Validator wallet
            collector_api: Collector Center API client
            storage: Storage instance (optional, will create default)
        """
        self.config = config
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.wallet = wallet
        self.collector_api = collector_api
        self.storage = storage or get_storage()
        
        # Scoring state
        self.replay_protection = None
        self.last_weights_update = 0
        self.score_cache = {}  # server_id -> (score, timestamp)
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
        mappings = {}
        
        try:
            # Try collector API first
            status, server_list = self.collector_api.get_validator_server_ids(hotkeys)
            
            collector_hotkeys = set()

            if status == 200 and server_list:
                for server_info in server_list:
                    hotkey = server_info.hotkey
                    server_id = server_info.id
                    mappings[hotkey] = server_id
                    collector_hotkeys.add(hotkey)
                    
                    # Update local registry
                    self.storage.register_server(
                        server_id, 
                        hotkey,
                        int(time.time() * 1000)
                    )
            
            if status == 200:
                # Mark hotkeys missing from collector as inactive locally
                for hotkey in hotkeys:
                    if hotkey in collector_hotkeys:
                        continue

                    server_id = self.storage.get_hotkey_server(hotkey)
                    if server_id:
                        bt.logging.debug(
                            f"Collector missing server mapping for hotkey {hotkey}, marking server {server_id} as missing"
                        )
                        self.storage.deactivate_server(server_id, status='missing')
                        self.score_cache.pop(server_id, None)

            else:
                # Collector unavailable, fall back to cached mappings
                for hotkey in hotkeys:
                    if hotkey not in mappings:
                        server_id = self.storage.get_hotkey_server(hotkey)
                        if server_id:
                            mappings[hotkey] = server_id
            
            bt.logging.info(f"Found {len(mappings)} server mappings")
            
        except Exception as e:
            bt.logging.error(f"Error getting server mappings: {e}")
        
        return mappings
    
    async def _score_server(self, server_id: str) -> Optional[Dict[str, any]]:
        """
        Score a single server
        
        Args:
            server_id: Server to score
            
        Returns:
            Scoring result dictionary or None
        """
        try:
            # 1. Fetch latest report from collector
            # Fetch latest report from collector (do not use HTTP latency in scoring)
            status, reports = self.collector_api.get_server_reports(server_id, limit=1)
            
            if status != 200 or not reports:
                bt.logging.debug(f"No reports for server {server_id}")
                return None
            
            # 2. Parse report
            latest_report = ServerReport.from_dict(reports[0])
            
            # 3. Load historical context
            history = self.storage.load_history(server_id, max_rows=60)
            
            # 4. Create scoring context (no registration/integrity/latency effects)
            context = MinerContext(
                report=latest_report,
                http_latency_s=0.0,
                history=history
            )
            
            # 5. Calculate score
            new_score, components = calculate_miner_score(context)
            
            # 6. Apply smoothing
            previous_score_data = self.storage.get_score(server_id)
            previous_score = previous_score_data['score'] if previous_score_data else None
            
            smoothed_score = apply_score_smoothing(new_score, previous_score)
            
            # 7. Store results
            self.storage.append_report(
                server_id,
                latest_report, 
                latency=0.0,
                compliance=True
            )
            
            self.storage.upsert_score(
                server_id,
                smoothed_score,
                components['infrastructure'],
                components['participation'],
                components['reliability']
            )
            
            # 8. Cache for weight updates
            self.score_cache[server_id] = (smoothed_score, time.time())
            
            if DEBUG_SCORING:
                bt.logging.debug(
                    f"Scored server {server_id}: {smoothed_score} (raw: {new_score})"
                )
            
            return {
                'server_id': server_id,
                'score': smoothed_score,
                'raw_score': new_score,
                'components': components,
                'latency': 0.0,
                'compliance': True,
                'reports_count': len(history)
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
        """Clean up old data to prevent database bloat"""
        try:
            bt.logging.info("🧹 Cleaning up old data...")
            
            # Clean up storage
            self.storage.cleanup_old_data(max_age_days=7)
            
            # Clean up replay protection
            self.replay_protection.cleanup_old_entries(max_age_hours=168)
            
            # Clear old score cache
            current_time = time.time()
            old_keys = [
                server_id for server_id, (score, timestamp) in self.score_cache.items()
                if current_time - timestamp > 3600  # 1 hour
            ]
            for key in old_keys:
                del self.score_cache[key]
            
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
            'storage_path': self.storage.db_path,
            'replay_protection_active': True,
            'config': {
                'netuid': self.config.netuid,
                'weight_update_interval': self.weight_update_interval,
                'weight_retry_interval': self.weight_retry_interval
            }
        }


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
        
        # Initialize storage
        storage = get_storage()
        
        # Create runner
        runner = Level114ValidatorRunner(
            config=validator_instance.config,
            subtensor=validator_instance.subtensor,
            metagraph=validator_instance.metagraph,
            wallet=validator_instance.wallet,
            collector_api=collector_api,
            storage=storage
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


# TODO: Integration hooks for existing validator
"""
To integrate with your existing validator, add these calls to your main validator loop:

1. In __init__():
   self.scoring_runner = await integrate_scoring_system(self)

2. In your main loop:
   cycle_stats = await self.scoring_runner.run_scoring_cycle()

3. Replace weight setting with:
   # Weights are automatically set by the scoring runner
   # based on server performance scores

4. Optional: Add status endpoint:
   def get_scoring_status(self):
       return self.scoring_runner.get_status()
"""
