"""
Persistence Odds Configuration

Based on 5 years of BTC data (137,206 15-minute windows).
If BTC is above/below strike at minute X, what's the probability it stays there?

This is the CORE edge - these are our "true probabilities" vs market prices.
"""

# Data structure: minute -> (mins_left, persistence_rate, max_consecutive_losses)
PERSISTENCE_BY_MINUTE = {
    0:  (14, 0.560, 15),   # 56.0% - too early, barely better than coin flip
    1:  (13, 0.626, 12),   # 62.6% - starting to see persistence
    2:  (12, 0.684, 10),   # 68.4% - solid edge emerging
    3:  (11, 0.732, 9),    # 73.2% - good persistence
    4:  (10, 0.771, 8),    # 77.1% - strong
    5:  (9,  0.804, 7),    # 80.4% - very strong
    6:  (8,  0.832, 6),    # 83.2% - excellent
    7:  (7,  0.856, 6),    # 85.6% - excellent
    8:  (6,  0.877, 5),    # 87.7% - very high
    9:  (5,  0.895, 5),    # 89.5% - very high
    10: (4,  0.912, 4),    # 91.2% - extremely high
    11: (3,  0.927, 4),    # 92.7% - extremely high
    12: (2,  0.941, 3),    # 94.1% - near-certain
    13: (1,  0.954, 3),    # 95.4% - near-certain
    14: (0,  0.968, 2),    # 96.8% - basically locked in
}

def get_persistence_rate(minute: int) -> float:
    """Get the persistence rate for a given minute"""
    if minute in PERSISTENCE_BY_MINUTE:
        return PERSISTENCE_BY_MINUTE[minute][1]
    return None

def get_mins_left(minute: int) -> int:
    """Get minutes left in window at a given minute"""
    if minute in PERSISTENCE_BY_MINUTE:
        return PERSISTENCE_BY_MINUTE[minute][0]
    return None

def calculate_edge(minute: int, market_price_cents: int) -> float:
    """
    Calculate edge: true_probability - implied_probability

    Args:
        minute: Current minute in the window (0-14)
        market_price_cents: Current YES price in cents (0-100)

    Returns:
        Edge as decimal (e.g., 0.15 = 15% edge)
    """
    true_prob = get_persistence_rate(minute)
    if true_prob is None:
        return 0

    implied_prob = market_price_cents / 100
    return true_prob - implied_prob
