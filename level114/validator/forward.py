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

import bittensor as bt
import numpy as np
from typing import List
from level114.protocol.metrics import MetricsProtocol
from level114.utils.uids import get_random_uids


async def forward(self):
    """
    The forward function is called by the validator every step.

    It is responsible for querying the network and scoring the responses.

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.
    """
    # TODO: The forward function should define the validator's behavior when querying the network.
    
    # Define how many miners to query each step
    k = min(self.config.neuron.sample_size, self.metagraph.n.item())
    
    # Get a random sample of miners to query.
    miner_uids = get_random_uids(self, k=k).tolist()
    
    # The dendrite client queries the network.
    metrics_synapses = []
    for uid in miner_uids:
        synapse = MetricsProtocol(miner_uid=uid)
        metrics_synapses.append(synapse)

    # Get the axon information for the miners we want to query
    axons = [self.metagraph.axons[uid] for uid in miner_uids]

    bt.logging.info(f"Querying {len(miner_uids)} miners for metrics...")

    # The dendrite client queries the network.
    responses = await self.dendrite(
        axons=axons,
        synapse=metrics_synapses,
        deserialize=True,
    )

    # Log the results for monitoring purposes.
    bt.logging.info(f"Received {len(responses)} responses")
    
    # Compute the rewards for the responses given the metrics.
    rewards = get_rewards(self, miner_uids, responses)

    bt.logging.info(f"Scored responses: {rewards}")
    
    # Update the scores based on the rewards. You may want to define your own update_scores function for custom behavior.
    self.update_scores(rewards, miner_uids)


def get_rewards(
    self,
    uids: List[int], 
    responses: List[MetricsProtocol],
) -> np.ndarray:
    """
    Returns a tensor of rewards for the given query and responses.

    Args:
        uids (List[int]): The list of miner UIDs that were queried.
        responses (List[MetricsProtocol]): The list of responses from the miners.

    Returns:
        np.ndarray: The rewards for the responses, normalized to sum to 1.
    """
    # Initialize rewards tensor
    rewards = np.zeros(len(responses))
    
    for i, (uid, response) in enumerate(zip(uids, responses)):
        try:
            # Check if the response was successful
            if not hasattr(response, 'metrics_accepted') or not response.metrics_accepted:
                bt.logging.warning(f"Miner {uid} did not accept metrics request")
                rewards[i] = 0.0
                continue
                
            # Calculate reward based on multiple factors
            reward_components = {}
            
            # 1. Uptime reward (25% weight) - higher is better
            if response.uptime is not None and response.uptime > 0:
                # Normalize uptime to hours and cap at reasonable values
                uptime_hours = min(response.uptime / 3600.0, 24.0 * 30)  # Cap at 30 days
                reward_components['uptime'] = min(uptime_hours / (24.0 * 7), 1.0)  # Normalize to weekly uptime
            else:
                reward_components['uptime'] = 0.0
                
            # 2. Resource efficiency reward (40% weight) - lower usage is better when productive
            cpu_score = 0.0
            memory_score = 0.0
            
            if response.cpu_usage is not None:
                # Reward moderate CPU usage (not too low, not too high)
                if response.cpu_usage < 5.0:
                    cpu_score = 0.3  # Too low might mean not working
                elif response.cpu_usage < 50.0:
                    cpu_score = 1.0  # Good efficiency
                elif response.cpu_usage < 80.0:
                    cpu_score = 0.7  # Acceptable
                else:
                    cpu_score = 0.3  # High usage
            
            if response.memory_usage is not None:
                # Similar scoring for memory
                if response.memory_usage < 10.0:
                    memory_score = 0.5
                elif response.memory_usage < 60.0:
                    memory_score = 1.0
                elif response.memory_usage < 85.0:
                    memory_score = 0.7
                else:
                    memory_score = 0.2
                    
            reward_components['efficiency'] = (cpu_score + memory_score) / 2.0
            
            # 3. Network performance reward (20% weight) - lower latency is better
            if response.network_latency is not None and response.network_latency > 0:
                # Convert latency to score (lower is better)
                if response.network_latency < 50.0:  # < 50ms is excellent
                    reward_components['network'] = 1.0
                elif response.network_latency < 150.0:  # < 150ms is good
                    reward_components['network'] = 0.8
                elif response.network_latency < 500.0:  # < 500ms is acceptable
                    reward_components['network'] = 0.5
                else:
                    reward_components['network'] = 0.2
            else:
                reward_components['network'] = 0.5  # Default score if no data
                
            # 4. Error rate reward (15% weight) - lower is better
            if response.error_rate is not None:
                error_score = max(0.0, 1.0 - (response.error_rate / 100.0))
                reward_components['reliability'] = error_score
            else:
                reward_components['reliability'] = 0.8  # Default if no error data
                
            # Calculate weighted final reward
            weights = {
                'uptime': 0.25,
                'efficiency': 0.40, 
                'network': 0.20,
                'reliability': 0.15
            }
            
            final_reward = 0.0
            for component, score in reward_components.items():
                final_reward += weights[component] * score
                
            # Add small bonus for having task completion data
            if response.tasks_completed is not None and response.tasks_completed > 0:
                final_reward *= 1.1  # 10% bonus for being active
                
            rewards[i] = max(0.0, min(1.0, final_reward))  # Ensure reward is in [0, 1]
            
            bt.logging.debug(f"Miner {uid} reward: {rewards[i]:.4f} (components: {reward_components})")
            
        except Exception as e:
            bt.logging.error(f"Error calculating reward for miner {uid}: {e}")
            rewards[i] = 0.0
    
    # Normalize rewards to sum to 1 if there are any non-zero rewards
    total_reward = np.sum(rewards)
    if total_reward > 0:
        rewards = rewards / total_reward
    else:
        # If all rewards are 0, give equal small rewards to prevent division by zero
        rewards = np.ones_like(rewards) / len(rewards) * 0.001
        
    bt.logging.info(f"Final normalized rewards: {rewards}")
    
    return rewards
