"""Helpers for fetching Minecraft server mappings from collector API."""

from __future__ import annotations

import time
from typing import Dict, List

import bittensor as bt


def fetch_server_mappings(mechanism, hotkeys: List[str]) -> Dict[str, str]:
    cached = mechanism.server_ids_last_fetch
    now = time.time()

    if cached and (now - cached) < mechanism.server_ids_min_refresh_interval:
        return mechanism.hotkey_to_server_id.copy()

    try:
        status, mappings = mechanism.collector_api.get_server_mappings(hotkeys)
        if status != 200 or not isinstance(mappings, dict):
            bt.logging.debug(
                f"[Minecraft] Failed to refresh server mappings (status={status});"
                f" using cached data with {len(mechanism.hotkey_to_server_id)} entries"
            )
            return mechanism.hotkey_to_server_id.copy()

        mechanism.server_ids_last_fetch = now
        mechanism.hotkey_to_server_id = {
            hotkey: mapping.get("server_id")
            for hotkey, mapping in mappings.items()
            if isinstance(mapping, dict) and mapping.get("server_id")
        }
        mechanism.server_id_to_hotkey = {
            server_id: hotkey for hotkey, server_id in mechanism.hotkey_to_server_id.items()
        }
        return mechanism.hotkey_to_server_id.copy()

    except Exception as exc:  # noqa: BLE001
        bt.logging.error(f"[Minecraft] Error fetching server mappings: {exc}")
        return mechanism.hotkey_to_server_id.copy()
