#!/usr/bin/env python3
"""
Polymarket Live Multi-Bot Paper Trading Worker

Runs ALL bots simultaneously against live Polymarket data.
Logs second-by-second market data for analysis.

Usage:
    python live_worker.py
"""

import os
import sys
import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Add config to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'config'))
from persistence_odds import get_persistence_rate, calculate_edge
from bot_configs import (
    ALL_BOTS,
    FIXED_MINUTE_BOTS,
    DYNAMIC_EDGE_BOTS,
    SENTIMENT_BOTS,
    polymarket_fee,
    get_bot_count,
)
from polymarket_client import get_market_tick, get_btc_price

# =============================================================================
# CONFIGURATION
# =============================================================================

STATE_FILE = 'bot_state.json'
TICK_LOG_FILE = 'tick_log.jsonl'  # Second-by-second logging
STATUS_LOG_INTERVAL = 30

# =============================================================================
# TICK LOGGER - Second by second market data
# =============================================================================

class TickLogger:
    """Log every tick for analysis"""

    def __init__(self, filename: str = TICK_LOG_FILE):
        self.filename = filename
        self.tick_count = 0

    def log(self, tick: dict):
        """Append tick to log file"""
        self.tick_count += 1
        try:
            with open(self.filename, 'a') as f:
                f.write(json.dumps(tick) + '\n')
        except Exception as e:
            print(f"Tick log error: {e}")

# =============================================================================
# BOT STATE
# =============================================================================

class LiveBotState:
    """Track live state for a single bot"""

    def __init__(self, bot_id: str, config: dict):
        self.bot_id = bot_id
        self.config = config
        self.bankroll = config.get('starting_bankroll', 1000)
        self.initial_bankroll = self.bankroll
        self.trades: List[dict] = []
        self.wins = 0
        self.losses = 0
        self.total_wagered = 0
        self.total_fees = 0
        self.current_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.pending_trade: Optional[dict] = None
        self.traded_windows = set()
        self.skipped_windows: List[dict] = []
        self.last_skip_reason: str = None

    def get_series(self) -> str:
        if self.bot_id.startswith('s1_'):
            return 'fixed_minute'
        elif self.bot_id.startswith('s2_'):
            return 'dynamic_edge'
        elif self.bot_id.startswith('s3_'):
            return 'sentiment'
        return 'unknown'

    def get_stats(self) -> dict:
        total_trades = self.wins + self.losses
        return {
            'bot_id': self.bot_id,
            'name': self.config.get('name', self.bot_id),
            'series': self.get_series(),
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': self.wins / total_trades * 100 if total_trades > 0 else 0,
            'bankroll': self.bankroll,
            'total_profit': self.bankroll - self.initial_bankroll,
            'roi': (self.bankroll - self.initial_bankroll) / self.initial_bankroll * 100,
            'total_wagered': self.total_wagered,
            'total_fees': self.total_fees,
            'current_streak': self.current_streak,
            'max_win_streak': self.max_win_streak,
            'max_loss_streak': self.max_loss_streak,
            'pending': bool(self.pending_trade),
        }

# =============================================================================
# BOT LOGIC (same as Kalshi version)
# =============================================================================

def check_fixed_minute_entry(bot: LiveBotState, tick: dict) -> Optional[dict]:
    """Check if fixed-minute bot should enter"""
    window_id = tick['window_id']

    if bot.pending_trade:
        bot.last_skip_reason = "Already has pending trade"
        return None

    if window_id in bot.traded_windows:
        bot.last_skip_reason = "Already traded this window"
        return None

    target_minute = bot.config['target_minute']
    mins_left = tick['mins_left']
    target_mins_left = 14 - target_minute

    if not (target_mins_left - 0.5 <= mins_left <= target_mins_left + 0.5):
        current_min = int(14 - mins_left)
        bot.last_skip_reason = f"Waiting for minute {target_minute} (currently min {current_min})"
        return None

    btc_price = tick['btc_price']
    strike = tick['strike_price']
    is_above = btc_price > strike

    if is_above:
        price = tick['yes_ask']
        direction = 'YES'
    else:
        price = tick['no_ask']
        direction = 'NO'

    if price == 0:
        bot.last_skip_reason = f"No market price available ({direction} ask = 0)"
        return None

    if price >= 100:
        bot.last_skip_reason = f"Price too high ({direction} @ {price}c = 100%)"
        return None

    true_prob = bot.config['true_probability']
    implied_prob = price / 100
    edge = true_prob - implied_prob

    min_edge = bot.config.get('min_edge', 0)
    if edge < min_edge:
        bot.last_skip_reason = f"Edge too low ({edge*100:.1f}% < {min_edge*100:.1f}% min)"
        return None

    max_price = bot.config.get('max_price_cents', 100)
    if price > max_price:
        bot.last_skip_reason = f"Price exceeds max ({price}c > {max_price}c)"
        return None

    bot.last_skip_reason = None
    return {'direction': direction, 'price': price, 'edge': edge}


def check_dynamic_edge_entry(bot: LiveBotState, tick: dict) -> Optional[dict]:
    """Check if dynamic edge bot should enter"""
    window_id = tick['window_id']

    if bot.pending_trade:
        bot.last_skip_reason = "Already has pending trade"
        return None

    if window_id in bot.traded_windows:
        bot.last_skip_reason = "Already traded this window"
        return None

    mins_left = tick['mins_left']
    min_wait = bot.config['min_wait_minutes']
    current_minute = int(14 - mins_left)

    if mins_left > (14 - min_wait):
        bot.last_skip_reason = f"Waiting {min_wait} min before entry (currently min {current_minute})"
        return None
    if mins_left < 1:
        bot.last_skip_reason = "Window ending (<1 min left)"
        return None

    if current_minute < 1 or current_minute > 13:
        bot.last_skip_reason = f"Invalid minute ({current_minute})"
        return None

    true_prob = get_persistence_rate(current_minute)
    if true_prob is None:
        bot.last_skip_reason = f"No persistence data for minute {current_minute}"
        return None

    btc_price = tick['btc_price']
    strike = tick['strike_price']
    is_above = btc_price > strike

    if is_above:
        price = tick['yes_ask']
        direction = 'YES'
    else:
        price = tick['no_ask']
        direction = 'NO'

    if price == 0:
        bot.last_skip_reason = f"No market price ({direction} ask = 0)"
        return None

    if price >= 100:
        bot.last_skip_reason = f"Price at 100% ({direction} @ {price}c)"
        return None

    implied_prob = price / 100
    edge = true_prob - implied_prob

    min_edge = bot.config['min_edge']
    if edge < min_edge:
        bot.last_skip_reason = f"Edge {edge*100:.1f}% < {min_edge*100:.1f}% threshold"
        return None

    bot.last_skip_reason = None
    return {'direction': direction, 'price': price, 'edge': edge}


def check_sentiment_entry(bot: LiveBotState, tick: dict) -> Optional[dict]:
    """Check if sentiment bot should enter"""
    window_id = tick['window_id']

    if bot.pending_trade:
        bot.last_skip_reason = "Already has pending trade"
        return None

    if window_id in bot.traded_windows:
        bot.last_skip_reason = "Already traded this window"
        return None

    mins_left = tick['mins_left']
    min_wait = bot.config['min_wait_minutes']
    current_minute = int(14 - mins_left)

    if mins_left > (14 - min_wait):
        bot.last_skip_reason = f"Waiting {min_wait} min (currently min {current_minute})"
        return None
    if mins_left < 0.5:
        bot.last_skip_reason = "Window ending (<30 sec left)"
        return None

    yes_price = tick['yes_ask']
    no_price = tick['no_ask']

    if yes_price == 0 or no_price == 0:
        bot.last_skip_reason = f"No market prices (YES={yes_price}c, NO={no_price}c)"
        return None

    threshold = bot.config['odds_threshold']

    if yes_price >= threshold:
        direction = 'YES'
        price = yes_price
    elif no_price >= threshold:
        direction = 'NO'
        price = no_price
    else:
        bot.last_skip_reason = f"No strong sentiment (YES={yes_price}c, NO={no_price}c < {threshold}c threshold)"
        return None

    if price >= 100:
        bot.last_skip_reason = f"Price at 100% ({direction} @ {price}c)"
        return None

    bot.last_skip_reason = None
    return {'direction': direction, 'price': price, 'edge': None}


def execute_trade(bot: LiveBotState, tick: dict, trade_info: dict):
    """Execute a paper trade for a bot"""
    direction = trade_info['direction']
    price = trade_info['price']

    bet_size = bot.config.get('bet_size', 10)

    if bot.config.get('scale_with_edge') and trade_info.get('edge'):
        edge = trade_info['edge']
        base = bot.config.get('base_bet_size', 10)
        max_bet = bot.config.get('max_bet_size', 50)
        scale = min(1, max(0, (edge - 0.10) / 0.20))
        bet_size = base + scale * (max_bet - base)

    fee = polymarket_fee(price)
    contracts = int(bet_size / (price / 100))

    bot.pending_trade = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'window_id': tick['window_id'],
        'market_id': tick.get('market_id'),
        'strike': tick['strike_price'],
        'btc_price': tick['btc_price'],
        'mins_left': tick['mins_left'],
        'direction': direction,
        'entry_price': price,
        'contracts': contracts,
        'bet_size': bet_size,
        'fee': fee * contracts / 100,
        'edge': trade_info.get('edge'),
    }
    bot.total_wagered += bet_size
    bot.traded_windows.add(tick['window_id'])


def settle_trade(bot: LiveBotState, result: str):
    """Settle a bot's pending trade"""
    if not bot.pending_trade:
        return None

    trade = bot.pending_trade
    won = (trade['direction'].lower() == result.lower())

    if won:
        profit = trade['contracts'] - trade['bet_size'] - trade['fee']
        bot.wins += 1
        bot.current_streak = max(0, bot.current_streak) + 1
        bot.max_win_streak = max(bot.max_win_streak, bot.current_streak)
    else:
        profit = -trade['bet_size'] - trade['fee']
        bot.losses += 1
        bot.current_streak = min(0, bot.current_streak) - 1
        bot.max_loss_streak = max(bot.max_loss_streak, abs(bot.current_streak))

    bot.bankroll += profit
    bot.total_fees += trade['fee']

    trade['outcome'] = 'win' if won else 'loss'
    trade['profit'] = profit
    trade['bankroll_after'] = bot.bankroll
    bot.trades.append(trade)
    bot.pending_trade = None

    return trade

# =============================================================================
# MAIN WORKER
# =============================================================================

class LiveWorker:
    """Main worker that runs all bots"""

    def __init__(self):
        self.bots: Dict[str, LiveBotState] = {}
        self.tick_logger = TickLogger()
        self.current_window = None
        self.settled_windows = set()
        self.last_status_log = 0
        self.start_time = datetime.now()
        self.last_tick = None

        # Track opening prices for each window (strike = BTC price at window start)
        self.window_strikes: Dict[str, float] = {}

        # Initialize all bots
        for bot_id, config in ALL_BOTS.items():
            self.bots[bot_id] = LiveBotState(bot_id, config)

        print(f"Initialized {len(self.bots)} bots", flush=True)

    def save_state(self):
        """Save current state to JSON for web dashboard"""
        state = {
            'platform': 'polymarket',
            'last_update': datetime.now(timezone.utc).isoformat(),
            'windows_processed': len(self.settled_windows),
            'current_window': self.current_window,
            'runtime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'market': self.last_tick,
            'tick_count': self.tick_logger.tick_count,
            'bots': {}
        }

        for bot_id, bot in self.bots.items():
            stats = bot.get_stats()
            config = bot.config
            state['bots'][bot_id] = {
                'series': stats['series'],
                'name': config.get('name', bot_id),
                'description': config.get('description', ''),
                'trades': stats['total_trades'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'win_rate': stats['win_rate'],
                'bankroll': stats['bankroll'],
                'profit': stats['total_profit'],
                'roi': stats['roi'],
                'pending': stats['pending'],
                'total_wagered': stats['total_wagered'],
                'total_fees': stats['total_fees'],
                'current_streak': stats['current_streak'],
                'max_win_streak': stats['max_win_streak'],
                'max_loss_streak': stats['max_loss_streak'],
                'trade_history': bot.trades,
                'pending_trade': bot.pending_trade,
                'last_skip_reason': bot.last_skip_reason,
                'config': {
                    'target_minute': config.get('target_minute'),
                    'min_wait_minutes': config.get('min_wait_minutes'),
                    'min_edge': config.get('min_edge'),
                    'odds_threshold': config.get('odds_threshold'),
                    'true_probability': config.get('true_probability'),
                    'bet_size': config.get('bet_size', 10),
                    'scale_with_edge': config.get('scale_with_edge', False),
                },
            }

        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Failed to save state: {e}")

    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def process_tick(self, tick: dict):
        """Process a tick for all bots"""
        for bot_id, bot in self.bots.items():
            trade_info = None

            if bot_id.startswith('s1_'):
                trade_info = check_fixed_minute_entry(bot, tick)
            elif bot_id.startswith('s2_'):
                trade_info = check_dynamic_edge_entry(bot, tick)
            elif bot_id.startswith('s3_'):
                trade_info = check_sentiment_entry(bot, tick)

            if trade_info:
                execute_trade(bot, tick, trade_info)
                self.log(f"TRADE: {bot_id} -> {trade_info['direction']} @ {trade_info['price']}c")

    def settle_window(self, window_id: str, result: str):
        """Settle all pending trades for a window"""
        if window_id in self.settled_windows:
            return

        trades_settled = 0
        for bot_id, bot in self.bots.items():
            if bot.pending_trade and bot.pending_trade['window_id'] == window_id:
                trade = settle_trade(bot, result)
                if trade:
                    trades_settled += 1

        if trades_settled > 0:
            self.log(f"SETTLED: Window {window_id} -> {result.upper()} ({trades_settled} trades)")
            self.save_state()

        self.settled_windows.add(window_id)

    def print_status(self):
        """Print status summary"""
        now = time.time()
        if now - self.last_status_log < STATUS_LOG_INTERVAL:
            return
        self.last_status_log = now

        total_trades = sum(b.wins + b.losses for b in self.bots.values())
        total_wins = sum(b.wins for b in self.bots.values())
        pending = sum(1 for b in self.bots.values() if b.pending_trade)
        total_profit = sum(b.bankroll - b.initial_bankroll for b in self.bots.values())

        win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        runtime = datetime.now() - self.start_time

        self.log(f"STATUS: {total_trades} trades, {win_rate:.1f}% win rate, ${total_profit:.2f} P/L, {pending} pending | Ticks: {self.tick_logger.tick_count}")
        self.save_state()

    def determine_result(self, tick: dict) -> Optional[str]:
        """Determine if BTC is above or below strike at end"""
        if tick['mins_left'] > 0.5:
            return None  # Not settled yet

        btc = tick['btc_price']
        strike = tick['strike_price']

        if btc > strike:
            return 'YES'
        else:
            return 'NO'

    def run(self):
        """Main loop"""
        print("=" * 70)
        print("POLYMARKET LIVE MULTI-BOT PAPER TRADING")
        print("=" * 70)
        print(f"Bots: {len(self.bots)}")
        print(f"Tick logging: {TICK_LOG_FILE}")
        print("=" * 70 + "\n")

        last_window = None

        while True:
            try:
                # Get current market data
                print("[LOOP] Fetching market tick...", flush=True)
                tick = get_market_tick()
                print(f"[LOOP] Got tick: {tick is not None}", flush=True)
                if not tick:
                    self.log("No active market found, waiting...")
                    time.sleep(30)
                    continue

                # Validate tick data (strike_price=0 is OK, we set it below)
                if tick['mins_left'] is None:
                    self.log("Invalid tick: mins_left is None")
                    time.sleep(5)
                    continue

                print(f"[LOOP] mins_left={tick['mins_left']:.1f}, btc={tick['btc_price']:.2f}", flush=True)
                print(f"[LOOP] YES/UP ask={tick['yes_ask']}c, NO/DOWN ask={tick['no_ask']}c", flush=True)

                # Log every tick
                self.tick_logger.log(tick)
                self.last_tick = tick

                window_id = tick['window_id']
                print(f"[LOOP] window_id={window_id}, current_window={self.current_window}", flush=True)

                # Check if previous window needs settlement
                if last_window and last_window != window_id:
                    # Previous window ended - determine result
                    # We'd need to check final price, for now assume YES if BTC > strike
                    btc = tick['btc_price']
                    # Note: This is approximate - ideally we'd query settlement data
                    self.log(f"Window {last_window} ended, new window: {window_id}")

                # New window detection - track opening price as strike
                if window_id != self.current_window:
                    # Record the current BTC price as the strike for this window
                    # This is the "price to beat" shown on Polymarket UI
                    self.window_strikes[window_id] = tick['btc_price']
                    strike = tick['btc_price']

                    self.log(f"\n{'='*50}")
                    self.log(f"NEW WINDOW: {window_id}")
                    self.log(f"Opening Price (Strike): ${strike:,.2f}")
                    self.log(f"UP = BTC >= ${strike:,.2f} | DOWN = BTC < ${strike:,.2f}")
                    self.log(f"{'='*50}")
                    self.current_window = window_id

                # Use tracked strike price for this window
                if window_id in self.window_strikes:
                    tick['strike_price'] = self.window_strikes[window_id]
                else:
                    # Shouldn't happen, but fallback to current price
                    tick['strike_price'] = tick['btc_price']
                    self.window_strikes[window_id] = tick['btc_price']

                # Process tick for all bots
                self.process_tick(tick)

                # Check for settlement (last 30 seconds)
                if tick['mins_left'] < 0.5:
                    result = self.determine_result(tick)
                    if result:
                        self.settle_window(window_id, result)

                last_window = window_id

                # Print status periodically
                self.print_status()

                # Adaptive sleep - faster polling for Polymarket
                mins_left = tick['mins_left']
                if mins_left > 10:
                    time.sleep(5)
                elif mins_left > 5:
                    time.sleep(3)
                elif mins_left > 1:
                    time.sleep(2)
                else:
                    time.sleep(1)  # Second-by-second near end

            except KeyboardInterrupt:
                self.shutdown()
                break
            except Exception as e:
                self.log(f"ERROR: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(30)

    def shutdown(self):
        """Clean shutdown"""
        print("\n" + "=" * 70)
        print("SHUTTING DOWN")
        print("=" * 70)
        self.save_state()
        print(f"\nTotal ticks logged: {self.tick_logger.tick_count}")
        print(f"Results saved to {STATE_FILE}")

# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    worker = LiveWorker()
    worker.run()
