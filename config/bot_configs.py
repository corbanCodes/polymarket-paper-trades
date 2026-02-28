"""
Bot Configurations - All paper trading bot strategies for Polymarket

Series 1: Fixed-Minute Bots (13 bots)
    - Each focuses on ONE specific minute
    - Only bets when edge is positive at their minute

Series 2: Dynamic Edge Bots (34 bots)
    - Wait for X minutes, then bet when edge >= threshold
    - Multiple variations with different thresholds

Series 3: Sentiment Bots (64 bots)
    - Bet with the crowd (direction market implies)
    - Test various entry criteria based on market odds
"""

try:
    from persistence_odds import PERSISTENCE_BY_MINUTE
except ImportError:
    from config.persistence_odds import PERSISTENCE_BY_MINUTE

# =============================================================================
# FEE CONFIGURATION - Polymarket has MUCH lower fees than Kalshi!
# =============================================================================

POLYMARKET_FEE_RATE = 0.02  # ~2% on crypto markets (vs Kalshi's 7%)

def polymarket_fee(price_cents):
    """Calculate Polymarket fee for a given price"""
    if price_cents <= 0 or price_cents >= 100:
        return 0
    p = price_cents / 100
    return POLYMARKET_FEE_RATE * p * (1 - p) * 100  # Returns fee in cents

# =============================================================================
# SERIES 1: FIXED-MINUTE BOTS
# =============================================================================

FIXED_MINUTE_BOTS = {}
for minute in range(1, 14):  # Minutes 1-13
    mins_left, persistence, max_losses = PERSISTENCE_BY_MINUTE[minute]
    FIXED_MINUTE_BOTS[f"fixed_min_{minute}"] = {
        "name": f"Fixed Minute {minute}",
        "description": f"Only bets at minute {minute} ({mins_left} min left). Persistence: {persistence*100:.1f}%",
        "target_minute": minute,
        "mins_left": mins_left,
        "true_probability": persistence,
        "max_price_cents": int(persistence * 100 * 0.95),
        "min_edge": 0.03,
        "starting_bankroll": 1000,
        "bet_size": 10,
    }

# =============================================================================
# SERIES 2: DYNAMIC EDGE BOTS
# =============================================================================

DYNAMIC_EDGE_BOTS = {}

for wait_minutes in [2, 3, 4, 5]:
    for edge_pct in [5, 10, 12, 15, 20, 25, 30, 40]:
        edge = edge_pct / 100
        bot_id = f"dynamic_wait{wait_minutes}_edge{edge_pct}"
        DYNAMIC_EDGE_BOTS[bot_id] = {
            "name": f"Dynamic Wait {wait_minutes}m, Edge {edge_pct}%",
            "description": f"Waits {wait_minutes} min, then enters when edge >= {edge_pct}%",
            "min_wait_minutes": wait_minutes,
            "min_edge": edge,
            "starting_bankroll": 1000,
            "bet_size": 10,
        }

# Scaled betting bots
DYNAMIC_EDGE_BOTS["dynamic_scaled_wait3"] = {
    "name": "Dynamic Scaled (Wait 3m)",
    "description": "Waits 3 min, scales bet size with edge (more edge = bigger bet)",
    "min_wait_minutes": 3,
    "min_edge": 0.05,
    "scale_with_edge": True,
    "base_bet_size": 10,
    "max_bet_size": 50,
    "starting_bankroll": 1000,
}

DYNAMIC_EDGE_BOTS["dynamic_scaled_wait5"] = {
    "name": "Dynamic Scaled (Wait 5m)",
    "description": "Waits 5 min, scales bet size with edge",
    "min_wait_minutes": 5,
    "min_edge": 0.10,
    "scale_with_edge": True,
    "base_bet_size": 10,
    "max_bet_size": 50,
    "starting_bankroll": 1000,
}

# =============================================================================
# SERIES 3: SENTIMENT BOTS
# =============================================================================

SENTIMENT_BOTS = {}

for odds_threshold in [55, 60, 65, 70, 75, 80, 85, 90, 95]:
    for min_wait in [0, 1, 2, 3, 5, 7, 10]:
        bot_id = f"sentiment_odds{odds_threshold}_wait{min_wait}"
        SENTIMENT_BOTS[bot_id] = {
            "name": f"Sentiment {odds_threshold}c (Wait {min_wait}m)",
            "description": f"Bets WITH the favorite when YES/NO hits {odds_threshold}c, after {min_wait} min",
            "odds_threshold": odds_threshold,
            "min_wait_minutes": min_wait,
            "starting_bankroll": 1000,
            "bet_size": 10,
        }

SENTIMENT_BOTS["sentiment_always_favorite"] = {
    "name": "Always Favorite",
    "description": "Always bets the favored side regardless of time or odds",
    "odds_threshold": 51,
    "min_wait_minutes": 0,
    "starting_bankroll": 1000,
    "bet_size": 10,
}

# =============================================================================
# ALL BOTS COMBINED
# =============================================================================

ALL_BOTS = {
    **{f"s1_{k}": v for k, v in FIXED_MINUTE_BOTS.items()},
    **{f"s2_{k}": v for k, v in DYNAMIC_EDGE_BOTS.items()},
    **{f"s3_{k}": v for k, v in SENTIMENT_BOTS.items()},
}

def get_bot_count():
    return len(ALL_BOTS)

if __name__ == "__main__":
    print(f"Series 1 (Fixed-Minute): {len(FIXED_MINUTE_BOTS)} bots")
    print(f"Series 2 (Dynamic Edge): {len(DYNAMIC_EDGE_BOTS)} bots")
    print(f"Series 3 (Sentiment): {len(SENTIMENT_BOTS)} bots")
    print(f"TOTAL: {get_bot_count()} bots")
