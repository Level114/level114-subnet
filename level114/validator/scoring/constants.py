"""
Level114 Subnet - Scoring Constants

Configuration constants for the Level114 subnet validator scoring system.
Defines thresholds, weights, caps, and targets for scoring Minecraft servers.
"""

import os
from typing import Set

# =============================================================================
# PERFORMANCE TARGETS & CAPS
# =============================================================================

# TPS (Ticks Per Second) targets
IDEAL_TPS = 20.0                    # Minecraft ideal TPS
MIN_TPS_THRESHOLD = 5.0             # Below this is considered broken
MAX_TPS_BONUS = 20.0                # Cap TPS bonus at perfect performance

# Network latency thresholds (removed)

# Uptime and reliability
MAX_UPTIME_BONUS_H = 72.0           # Cap reliability bonus to 72h window

# Player activity
MAX_PLAYERS_WEIGHT = 200            # Beyond 200 concurrent adds no extra benefit
MIN_PLAYERS_FOR_BONUS = 5           # Minimum players for activity bonus
OPTIMAL_PLAYER_RATIO_MIN = 0.2      # 20% occupancy minimum for optimal score
OPTIMAL_PLAYER_RATIO_MAX = 0.8      # 80% occupancy maximum for optimal score

# Memory and resource limits (removed)

# =============================================================================
# REQUIRED COMPONENTS
# =============================================================================

# Required plugins for compliance
REQUIRED_PLUGINS: Set[str] = {
    "Level114",
    "LuckPerms",
}

# Optional plugins that provide bonuses
BONUS_PLUGINS: Set[str] = {
    "ViaVersion",
    "ViaBackwards",
    "ViaRewind",
}

# Plugin scoring weights (consolidated into logic)

# =============================================================================
# SCORING WEIGHTS
# =============================================================================

# Primary component weights (must sum to 1.0)
W_INFRA = 0.40                      # Infrastructure (TPS, latency, resources)
W_PART = 0.35                       # Participation (players, compliance, registration)
W_RELY = 0.25                       # Reliability (uptime, stability, recovery)

# Infrastructure sub-weights (TPS-only)
W_INFRA_TPS = 1.0                   # TPS performance only

# Participation sub-weights (no registration)
# Keep active players at ~5% of the overall score by shrinking their share of the
# participation component.
W_PART_COMPLIANCE = 0.8571428571428571  # Plugin compliance
W_PART_PLAYERS = 0.14285714285714285    # Player activity (~5% overall weight)

# Reliability sub-weights (must sum to 1.0)
W_RELY_UPTIME = 0.50                # Uptime trends
W_RELY_STABILITY = 0.35             # TPS stability
W_RELY_RECOVERY = 0.15              # Recovery after issues

# =============================================================================
# ANTI-CHEAT & SANITY LIMITS
# =============================================================================

# Score penalties (integrity removed)

# =============================================================================
# SCORE NORMALIZATION
# =============================================================================

# Output score range
MIN_SCORE = 0                       # Minimum possible score
MAX_SCORE = 1000                    # Maximum possible score
DEFAULT_SCORE = 100                 # Default score for new miners

# Score smoothing
EMA_ALPHA = 0.2                     # Exponential moving average alpha
MIN_SCORE_CHANGE = 1                # Minimum score change to apply
MAX_SCORE_CHANGE = 200              # Maximum single-update score change

# Quality thresholds for classification
EXCELLENT_SCORE_THRESHOLD = 850     # Scores above this are "excellent"
GOOD_SCORE_THRESHOLD = 650          # Scores above this are "good"
POOR_SCORE_THRESHOLD = 300          # Scores below this are "poor"

# =============================================================================
# HISTORY AND SAMPLING
# =============================================================================

# Report history management
MAX_REPORT_HISTORY = 60             # Maximum reports to keep per server
MIN_REPORTS_FOR_RELIABILITY = 5    # Minimum reports needed for reliability scoring

# TPS stability calculation
TPS_STABILITY_WINDOW = 20           # Number of samples for stability calculation
MAX_TPS_COEFFICIENT_OF_VARIATION = 0.3  # Maximum CV for perfect stability score

# Recovery detection
RECOVERY_TPS_THRESHOLD = 18.0       # TPS threshold for "recovered" state
RECOVERY_SAMPLE_COUNT = 10          # Consecutive samples needed for recovery
MAX_RECOVERY_TIME_MINUTES = 30     # Maximum time to recover for full score

# =============================================================================
# ENVIRONMENT OVERRIDES
# =============================================================================

# Allow environment variables to override key constants
IDEAL_TPS = float(os.getenv("LEVEL114_IDEAL_TPS", IDEAL_TPS))
MAX_PLAYERS_WEIGHT = int(os.getenv("LEVEL114_MAX_PLAYERS_WEIGHT", MAX_PLAYERS_WEIGHT))

W_INFRA = float(os.getenv("LEVEL114_W_INFRA", W_INFRA))
W_PART = float(os.getenv("LEVEL114_W_PART", W_PART))
W_RELY = float(os.getenv("LEVEL114_W_RELY", W_RELY))

EMA_ALPHA = float(os.getenv("LEVEL114_EMA_ALPHA", EMA_ALPHA))
MAX_SCORE = int(os.getenv("LEVEL114_MAX_SCORE", MAX_SCORE))

# Debug and development flags
DEBUG_SCORING = os.getenv("LEVEL114_DEBUG_SCORING", "false").lower() == "true"

# =============================================================================
# VALIDATION
# =============================================================================

def validate_constants():
    """
    Validate that all constants are reasonable and consistent
    
    Raises:
        ValueError: If constants are invalid
    """
    # Check weights sum to 1.0
    total_weight = W_INFRA + W_PART + W_RELY
    if abs(total_weight - 1.0) > 0.001:
        raise ValueError(f"Primary weights must sum to 1.0, got {total_weight}")
    
    infra_total = W_INFRA_TPS
    if abs(infra_total - 1.0) > 0.001:
        raise ValueError(f"Infrastructure weights must sum to 1.0, got {infra_total}")
    
    part_total = W_PART_COMPLIANCE + W_PART_PLAYERS 
    if abs(part_total - 1.0) > 0.001:
        raise ValueError(f"Participation weights must sum to 1.0, got {part_total}")
    
    rely_total = W_RELY_UPTIME + W_RELY_STABILITY + W_RELY_RECOVERY
    if abs(rely_total - 1.0) > 0.001:
        raise ValueError(f"Reliability weights must sum to 1.0, got {rely_total}")
    
    # Check reasonable ranges
    if not (0 < IDEAL_TPS <= 30):
        raise ValueError(f"IDEAL_TPS must be in (0, 30], got {IDEAL_TPS}")
    
    # Latency checks removed
    
    if not (0 < EMA_ALPHA <= 1):
        raise ValueError(f"EMA_ALPHA must be in (0, 1], got {EMA_ALPHA}")
    
    if MAX_SCORE <= MIN_SCORE:
        raise ValueError(f"MAX_SCORE ({MAX_SCORE}) must be > MIN_SCORE ({MIN_SCORE})")


# Validate constants on import
if __name__ != "__main__":
    validate_constants()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_score_classification(score: int) -> str:
    """
    Classify a score into performance categories
    
    Args:
        score: Numeric score to classify
        
    Returns:
        Performance classification string
    """
    if score >= EXCELLENT_SCORE_THRESHOLD:
        return "excellent"
    elif score >= GOOD_SCORE_THRESHOLD:
        return "good"  
    elif score >= POOR_SCORE_THRESHOLD:
        return "average"
    else:
        return "poor"


def get_constants_summary() -> dict:
    """
    Get a summary of all scoring constants for debugging
    
    Returns:
        Dictionary with constant categories
    """
    return {
        "performance_targets": {
            "ideal_tps": IDEAL_TPS,
            "max_uptime_bonus_h": MAX_UPTIME_BONUS_H,
            "max_players_weight": MAX_PLAYERS_WEIGHT
        },
        "weights": {
            "infrastructure": W_INFRA,
            "participation": W_PART,
            "reliability": W_RELY
        },
        "sub_weights": {
            "infra": {
                "tps": W_INFRA_TPS
            },
            "part": {
                "compliance": W_PART_COMPLIANCE,
                "players": W_PART_PLAYERS
            },
            "rely": {
                "uptime": W_RELY_UPTIME,
                "stability": W_RELY_STABILITY,
                "recovery": W_RELY_RECOVERY
            }
        },
        "score_range": {
            "min": MIN_SCORE,
            "max": MAX_SCORE,
            "thresholds": {
                "excellent": EXCELLENT_SCORE_THRESHOLD,
                "good": GOOD_SCORE_THRESHOLD,
                "poor": POOR_SCORE_THRESHOLD
            }
        },
        "required_plugins": list(REQUIRED_PLUGINS),
        "bonus_plugins": list(BONUS_PLUGINS)
    }
