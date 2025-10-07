"""Minecraft mechanism orchestrating collector scoring."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import bittensor as bt

from level114.validator.mechanisms.base import MechanismContext, ValidatorMechanism
from level114.validator.mechanisms.minecraft.mappings import fetch_server_mappings
from level114.validator.mechanisms.minecraft.scoring import score_server
from level114.validator.mechanisms.minecraft.types import ScoreCacheEntry


class MinecraftMechanism(ValidatorMechanism):
    """Fetch collector reports and compute Minecraft scores."""

    mechanism_id = 0
    mechanism_name = "minecraft"

    def __init__(self, context: MechanismContext) -> None:
        super().__init__(context)
        self.config = context.config
        self.metagraph = context.metagraph
        self.collector_api = context.collector_api

        self.replay_protection = None
        self.score_cache: Dict[str, ScoreCacheEntry] = {}
        self.hotkey_to_server_id: Dict[str, str] = {}
        self.server_id_to_hotkey: Dict[str, str] = {}
        self.server_ids_last_fetch: float = 0.0
        self.server_ids_min_refresh_interval: float = 12.5
        self.report_fetch_limit: int = getattr(
            getattr(self.config, "collector", None), "reports_limit", 25
        )
        self.latest_scores: Dict[str, Dict[str, Any]] = {}
        self.last_cleanup = time.time()

        bt.logging.info("Minecraft mechanism initialized - collector scoring")

    async def run_cycle(self) -> Dict[str, Any]:
        cycle_start = time.time()
        stats: Dict[str, Any] = {
            "cycle_id": self.cycle_count,
            "timestamp": cycle_start,
            "servers_processed": 0,
            "scores_updated": 0,
            "errors": 0,
            "total_time": 0.0,
            "scoring_results": {},
            "mechanism_id": self.mechanism_id,
            "mechanism_name": self.mechanism_name,
        }

        try:
            bt.logging.info(f"🔄 [Minecraft] Starting scoring cycle {self.cycle_count}")
            active_hotkeys = list(self.metagraph.hotkeys)
            server_mappings = self._get_server_mappings(active_hotkeys)
            stats["servers_found"] = len(server_mappings)

            if not server_mappings:
                bt.logging.warning("[Minecraft] No server mappings found for active hotkeys")
                return stats

            scoring_results: Dict[str, Dict[str, Any]] = {}
            for hotkey, server_id in server_mappings.items():
                result = await self._score_server(server_id)
                if result:
                    scoring_results[hotkey] = result
                    stats["scores_updated"] += 1
                stats["servers_processed"] += 1

            stats["scoring_results"] = scoring_results
            self.latest_scores = scoring_results

            if time.time() - self.last_cleanup > 3600:
                self._cleanup_old_data()
                self.last_cleanup = time.time()

        except Exception as exc:  # noqa: BLE001
            bt.logging.error(f"[Minecraft] Critical error in scoring cycle: {exc}")
            stats["errors"] += 1
        finally:
            stats["total_time"] = time.time() - cycle_start
            self.cycle_count += 1
            bt.logging.info(
                (
                    "✅ [Minecraft] Cycle {cycle} complete: {processed} servers, {updated} "
                    "scores updated, {errors} errors, {duration:.1f}s"
                ).format(
                    cycle=stats["cycle_id"],
                    processed=stats.get("servers_processed", 0),
                    updated=stats.get("scores_updated", 0),
                    errors=stats.get("errors", 0),
                    duration=stats["total_time"],
                )
            )

        return stats

    def get_latest_scores(self) -> Dict[str, Dict[str, Any]]:
        return self.latest_scores

    def _get_server_mappings(self, hotkeys: List[str]) -> Dict[str, str]:
        return fetch_server_mappings(self, hotkeys)

    async def _score_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        return score_server(
            mechanism=self,
            server_id=server_id,
            report_fetch_limit=self.report_fetch_limit,
        )

    def _cleanup_old_data(self) -> None:
        try:
            bt.logging.info("🧹 [Minecraft] Cleaning up old data...")
            if self.replay_protection:
                self.replay_protection.cleanup_old_entries(max_age_hours=168)

            current_time = time.time()
            stale_ids = [
                server_id
                for server_id, entry in self.score_cache.items()
                if current_time - entry.updated_at > 3600
            ]
            for server_id in stale_ids:
                self.score_cache.pop(server_id, None)

            bt.logging.info("✅ [Minecraft] Cleanup complete")
        except Exception as exc:  # noqa: BLE001
            bt.logging.error(f"[Minecraft] Error during cleanup: {exc}")

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update(
            {
                "cached_scores": len(self.score_cache),
                "cached_mappings": len(self.hotkey_to_server_id),
                "latest_scores": len(self.latest_scores),
                "replay_protection_active": bool(self.replay_protection),
                "config": {
                    "netuid": self.config.netuid,
                },
            }
        )
        return status

    def get_server_id_for_hotkey(self, hotkey: str) -> Optional[str]:
        return self.hotkey_to_server_id.get(hotkey)

    def get_cached_score(self, server_id: str) -> Optional[ScoreCacheEntry]:
        return self.score_cache.get(server_id)
