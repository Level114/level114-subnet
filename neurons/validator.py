# The MIT License (MIT)
# Copyright © 2025 Level114 Team

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import asyncio
import time
import bittensor as bt
from level114.utils.uids import sequential_select_untrusted

from level114.base.validator import BaseValidatorNeuron
from level114.validator.runner import Level114ValidatorRunner
from level114.validator.storage import get_storage


MIN_VALIDATION_INTERVAL = 70  # seconds


class Validator(BaseValidatorNeuron):
    """
    Level114 validator neuron class. This validator queries nodes for their performance metrics
    and uses those metrics to set weights based on node performance evaluation.
    
    The validator queries nodes that have registered with the collector-center-main service
    and evaluates their reported metrics to determine appropriate weight distributions.
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        bt.logging.info("load_state()")
        self.load_state()
        
        # Initialize Level114 scoring system
        bt.logging.info("Initializing Level114 scoring system...")
        try:
            # Initialize storage for scoring system
            self.storage = get_storage()
            
            # Initialize the comprehensive validator runner
            self.scoring_runner = Level114ValidatorRunner(
                config=self.config,
                subtensor=self.subtensor,
                metagraph=self.metagraph,
                wallet=self.wallet,
                collector_api=self.collector_api,
                storage=self.storage
            )
            
            bt.logging.success("✅ Level114 scoring system initialized successfully")
            bt.logging.info(f"📊 Storage: {self.storage.db_path}")
            bt.logging.info(f"⚖️  Weight update interval: {getattr(self.config.validator, 'weight_update_interval', 300)}s")
            
        except Exception as e:
            bt.logging.error(f"❌ Failed to initialize scoring system: {e}")
            raise

    async def validate(self):
        """
        Main validation step using Level114 comprehensive scoring system
        
        This replaces the basic validation with our advanced scoring that:
        1. Fetches all server reports from collector API
        2. Verifies report integrity (hash/signature validation)
        3. Calculates comprehensive scores (infrastructure, participation, reliability)
        4. Updates Bittensor weights based on server performance
        5. Persists scoring history and analytics
        """
        try:
            # Check if enough time has passed since last validation
            configured_interval = getattr(
                self.config.validator, 'validation_interval', MIN_VALIDATION_INTERVAL
            )
            validation_interval = max(configured_interval, MIN_VALIDATION_INTERVAL)
            current_time = time.time()
            
            if not hasattr(self, 'last_validation_time'):
                self.last_validation_time = 0
            
            if (
                validation_interval > configured_interval
                and not getattr(self, '_warned_validation_interval', False)
            ):
                bt.logging.warning(
                    f"Validation interval increased to {validation_interval}s (minimum enforced)"
                )
                self._warned_validation_interval = True
            
            if current_time - self.last_validation_time < validation_interval:
                # Not time for validation yet, just wait
                await asyncio.sleep(1)
                return
            
            bt.logging.info("🔄 Starting Level114 validation cycle...")
            
            # Run comprehensive scoring cycle
            cycle_stats = await self.scoring_runner.run_scoring_cycle()
            
            # Update last validation time
            self.last_validation_time = current_time
            
            # Log detailed results
            bt.logging.info(
                f"✅ Validation cycle complete: "
                f"{cycle_stats['servers_processed']} servers processed, "
                f"{cycle_stats['scores_updated']} scores updated, "
                f"{cycle_stats['errors']} errors, "
                f"weights updated: {cycle_stats['weights_updated']}, "
                f"cycle time: {cycle_stats['total_time']:.1f}s"
            )
            
            # Update traditional scores for compatibility with base class
            # This ensures existing monitoring and state saving still works
            if cycle_stats['scores_updated'] > 0:
                self._update_legacy_scores()
            
            # Status summary every 10 cycles
            if self.scoring_runner.cycle_count % 10 == 0:
                self._log_validator_status()
            
        except Exception as e:
            bt.logging.error(f"❌ Error in validation cycle: {e}")
            bt.logging.error(f"❌ Error details: {type(e).__name__}: {str(e)}")
            
            # Fall back to basic validation to avoid complete failure
            try:
                bt.logging.warning("🔧 Attempting fallback validation...")
                await self._basic_fallback_validation()
            except Exception as fallback_error:
                bt.logging.error(f"❌ Fallback validation also failed: {fallback_error}")
                # Wait a bit longer if both systems fail
                await asyncio.sleep(30)
    
    def _update_legacy_scores(self):
        """
        Update legacy scoring system for compatibility with base validator class
        
        This syncs our advanced scoring results with the traditional score tracking
        so existing state saving, monitoring, and UI still work correctly.
        """
        try:
            # Get current scores from our scoring system
            hotkey_to_uid = {axon.hotkey: uid for uid, axon in enumerate(self.metagraph.axons)}
            
            # Initialize score updates
            score_updates = {}
            
            # Get scores from our storage for each active server
            for hotkey in self.metagraph.hotkeys:
                if hotkey in hotkey_to_uid:
                    uid = hotkey_to_uid[hotkey]
                    
                    # Try to get server ID for this hotkey
                    server_id = self.storage.get_hotkey_server(hotkey)
                    if server_id:
                        # Get latest score
                        score_data = self.storage.get_score(server_id)
                        if score_data:
                            # Convert our 0-1000 score to 0-1 range for legacy system
                            normalized_score = score_data['score'] / 1000.0
                            score_updates[uid] = normalized_score
            
            # Update scores if we have any
            if score_updates:
                for uid, score in score_updates.items():
                    if uid < len(self.scores):
                        self.scores[uid] = score
                
                bt.logging.debug(f"Updated legacy scores for {len(score_updates)} miners")
            
        except Exception as e:
            bt.logging.error(f"Error updating legacy scores: {e}")
    
    def _log_validator_status(self):
        """Log comprehensive validator status summary"""
        try:
            status = self.scoring_runner.get_status()
            
            bt.logging.info("=" * 60)
            bt.logging.info("📊 LEVEL114 VALIDATOR STATUS SUMMARY")
            bt.logging.info("=" * 60)
            bt.logging.info(f"🔄 Cycles completed: {status['cycle_count']}")
            bt.logging.info(f"⚖️  Last weights update: {time.ctime(status['last_weights_update']) if status['last_weights_update'] else 'Never'}")
            bt.logging.info(f"🗂️  Cached scores: {status['cached_scores']}")
            bt.logging.info(f"💾 Storage: {status['storage_path']}")
            bt.logging.info(f"🔒 Replay protection: {'Active' if status['replay_protection_active'] else 'Inactive'}")
            
            # Network info
            bt.logging.info(f"🌐 Network: {self.config.subtensor.network}")
            bt.logging.info(f"🔢 Subnet: {status['config']['netuid']}")
            bt.logging.info(f"👥 Metagraph size: {self.metagraph.n}")
            
            # Weight timing
            weight_interval = status['config']['weight_update_interval'] 
            next_update = status.get('next_weight_update')
            if not next_update:
                next_update = status['last_weights_update'] + weight_interval if status['last_weights_update'] else time.time()
            time_to_next = max(0, next_update - time.time())
            bt.logging.info(f"⏰ Next weight update: {time_to_next:.0f}s")
            bt.logging.info(
                f"🔁 Weight retry interval: {status['config'].get('weight_retry_interval', 'n/a')}s"
            )
            
            bt.logging.info("=" * 60)
            
        except Exception as e:
            bt.logging.error(f"Error logging validator status: {e}")
    
    async def _basic_fallback_validation(self):
        """
        Basic fallback validation in case our comprehensive system fails
        
        This provides minimal functionality to keep the validator running
        while issues with the scoring system are resolved.
        """
        bt.logging.warning("⚠️  Using basic fallback validation")
        
        try:
            # Basic sampling like the original validator
            sample_size = min(getattr(self.config.neuron, 'sample_size', 10), len(self.metagraph.hotkeys))
            start_index = getattr(self, 'selection_index', 0)
            selected_uids, next_index = sequential_select_untrusted(self.metagraph, sample_size, start_index)
            self.selection_index = next_index
            
            selected_hotkeys = [self.metagraph.hotkeys[uid] for uid in selected_uids]
            bt.logging.info(f"🔍 Fallback validation: checking {len(selected_hotkeys)} hotkeys")
            
            # Try to fetch some basic data
            if selected_hotkeys:
                status, servers = self.collector_api.get_validator_server_ids(selected_hotkeys)
                if 200 <= status < 300:
                    bt.logging.info(f"✅ Collector API accessible: {len(servers)} servers found")
                else:
                    bt.logging.warning(f"⚠️  Collector API issue: status {status}")
            
        except Exception as e:
            bt.logging.error(f"❌ Error in fallback validation: {e}")


if __name__ == "__main__":
    try:
        Validator().run()
    except KeyboardInterrupt:
        pass
