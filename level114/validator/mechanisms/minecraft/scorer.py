"""Scoring logic for Minecraft validator reports."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from level114.validator.mechanisms.minecraft.constants import (
    BONUS_PLUGINS,
    DEBUG_SCORING,
    DEFAULT_SCORE,
    EMA_ALPHA,
    IDEAL_TPS,
    MAX_PLAYERS_WEIGHT,
    MAX_REPORT_HISTORY,
    MAX_SCORE,
    MAX_SCORE_CHANGE,
    MAX_TPS_BONUS,
    MAX_UPTIME_BONUS_H,
    MIN_PLAYERS_FOR_BONUS,
    MIN_REPORTS_FOR_RELIABILITY,
    MIN_SCORE,
    MIN_SCORE_CHANGE,
    MIN_TPS_THRESHOLD,
    OPTIMAL_PLAYER_RATIO_MAX,
    OPTIMAL_PLAYER_RATIO_MIN,
    W_INFRA,
    W_INFRA_TPS,
    W_PART,
    W_PART_COMPLIANCE,
    W_PART_PLAYERS,
    W_RELY,
    W_RELY_RECOVERY,
    W_RELY_STABILITY,
    W_RELY_UPTIME,
)
from level114.validator.mechanisms.minecraft.report_schema import ServerReport
from level114.validator.mechanisms.minecraft.scorer_components import (
    calculate_recovery_score,
    calculate_stability_score,
    calculate_uptime_score,
)


@dataclass
class MinerContext:
    report: ServerReport
    http_latency_s: float
    history: Deque[ServerReport]

    def __post_init__(self) -> None:
        if not isinstance(self.history, deque):
            self.history = deque(self.history or [], maxlen=MAX_REPORT_HISTORY)
        self.http_latency_s = 0.0


def evaluate_infrastructure(ctx: MinerContext) -> float:
    try:
        tps_actual = ctx.report.payload.tps_actual
        tps_clamped = max(0.0, min(tps_actual, MAX_TPS_BONUS))
        tps_score = (tps_clamped / IDEAL_TPS) if IDEAL_TPS > 0 else 0.0
        tps_score = min(1.0, tps_score)
        if tps_actual < MIN_TPS_THRESHOLD:
            tps_score *= 0.1
        infra_score = W_INFRA_TPS * tps_score
        if DEBUG_SCORING:
            print(f"Infrastructure: TPS={tps_score:.3f} -> {infra_score:.3f}")
        return max(0.0, min(1.0, infra_score))
    except Exception as exc:  # noqa: BLE001
        if DEBUG_SCORING:
            print(f"Infrastructure scoring error: {exc}")
        return 0.0


def evaluate_participation(ctx: MinerContext) -> float:
    try:
        payload = ctx.report.payload
        compliance = 0.6 if payload.has_required_plugins else 0.0
        plugin_set = {plugin.strip() for plugin in payload.plugins}
        bonus_plugins = len(plugin_set & BONUS_PLUGINS)
        max_bonus = min(len(BONUS_PLUGINS), 10)
        compliance += min(0.4, bonus_plugins / max_bonus * 0.4 if max_bonus else 0.0)
        compliance = min(1.0, compliance)

        players_score = 0.0
        player_count = payload.player_count
        if player_count >= MIN_PLAYERS_FOR_BONUS:
            raw = min(player_count / MAX_PLAYERS_WEIGHT, 1.0)
            if payload.max_players > 0:
                ratio = player_count / payload.max_players
                if OPTIMAL_PLAYER_RATIO_MIN <= ratio <= OPTIMAL_PLAYER_RATIO_MAX:
                    raw *= 1.2
                elif ratio > 0.95:
                    raw *= 0.8
            players_score = min(1.0, raw)

        part_score = W_PART_COMPLIANCE * compliance + W_PART_PLAYERS * players_score
        if DEBUG_SCORING:
            print(
                "Participation:"
                f" Compliance={compliance:.3f}, Players={players_score:.3f}"
                f" -> {part_score:.3f}"
            )
        return max(0.0, min(1.0, part_score))
    except Exception as exc:  # noqa: BLE001
        if DEBUG_SCORING:
            print(f"Participation scoring error: {exc}")
        return 0.0


def evaluate_reliability(ctx: MinerContext) -> float:
    try:
        history = ctx.history
        if len(history) < MIN_REPORTS_FOR_RELIABILITY:
            uptime_hours = ctx.report.payload.system_info.uptime_hours
            return min(uptime_hours / (MAX_UPTIME_BONUS_H / 2), 1.0) * 0.5

        uptime_score = calculate_uptime_score(history)
        stability_score = calculate_stability_score(history)
        recovery_score = calculate_recovery_score(history)
        reliability = (
            W_RELY_UPTIME * uptime_score
            + W_RELY_STABILITY * stability_score
            + W_RELY_RECOVERY * recovery_score
        )
        if DEBUG_SCORING:
            print(
                "Reliability:"
                f" Uptime={uptime_score:.3f}, Stability={stability_score:.3f},"
                f" Recovery={recovery_score:.3f} -> {reliability:.3f}"
            )
        return max(0.0, min(1.0, reliability))
    except Exception as exc:  # noqa: BLE001
        if DEBUG_SCORING:
            print(f"Reliability scoring error: {exc}")
        return 0.0


def normalize_score(raw_score: float) -> int:
    clamped = max(0.0, min(1.0, raw_score))
    score_range = MAX_SCORE - MIN_SCORE
    normalized = MIN_SCORE + int(round(score_range * clamped))
    return max(MIN_SCORE, min(MAX_SCORE, normalized))


def calculate_miner_score(ctx: MinerContext) -> Tuple[int, Dict[str, float]]:
    try:
        infra = evaluate_infrastructure(ctx)
        part = evaluate_participation(ctx)
        rely = evaluate_reliability(ctx)
        raw = W_INFRA * infra + W_PART * part + W_RELY * rely
        final_score = normalize_score(raw)
        components = {
            "infrastructure": infra,
            "participation": part,
            "reliability": rely,
            "raw_combined": raw,
            "final_normalized": final_score,
        }
        if DEBUG_SCORING:
            print(
                f"Final Score: {final_score}"
                f" (infra={infra:.3f}, part={part:.3f}, rely={rely:.3f})"
            )
        return final_score, components
    except Exception as exc:  # noqa: BLE001
        if DEBUG_SCORING:
            print(f"Score calculation error: {exc}")
        return DEFAULT_SCORE, {
            "infrastructure": 0.0,
            "participation": 0.0,
            "reliability": 0.0,
            "raw_combined": 0.0,
            "final_normalized": DEFAULT_SCORE,
        }


def apply_score_smoothing(new_score: int, previous_score: Optional[int] = None, alpha: float = EMA_ALPHA) -> int:
    if previous_score is None:
        return new_score
    smoothed = alpha * new_score + (1 - alpha) * previous_score
    smoothed_int = int(round(smoothed))
    max_change = min(MAX_SCORE_CHANGE, max(MIN_SCORE_CHANGE, abs(new_score - previous_score) * 0.5))
    if abs(smoothed_int - previous_score) > max_change:
        smoothed_int = (
            previous_score + max_change if smoothed_int > previous_score else previous_score - max_change
        )
    if abs(smoothed_int - previous_score) < MIN_SCORE_CHANGE:
        return previous_score
    return max(MIN_SCORE, min(MAX_SCORE, smoothed_int))
