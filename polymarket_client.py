"""
Polymarket API Client

Handles all Polymarket Gamma API interactions for BTC 15-minute markets.
No authentication needed for read-only market data.
"""

import time
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List

# =============================================================================
# API ENDPOINTS
# =============================================================================

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# BTC price from Kraken (same as Kalshi version for consistency)
KRAKEN_API = "https://api.kraken.com/0/public/Ticker"

# =============================================================================
# BTC PRICE
# =============================================================================

def get_btc_price() -> Optional[float]:
    """Get current BTC price from Kraken"""
    try:
        resp = requests.get(KRAKEN_API, params={"pair": "XBTUSD"}, timeout=5)
        data = resp.json()
        return float(data['result']['XXBTZUSD']['c'][0])
    except Exception as e:
        print(f"Kraken price error: {e}")
        return None

# =============================================================================
# POLYMARKET 15-MINUTE MARKET DISCOVERY
# =============================================================================

def get_current_window_timestamp() -> int:
    """
    Get the Unix timestamp for the current 15-minute window.
    Polymarket uses timestamps rounded to 15-minute intervals.
    """
    now = datetime.now(timezone.utc)
    # Round down to nearest 15-minute interval
    minute = (now.minute // 15) * 15
    window_start = now.replace(minute=minute, second=0, microsecond=0)
    return int(window_start.timestamp())

def get_next_window_timestamp() -> int:
    """Get the Unix timestamp for the next 15-minute window."""
    current = get_current_window_timestamp()
    return current + (15 * 60)  # Add 15 minutes

def generate_market_slug(timestamp: int) -> str:
    """Generate the Polymarket market slug for a BTC 15-min window."""
    return f"btc-updown-15m-{timestamp}"

def get_market_by_slug(slug: str) -> Optional[Dict]:
    """Fetch market data from Polymarket Gamma API by slug."""
    try:
        url = f"{GAMMA_API}/markets"
        params = {"slug": slug}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        if markets and len(markets) > 0:
            return markets[0]
        return None
    except Exception as e:
        print(f"Gamma API error: {e}")
        return None

def get_active_btc_markets() -> List[Dict]:
    """Get all active BTC 15-minute markets."""
    try:
        url = f"{GAMMA_API}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "tag": "crypto",
            "limit": 50
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        markets = resp.json()

        # Filter for BTC 15-min markets
        btc_15m = [m for m in markets if 'btc' in m.get('slug', '').lower()
                   and '15m' in m.get('slug', '').lower()]
        return btc_15m
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def get_current_btc_15m_market() -> Optional[Dict]:
    """
    Find the current active BTC 15-minute market.
    Tries current window timestamp first, then searches active markets.
    """
    # Try current window
    current_ts = get_current_window_timestamp()
    slug = generate_market_slug(current_ts)
    print(f"[API] Trying slug: {slug}", flush=True)
    market = get_market_by_slug(slug)
    if market:
        print(f"[API] Found market by current slug", flush=True)
        return market

    # Try next window (in case current just ended)
    next_ts = get_next_window_timestamp()
    slug = generate_market_slug(next_ts)
    print(f"[API] Trying next slug: {slug}", flush=True)
    market = get_market_by_slug(slug)
    if market:
        print(f"[API] Found market by next slug", flush=True)
        return market

    # Fallback: search active markets
    print(f"[API] Searching active BTC markets...", flush=True)
    markets = get_active_btc_markets()
    print(f"[API] Found {len(markets)} active BTC 15m markets", flush=True)
    if markets:
        # Return the one ending soonest
        return sorted(markets, key=lambda m: m.get('endDate', ''))[0]

    return None

# =============================================================================
# MARKET DATA PARSING
# =============================================================================

def parse_market_data(market: Dict) -> Optional[Dict]:
    """
    Parse raw Polymarket market data into standardized format.

    Polymarket BTC 15-min markets use UP/DOWN (not YES/NO):
    - UP = BTC finishes >= opening price (maps to YES in our system)
    - DOWN = BTC finishes < opening price (maps to NO in our system)

    Note: The "strike price" (price to beat) is the BTC price at window start.
    The API doesn't provide this - we track it ourselves in the worker.

    Returns dict with:
        - market_id: str
        - slug: str
        - question: str
        - strike_price: float (0 - tracked by worker)
        - end_time: str (ISO format)
        - mins_left: float
        - up_price: int (cents) - maps to YES
        - down_price: int (cents) - maps to NO
        - up_token_id: str
        - down_token_id: str
    """
    if not market:
        return None

    try:
        # Extract basic info
        market_id = market.get('id', '')
        slug = market.get('slug', '')
        question = market.get('question', '')
        end_time = market.get('endDate', '')

        # Strike price is NOT in the API - it's the BTC price at window start
        # We'll track this in the worker when we first see a new window
        strike = 0.0

        # Calculate minutes left
        mins_left = None
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                mins_left = (end_dt - now).total_seconds() / 60
            except:
                pass

        # Get prices - Polymarket returns [Up, Down] in outcomePrices
        up_price = 50  # Default
        down_price = 50

        outcome_prices = market.get('outcomePrices', [])
        if outcome_prices:
            # Handle both string "[\"0.5\", \"0.5\"]" and list formats
            if isinstance(outcome_prices, str):
                import json
                outcome_prices = json.loads(outcome_prices)
            if len(outcome_prices) >= 2:
                try:
                    up_price = int(float(outcome_prices[0]) * 100)
                    down_price = int(float(outcome_prices[1]) * 100)
                except:
                    pass

        # Get token IDs for trading - [Up token, Down token]
        tokens = market.get('clobTokenIds', [])
        if isinstance(tokens, str):
            import json
            tokens = json.loads(tokens)
        up_token = tokens[0] if len(tokens) > 0 else None
        down_token = tokens[1] if len(tokens) > 1 else None

        return {
            'market_id': market_id,
            'slug': slug,
            'question': question,
            'strike_price': strike,  # Will be set by worker
            'end_time': end_time,
            'mins_left': mins_left,
            # Map UP/DOWN to YES/NO for compatibility with bot logic
            'yes_price': up_price,    # UP = YES (BTC above strike)
            'no_price': down_price,   # DOWN = NO (BTC below strike)
            'yes_token_id': up_token,
            'no_token_id': down_token,
        }

    except Exception as e:
        print(f"Error parsing market: {e}", flush=True)
        return None

def get_orderbook_prices(token_id: str) -> Optional[Dict]:
    """
    Get best bid/ask from CLOB orderbook for a token.
    This gives more accurate prices than the Gamma API.
    """
    if not token_id:
        return None

    try:
        url = f"{CLOB_API}/book"
        params = {"token_id": token_id}
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        book = resp.json()

        bids = book.get('bids', [])
        asks = book.get('asks', [])

        best_bid = int(float(bids[0]['price']) * 100) if bids else 0
        best_ask = int(float(asks[0]['price']) * 100) if asks else 100

        return {
            'bid': best_bid,
            'ask': best_ask,
            'spread': best_ask - best_bid
        }
    except Exception as e:
        # Silently fail - orderbook might not be available
        return None

# =============================================================================
# COMBINED DATA FETCH
# =============================================================================

def get_market_tick() -> Optional[Dict]:
    """
    Get all current market data in one call.
    Returns standardized tick format for the worker.

    Note: strike_price will be 0 from API - worker tracks opening price.
    UP/DOWN prices are mapped to yes/no for bot compatibility.
    """
    # Get market
    print("[API] Searching for BTC 15-min market...", flush=True)
    market = get_current_btc_15m_market()
    print(f"[API] Market found: {market is not None}", flush=True)
    if not market:
        return None

    parsed = parse_market_data(market)
    print(f"[API] Parsed: {parsed is not None}", flush=True)
    if not parsed:
        return None

    # Get BTC price
    print("[API] Fetching BTC price...", flush=True)
    btc_price = get_btc_price()
    print(f"[API] BTC price: {btc_price}", flush=True)
    if not btc_price:
        return None

    # Try to get orderbook prices for more accuracy
    # yes_token = UP token, no_token = DOWN token
    print(f"[API] Fetching orderbook for UP token...", flush=True)
    up_book = get_orderbook_prices(parsed.get('yes_token_id'))
    print(f"[API] UP orderbook: {up_book}", flush=True)
    print(f"[API] Fetching orderbook for DOWN token...", flush=True)
    down_book = get_orderbook_prices(parsed.get('no_token_id'))
    print(f"[API] DOWN orderbook: {down_book}", flush=True)

    # Use orderbook if available, else Gamma API prices
    if up_book:
        yes_ask = up_book['ask']  # UP ask = YES ask
        yes_bid = up_book['bid']
    else:
        yes_ask = parsed['yes_price']
        yes_bid = max(0, parsed['yes_price'] - 2)

    if down_book:
        no_ask = down_book['ask']  # DOWN ask = NO ask
        no_bid = down_book['bid']
    else:
        no_ask = parsed['no_price']
        no_bid = max(0, parsed['no_price'] - 2)

    # Build tick
    # Note: strike_price=0 here, worker will set it when window starts
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'window_id': parsed['slug'],
        'market_id': parsed['market_id'],
        'question': parsed['question'],
        'strike_price': 0,  # Worker tracks this as opening price
        'mins_left': parsed['mins_left'],
        'btc_price': btc_price,
        # UP maps to YES (BTC above opening = UP wins)
        'yes_ask': yes_ask,
        'yes_bid': yes_bid,
        # DOWN maps to NO (BTC below opening = DOWN wins)
        'no_ask': no_ask,
        'no_bid': no_bid,
        'yes_token_id': parsed.get('yes_token_id'),
        'no_token_id': parsed.get('no_token_id'),
    }

# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("Testing Polymarket Client...")
    print(f"Current window timestamp: {get_current_window_timestamp()}")
    print(f"Current slug: {generate_market_slug(get_current_window_timestamp())}")

    print("\nFetching current market...")
    tick = get_market_tick()
    if tick:
        print(f"Window: {tick['window_id']}")
        print(f"Strike: ${tick['strike_price']:,.2f}")
        print(f"BTC: ${tick['btc_price']:,.2f}")
        print(f"Mins left: {tick['mins_left']:.1f}")
        print(f"YES: {tick['yes_ask']}c / NO: {tick['no_ask']}c")
    else:
        print("No active market found")
