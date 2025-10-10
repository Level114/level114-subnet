"""Minecraft mechanism orchestrating collector scoring."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import bittensor as bt

from level114.validator.mechanisms.base import MechanismContext, ValidatorMechanism
from level114.validator.mechanisms.minecraft._scanner_controller import MinecraftScanner
from level114.validator.mechanisms.minecraft._scanner_logger import _BTScannerLogger
from level114.validator.mechanisms.minecraft._voting_client import VoteClient
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

        validator_cfg = getattr(self.config, "validator", None)
        configured_interval = (
            getattr(validator_cfg, "scanner_interval_seconds", 24 * 60)
            if validator_cfg
            else 24 * 60
        )
        try:
            interval_value = float(configured_interval)
            if not interval_value or interval_value != interval_value:
                raise ValueError
        except (TypeError, ValueError):
            interval_value = 24 * 60.0
        self.scan_interval = max(interval_value, 300.0)

        self._scanner_logger = _BTScannerLogger()
        self.scanner = MinecraftScanner(self.collector_api, self._scanner_logger, self.scan_interval)

        self.vote_client_version = (
            getattr(validator_cfg, "client_version", None) if validator_cfg else None
        )
        if not isinstance(self.vote_client_version, str) or not self.vote_client_version.strip():
            self.vote_client_version = "validator-agent/2.1.0"
        self.vote_client = VoteClient(self.collector_api, self.vote_client_version)

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

            stats["scanner"] = await self.scanner.refresh(list(server_mappings.values()))

            scoring_results: Dict[str, Dict[str, Any]] = {}
            pending_votes: List[Tuple[str, Dict[str, Any]]] = []
            for hotkey, server_id in server_mappings.items():
                result = await self._score_server(server_id)
                if result:
                    scoring_results[hotkey] = result
                    stats["scores_updated"] += 1
                    pending_votes.append((server_id, result))
                stats["servers_processed"] += 1

            stats["votes"] = await self.vote_client.submit_votes(pending_votes)

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
            scanner_entry=self.scan_results.get(server_id),
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
        status.update({
            "cached_scores": len(self.score_cache),
            "cached_mappings": len(self.hotkey_to_server_id),
            "latest_scores": len(self.latest_scores),
            "replay_protection_active": bool(self.replay_protection),
            "config": {"netuid": self.config.netuid},
            "scanner_last_run": self.scanner.last_scan_time or None,
            "scanner_interval_seconds": self.scan_interval,
            "scanner_cached": sum(1 for entry in self.scan_results.values() if entry is not None),
            "scanner_missing": sum(1 for entry in self.scan_results.values() if entry is None),
            "scanner_last_status": self.scanner.last_status,
            "scanner_last_error": self.scanner.last_error,
            "scanner_metrics": self.scanner.last_metrics,
            "scanner_disabled": sorted(self.scanner.disabled_scanners),
        })
        return status

    def get_server_id_for_hotkey(self, hotkey: str) -> Optional[str]:
        return self.hotkey_to_server_id.get(hotkey)

    def get_cached_score(self, server_id: str) -> Optional[ScoreCacheEntry]:
        return self.score_cache.get(server_id)

    scan_results = property(lambda self: self.scanner.results)
    scan_last_metrics = property(lambda self: self.scanner.last_metrics)
    scan_last_attempt_ids = property(lambda self: self.scanner.last_attempt_ids)
    scan_missing_ids = property(lambda self: self.scanner.missing_ids)
    scan_last_status = property(lambda self: self.scanner.last_status)
    scan_last_error = property(lambda self: self.scanner.last_error)
    scan_disabled_scanners = property(lambda self: self.scanner.disabled_scanners)
