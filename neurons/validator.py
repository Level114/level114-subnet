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
import bittensor as bt
from level114.utils.uids import sequential_select_untrusted

from level114.base.validator import BaseValidatorNeuron


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

    async def validate(self):
        sample_size = getattr(self.config.neuron, 'sample_size', 10)
        start_index = getattr(self, 'selection_index', 0)
        selected_uids, next_index = sequential_select_untrusted(self.metagraph, sample_size, start_index)
        self.selection_index = next_index
        selected_hotkeys = [self.metagraph.hotkeys[uid] for uid in selected_uids]
        bt.logging.info(f"validate() selected uids={selected_uids} hotkeys={selected_hotkeys}")
        if selected_hotkeys:
            status, servers = self.collector_api.get_validator_server_ids(selected_hotkeys)
            if status < 200 or status >= 300:
                await asyncio.sleep(10)
                return
            hk_to_server = {s.hotkey: s for s in servers}
            bt.logging.info(f"collector ids status={status} servers={len(servers)}")
            for hotkey, server in hk_to_server.items():
                rep_status, reports = self.collector_api.get_server_reports(server.id)
                if rep_status < 200 or rep_status >= 300:
                    continue
                bt.logging.info(f"reports status={rep_status} server_id={server.id} hotkey={hotkey} items={len(reports)}")
        await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        Validator().run()
    except KeyboardInterrupt:
        pass
