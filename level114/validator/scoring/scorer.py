"""
Level114 Subnet - Scoring Functions

Main scoring logic for evaluating Minecraft server performance.
Combines infrastructure, participation, and reliability metrics into a final score.
"""

import math
import statistics
from collections import deque
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import time

from .report_schema import ServerReport
from .constants import *


@dataclass
class MinerContext:
    """
    Context data for scoring a miner server
    """
    report: ServerReport                    # Latest server report
    http_latency_s: float                   # HTTP latency measured by validator
    registration_ok: bool                   # Server is properly registered
    compliance_ok: bool                     # Integrity checks passed
    history: deque                          # Recent report history (ServerReport objects)
    
    def __post_init__(self):
        """Initialize with defaults if needed"""
        if not isinstance(self.history, deque):
            self.history = deque(self.history or [], maxlen=MAX_REPORT_HISTORY)
        
        # Ensure reasonable latency value
        self.http_latency_s = max(0.0, min(self.http_latency_s, MAX_LATENCY_S * 2))


def evaluate_infrastructure(miner_ctx: MinerContext) -> float:
    """
    Evaluate infrastructure performance (TPS, latency, resources)
    
    Args:
        miner_ctx: Miner context with report and metrics
        
    Returns:
        Infrastructure score [0.0-1.0]
    """
    try:
        report = miner_ctx.report
        payload = report.payload
        
        # 1. TPS Score (55% of infrastructure)
        tps_actual = payload.tps_actual  # Converted from tps_millis
        tps_clamped = max(0.0, min(tps_actual, MAX_TPS_BONUS))
        tps_score = tps_clamped / IDEAL_TPS if IDEAL_TPS > 0 else 0.0
        tps_score = min(1.0, tps_score)  # Cap at 1.0
        
        # Penalty for very low TPS
        if tps_actual < MIN_TPS_THRESHOLD:
            tps_score *= 0.1  # Severe penalty for broken servers
        
        # 2. Latency Score (25% of infrastructure)  
        latency_clamped = max(0.0, min(miner_ctx.http_latency_s, MAX_LATENCY_S))
        latency_score = 1.0 - (latency_clamped / MAX_LATENCY_S)
        
        # Bonus for excellent latency
        if miner_ctx.http_latency_s <= EXCELLENT_LATENCY_S:
            latency_score = min(1.0, latency_score * 1.1)
        
        # 3. Memory Headroom Score (20% of infrastructure)
        memory_info = payload.memory_ram_info
        if memory_info.total_bytes > 0:
            headroom_ratio = memory_info.free_ratio
            
            if headroom_ratio < MIN_MEMORY_HEADROOM:
                # Penalty for low memory
                memory_score = headroom_ratio / MIN_MEMORY_HEADROOM * 0.5
            elif headroom_ratio > (1 - IDEAL_MEMORY_USAGE):
                # Good headroom
                memory_score = 1.0
            else:
                # Linear scale between minimum and ideal
                range_size = (1 - IDEAL_MEMORY_USAGE) - MIN_MEMORY_HEADROOM
                memory_score = 0.5 + 0.5 * (headroom_ratio - MIN_MEMORY_HEADROOM) / range_size
                
            memory_score = max(0.0, min(1.0, memory_score))
        else:
            memory_score = 0.5  # Default for missing memory data
        
        # Combine with weights
        infra_score = (
            W_INFRA_TPS * tps_score +
            W_INFRA_LATENCY * latency_score +
            W_INFRA_MEMORY * memory_score
        )
        
        if DEBUG_SCORING:
            print(f"Infrastructure: TPS={tps_score:.3f}, Latency={latency_score:.3f}, Memory={memory_score:.3f} -> {infra_score:.3f}")
        
        return max(0.0, min(1.0, infra_score))
        
    except Exception as e:
        if DEBUG_SCORING:
            print(f"Infrastructure scoring error: {e}")
        return 0.0


def evaluate_participation(miner_ctx: MinerContext) -> float:
    """
    Evaluate participation metrics (compliance, players, registration)
    
    Args:
        miner_ctx: Miner context with report and metrics
        
    Returns:
        Participation score [0.0-1.0]
    """
    try:
        report = miner_ctx.report
        payload = report.payload
        
        # 1. Compliance Score (55% of participation)
        compliance_score = 0.0
        
        # Required plugins check
        has_required = payload.has_required_plugins
        if has_required:
            compliance_score += 0.6  # 60% for required plugins
        
        # Bonus for additional useful plugins
        plugin_set = {plugin.strip() for plugin in payload.plugins}
        bonus_plugins_present = len(plugin_set & BONUS_PLUGINS)
        max_bonus = min(len(BONUS_PLUGINS), 10)  # Cap bonus plugins considered
        plugin_bonus = min(0.4, bonus_plugins_present / max_bonus * 0.4)  # Up to 40% bonus
        compliance_score += plugin_bonus
        
        # Integrity verification bonus/penalty
        if miner_ctx.compliance_ok:
            compliance_score = min(1.0, compliance_score)
        else:
            compliance_score *= INTEGRITY_FAILURE_CAP  # Major penalty for integrity failure
        
        # 2. Players Score (30% of participation)
        player_count = payload.player_count
        players_score = 0.0
        
        if player_count >= MIN_PLAYERS_FOR_BONUS:
            # Calculate based on count up to maximum weight
            raw_player_score = min(player_count / MAX_PLAYERS_WEIGHT, 1.0)
            
            # Bonus for optimal occupancy ratio
            if payload.max_players > 0:
                occupancy_ratio = player_count / payload.max_players
                if OPTIMAL_PLAYER_RATIO_MIN <= occupancy_ratio <= OPTIMAL_PLAYER_RATIO_MAX:
                    raw_player_score *= 1.2  # 20% bonus for good ratio
                elif occupancy_ratio > 0.95:
                    raw_player_score *= 0.8  # Penalty for overcrowding
            
            players_score = min(1.0, raw_player_score)
        
        # 3. Registration Score (15% of participation)
        registration_score = 1.0 if miner_ctx.registration_ok else 0.0
        
        # Combine with weights
        part_score = (
            W_PART_COMPLIANCE * compliance_score +
            W_PART_PLAYERS * players_score +
            W_PART_REGISTRATION * registration_score
        )
        
        if DEBUG_SCORING:
            print(f"Participation: Compliance={compliance_score:.3f}, Players={players_score:.3f}, Registration={registration_score:.3f} -> {part_score:.3f}")
        
        return max(0.0, min(1.0, part_score))
        
    except Exception as e:
        if DEBUG_SCORING:
            print(f"Participation scoring error: {e}")
        return 0.0


def evaluate_reliability(miner_ctx: MinerContext) -> float:
    """
    Evaluate reliability metrics (uptime, stability, recovery)
    
    Args:
        miner_ctx: Miner context with report and metrics
        
    Returns:
        Reliability score [0.0-1.0]
    """
    try:
        report = miner_ctx.report
        history = miner_ctx.history
        
        # Need minimum history for reliability scoring
        if len(history) < MIN_REPORTS_FOR_RELIABILITY:
            # Use basic uptime for new servers
            uptime_hours = report.payload.system_info.uptime_hours
            basic_score = min(uptime_hours / (MAX_UPTIME_BONUS_H / 2), 1.0)
            return basic_score * 0.5  # Reduced score for insufficient history
        
        # 1. Uptime Trend Score (50% of reliability)
        uptime_score = _calculate_uptime_score(history)
        
        # 2. TPS Stability Score (35% of reliability)
        stability_score = _calculate_stability_score(history)
        
        # 3. Recovery Score (15% of reliability)
        recovery_score = _calculate_recovery_score(history)
        
        # Combine with weights
        rely_score = (
            W_RELY_UPTIME * uptime_score +
            W_RELY_STABILITY * stability_score +
            W_RELY_RECOVERY * recovery_score
        )
        
        if DEBUG_SCORING:
            print(f"Reliability: Uptime={uptime_score:.3f}, Stability={stability_score:.3f}, Recovery={recovery_score:.3f} -> {rely_score:.3f}")
        
        return max(0.0, min(1.0, rely_score))
        
    except Exception as e:
        if DEBUG_SCORING:
            print(f"Reliability scoring error: {e}")
        return 0.0


def _calculate_uptime_score(history: deque) -> float:
    """Calculate uptime trend score from history"""
    try:
        if len(history) < 2:
            return 0.5
        
        # Extract uptime values
        uptimes = []
        timestamps = []
        for report in history:
            uptimes.append(report.payload.system_info.uptime_ms)
            timestamps.append(report.client_timestamp_ms)
        
        # Detect resets (uptime decreases)
        reset_count = 0
        reset_penalty = 0.0
        
        for i in range(1, len(uptimes)):
            if uptimes[i] < uptimes[i-1]:
                reset_count += 1
                # More recent resets are penalized more heavily
                age_factor = (len(uptimes) - i) / len(uptimes)
                reset_penalty += age_factor * 0.3
        
        # Base score from current uptime
        current_uptime_hours = uptimes[-1] / (1000 * 60 * 60)
        uptime_score = min(current_uptime_hours / MAX_UPTIME_BONUS_H, 1.0)
        
        # Apply reset penalties
        uptime_score = max(0.0, uptime_score - reset_penalty)
        
        # Bonus for consistent uptime growth
        if reset_count == 0 and len(uptimes) >= 5:
            # Check if uptime is growing consistently
            growth_rates = []
            for i in range(1, len(uptimes)):
                time_diff = (timestamps[i] - timestamps[i-1]) / 1000 / 3600  # hours
                uptime_diff = (uptimes[i] - uptimes[i-1]) / 1000 / 3600  # hours
                if time_diff > 0:
                    growth_rates.append(uptime_diff / time_diff)
            
            if growth_rates and statistics.mean(growth_rates) > 0.8:  # Growing ~linearly
                uptime_score = min(1.0, uptime_score * 1.1)
        
        return uptime_score
        
    except Exception:
        return 0.5


def _calculate_stability_score(history: deque) -> float:
    """Calculate TPS stability score from history"""
    try:
        if len(history) < TPS_STABILITY_WINDOW:
            return 0.5
        
        # Extract recent TPS values
        recent_history = list(history)[-TPS_STABILITY_WINDOW:]
        tps_values = [report.payload.tps_actual for report in recent_history]
        
        # Filter out obviously broken values
        valid_tps = [tps for tps in tps_values if MIN_TPS_THRESHOLD <= tps <= MAX_TPS_BONUS]
        
        if len(valid_tps) < 3:
            return 0.1  # Insufficient valid data
        
        # Calculate coefficient of variation
        mean_tps = statistics.mean(valid_tps)
        if mean_tps <= 0:
            return 0.0
        
        stdev_tps = statistics.stdev(valid_tps) if len(valid_tps) > 1 else 0
        cv = stdev_tps / mean_tps
        
        # Convert CV to stability score (lower CV = higher stability)
        stability_score = max(0.0, 1.0 - (cv / MAX_TPS_COEFFICIENT_OF_VARIATION))
        
        # Bonus for consistently high TPS
        if mean_tps >= IDEAL_TPS * 0.9:  # Within 10% of ideal
            stability_score = min(1.0, stability_score * 1.1)
        
        return stability_score
        
    except Exception:
        return 0.5


def _calculate_recovery_score(history: deque) -> float:
    """Calculate recovery score after detected issues"""
    try:
        if len(history) < 10:
            return 1.0  # Default to good recovery for new servers
        
        recent_reports = list(history)[-30:]  # Last 30 reports
        recovery_score = 1.0
        
        # Look for TPS drops and recovery patterns
        for i, report in enumerate(recent_reports):
            tps = report.payload.tps_actual
            
            # Detect TPS drops
            if tps < RECOVERY_TPS_THRESHOLD:
                # Look for recovery in subsequent reports
                recovery_time = _measure_recovery_time(recent_reports[i:])
                
                if recovery_time is None:
                    recovery_score *= 0.5  # No recovery detected
                elif recovery_time > MAX_RECOVERY_TIME_MINUTES:
                    recovery_score *= 0.7  # Slow recovery
                else:
                    # Faster recovery = better score
                    recovery_factor = 1.0 - (recovery_time / MAX_RECOVERY_TIME_MINUTES) * 0.3
                    recovery_score *= recovery_factor
        
        return max(0.0, min(1.0, recovery_score))
        
    except Exception:
        return 1.0


def _measure_recovery_time(reports_after_issue: List[ServerReport]) -> Optional[float]:
    """Measure time to recover after an issue"""
    try:
        if len(reports_after_issue) < RECOVERY_SAMPLE_COUNT:
            return None
        
        good_samples = 0
        start_time = reports_after_issue[0].client_timestamp_ms
        
        for report in reports_after_issue[1:]:
            if report.payload.tps_actual >= RECOVERY_TPS_THRESHOLD:
                good_samples += 1
                if good_samples >= RECOVERY_SAMPLE_COUNT:
                    # Found recovery
                    recovery_time_ms = report.client_timestamp_ms - start_time
                    return recovery_time_ms / (1000 * 60)  # Convert to minutes
            else:
                good_samples = 0  # Reset counter on bad sample
        
        return None  # No recovery detected
        
    except Exception:
        return None


def normalize_score(raw_score: float) -> int:
    """
    Normalize raw score [0.0-1.0] to validator weight scale
    
    Args:
        raw_score: Raw score between 0.0 and 1.0
        
    Returns:
        Normalized score between MIN_SCORE and MAX_SCORE
    """
    # Clamp input
    clamped = max(0.0, min(1.0, raw_score))
    
    # Map to output range
    score_range = MAX_SCORE - MIN_SCORE
    normalized = MIN_SCORE + int(round(score_range * clamped))
    
    return max(MIN_SCORE, min(MAX_SCORE, normalized))


def calculate_miner_score(miner_ctx: MinerContext) -> Tuple[int, Dict[str, float]]:
    """
    Calculate comprehensive miner score from context
    
    Args:
        miner_ctx: Miner context with all scoring data
        
    Returns:
        Tuple of (final_score, component_scores)
    """
    try:
        # Calculate component scores
        infra_score = evaluate_infrastructure(miner_ctx)
        part_score = evaluate_participation(miner_ctx)
        rely_score = evaluate_reliability(miner_ctx)
        
        # Combine with weights
        raw_score = (
            W_INFRA * infra_score +
            W_PART * part_score +
            W_RELY * rely_score
        )
        
        # Apply final penalties for critical failures
        if not miner_ctx.compliance_ok:
            raw_score = min(raw_score, INTEGRITY_FAILURE_CAP)
        
        if not miner_ctx.registration_ok:
            raw_score *= 0.8  # 20% penalty for registration issues
        
        # Normalize to final score
        final_score = normalize_score(raw_score)
        
        # Component breakdown for debugging/analysis
        components = {
            'infrastructure': infra_score,
            'participation': part_score,
            'reliability': rely_score,
            'raw_combined': raw_score,
            'final_normalized': final_score
        }
        
        if DEBUG_SCORING:
            print(f"Final Score: {final_score} (infra={infra_score:.3f}, part={part_score:.3f}, rely={rely_score:.3f})")
        
        return final_score, components
        
    except Exception as e:
        if DEBUG_SCORING:
            print(f"Score calculation error: {e}")
        return DEFAULT_SCORE, {
            'infrastructure': 0.0,
            'participation': 0.0,
            'reliability': 0.0,
            'raw_combined': 0.0,
            'final_normalized': DEFAULT_SCORE
        }


def apply_score_smoothing(
    new_score: int,
    previous_score: Optional[int] = None,
    alpha: float = EMA_ALPHA
) -> int:
    """
    Apply exponential moving average smoothing to reduce score volatility
    
    Args:
        new_score: Newly calculated score
        previous_score: Previously stored score
        alpha: Smoothing factor [0-1], higher = less smoothing
        
    Returns:
        Smoothed score
    """
    if previous_score is None:
        return new_score
    
    # Apply EMA smoothing
    smoothed = alpha * new_score + (1 - alpha) * previous_score
    smoothed_int = int(round(smoothed))
    
    # Limit maximum single-update change
    max_change = min(MAX_SCORE_CHANGE, max(MIN_SCORE_CHANGE, abs(new_score - previous_score) * 0.5))
    
    if abs(smoothed_int - previous_score) > max_change:
        if smoothed_int > previous_score:
            smoothed_int = previous_score + max_change
        else:
            smoothed_int = previous_score - max_change
    
    # Apply minimum change threshold
    if abs(smoothed_int - previous_score) < MIN_SCORE_CHANGE:
        return previous_score
    
    return max(MIN_SCORE, min(MAX_SCORE, smoothed_int))
