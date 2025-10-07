"""Component helpers for Minecraft scoring calculations."""

from __future__ import annotations

import statistics
from collections import deque
from typing import Deque, List, Optional

from level114.validator.mechanisms.minecraft.constants import (
    IDEAL_TPS,
    MAX_RECOVERY_TIME_MINUTES,
    MAX_TPS_BONUS,
    MAX_TPS_COEFFICIENT_OF_VARIATION,
    MAX_UPTIME_BONUS_H,
    MIN_TPS_THRESHOLD,
    RECOVERY_SAMPLE_COUNT,
    RECOVERY_TPS_THRESHOLD,
    TPS_STABILITY_WINDOW,
)
from level114.validator.mechanisms.minecraft.report_schema import ServerReport


def calculate_uptime_score(history: Deque[ServerReport]) -> float:
    try:
        if len(history) < 2:
            return 0.5
        uptimes = [report.payload.system_info.uptime_ms for report in history]
        timestamps = [report.client_timestamp_ms for report in history]
        reset_penalty = 0.0
        resets = 0
        total = len(uptimes)
        for idx in range(1, total):
            if uptimes[idx] < uptimes[idx - 1]:
                resets += 1
                reset_penalty += ((total - idx) / total) * 0.3
        current_hours = uptimes[-1] / 3_600_000
        uptime_score = max(0.0, min(current_hours / MAX_UPTIME_BONUS_H, 1.0) - reset_penalty)
        if resets == 0 and total >= 5:
            growth = []
            for idx in range(1, total):
                time_diff = (timestamps[idx] - timestamps[idx - 1]) / 3_600_000
                uptime_diff = (uptimes[idx] - uptimes[idx - 1]) / 3_600_000
                if time_diff > 0:
                    growth.append(uptime_diff / time_diff)
            if growth and statistics.mean(growth) > 0.8:
                uptime_score = min(1.0, uptime_score * 1.1)
        return uptime_score
    except Exception:  # noqa: BLE001
        return 0.5


def calculate_stability_score(history: Deque[ServerReport]) -> float:
    try:
        if len(history) < TPS_STABILITY_WINDOW:
            return 0.5
        recent = list(history)[-TPS_STABILITY_WINDOW:]
        tps_values = [report.payload.tps_actual for report in recent]
        valid = [tps for tps in tps_values if MIN_TPS_THRESHOLD <= tps <= MAX_TPS_BONUS]
        if len(valid) < 3:
            return 0.1
        mean_tps = statistics.mean(valid)
        if mean_tps <= 0:
            return 0.0
        stdev_tps = statistics.stdev(valid) if len(valid) > 1 else 0.0
        cv = stdev_tps / mean_tps
        stability = max(0.0, 1.0 - (cv / MAX_TPS_COEFFICIENT_OF_VARIATION))
        if mean_tps >= IDEAL_TPS * 0.9:
            stability = min(1.0, stability * 1.1)
        return stability
    except Exception:  # noqa: BLE001
        return 0.5


def calculate_recovery_score(history: Deque[ServerReport]) -> float:
    try:
        if len(history) < 10:
            return 1.0
        recent = list(history)[-30:]
        recovery = 1.0
        for idx, report in enumerate(recent):
            if report.payload.tps_actual < RECOVERY_TPS_THRESHOLD:
                recovery_time = measure_recovery_time(recent[idx:])
                if recovery_time is None:
                    recovery *= 0.5
                elif recovery_time > MAX_RECOVERY_TIME_MINUTES:
                    recovery *= 0.7
                else:
                    recovery *= 1.0 - (recovery_time / MAX_RECOVERY_TIME_MINUTES) * 0.3
        return max(0.0, min(1.0, recovery))
    except Exception:  # noqa: BLE001
        return 1.0


def measure_recovery_time(reports_after_issue: List[ServerReport]) -> Optional[float]:
    try:
        if len(reports_after_issue) < RECOVERY_SAMPLE_COUNT:
            return None
        good_samples = 0
        start_time = reports_after_issue[0].client_timestamp_ms
        for report in reports_after_issue[1:]:
            if report.payload.tps_actual >= RECOVERY_TPS_THRESHOLD:
                good_samples += 1
                if good_samples >= RECOVERY_SAMPLE_COUNT:
                    diff_ms = report.client_timestamp_ms - start_time
                    return diff_ms / 60_000
            else:
                good_samples = 0
        return None
    except Exception:  # noqa: BLE001
        return None
