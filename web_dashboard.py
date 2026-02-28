#!/usr/bin/env python3
"""
Polymarket Paper Trading Web Dashboard

Mobile-responsive dashboard with:
- Live market info (BTC price, strike, time left)
- Bot performance charts
- Individual bot detail pages
- CSV/JSON export
"""

import os
import json
import csv
import io
from datetime import datetime, timezone
from functools import wraps
from types import SimpleNamespace

from flask import Flask, render_template_string, jsonify, request, Response, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'polymarket-paper-trading-secret-key')

STATE_FILE = 'bot_state.json'
TICK_LOG_FILE = 'tick_log.jsonl'
DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD', 'poly2024')

# =============================================================================
# AUTH
# =============================================================================

def check_auth(password):
    return password == DASHBOARD_PASSWORD

def authenticate():
    return Response(
        'Access denied. Please provide password.',
        401,
        {'WWW-Authenticate': 'Basic realm="Polymarket Dashboard"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# =============================================================================
# DATA
# =============================================================================

def load_state():
    """Load current bot state from JSON"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error loading state: {e}")
        return None

def get_tick_stats():
    """Get tick log statistics"""
    try:
        count = 0
        first_tick = None
        last_tick = None
        with open(TICK_LOG_FILE, 'r') as f:
            for line in f:
                count += 1
                if count == 1:
                    first_tick = json.loads(line)
                last_tick = json.loads(line)
        return {
            'count': count,
            'first': first_tick,
            'last': last_tick
        }
    except:
        return {'count': 0, 'first': None, 'last': None}

# =============================================================================
# TEMPLATES
# =============================================================================

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket Paper Trading Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-dark: #0a0a0f;
            --bg-card: #12121a;
            --bg-card-hover: #1a1a25;
            --border: #2a2a3a;
            --text-primary: #e0e0e0;
            --text-secondary: #888;
            --green: #00d26a;
            --red: #ff4757;
            --blue: #4a9eff;
            --purple: #a855f7;
            --orange: #ff9500;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 16px;
        }

        .header {
            text-align: center;
            margin-bottom: 24px;
            padding: 20px;
            background: linear-gradient(135deg, var(--purple), var(--blue));
            border-radius: 12px;
        }

        .header h1 {
            font-size: 1.8rem;
            margin-bottom: 8px;
        }

        .header .subtitle {
            opacity: 0.9;
            font-size: 0.95rem;
        }

        .market-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }

        .market-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            text-align: center;
        }

        .market-card .label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .market-card .value {
            font-size: 1.3rem;
            font-weight: 700;
        }

        .market-card .value.btc { color: var(--orange); }
        .market-card .value.strike { color: var(--blue); }
        .market-card .value.time { color: var(--purple); }
        .market-card .value.ticks { color: var(--green); }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            text-align: center;
        }

        .stat-card .number {
            font-size: 1.8rem;
            font-weight: 700;
        }

        .stat-card .label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .positive { color: var(--green); }
        .negative { color: var(--red); }

        .chart-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .chart-container h3 {
            margin-bottom: 16px;
            font-size: 1.1rem;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .section-header h2 {
            font-size: 1.3rem;
        }

        .btn-group {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            text-decoration: none;
            transition: all 0.2s;
        }

        .btn:hover {
            background: var(--bg-card-hover);
            border-color: var(--blue);
        }

        .btn.active {
            background: var(--blue);
            border-color: var(--blue);
        }

        .bot-table {
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 24px;
        }

        .bot-table th, .bot-table td {
            padding: 12px 10px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        .bot-table th {
            background: var(--bg-card-hover);
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-secondary);
        }

        .bot-table tr:hover {
            background: var(--bg-card-hover);
        }

        .bot-table tr {
            cursor: pointer;
        }

        .bot-name {
            font-weight: 600;
            color: var(--blue);
        }

        .status-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
        }

        .status-pending {
            background: rgba(255, 149, 0, 0.2);
            color: var(--orange);
        }

        .status-waiting {
            background: rgba(136, 136, 136, 0.2);
            color: var(--text-secondary);
        }

        .skip-reason {
            font-size: 0.75rem;
            color: var(--text-secondary);
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        @media (max-width: 768px) {
            body { padding: 10px; }
            .header h1 { font-size: 1.4rem; }
            .stat-card .number { font-size: 1.4rem; }
            .bot-table { font-size: 0.85rem; }
            .bot-table th, .bot-table td { padding: 10px 6px; }
            .hide-mobile { display: none; }
        }

        .footer {
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Polymarket Paper Trading</h1>
        <div class="subtitle">BTC 15-Minute Strategy | {{ bot_count }} Bots Active</div>
    </div>

    {% if market %}
    <div class="market-info">
        <div class="market-card">
            <div class="label">BTC Price</div>
            <div class="value btc">${{ "{:,.2f}".format(market.btc_price or 0) }}</div>
        </div>
        <div class="market-card">
            <div class="label">Strike</div>
            <div class="value strike">${{ "{:,.2f}".format(market.strike_price or 0) }}</div>
        </div>
        <div class="market-card">
            <div class="label">Time Left</div>
            <div class="value time">{{ "{:.1f}".format(market.mins_left or 0) }}m</div>
        </div>
        <div class="market-card">
            <div class="label">Ticks Logged</div>
            <div class="value ticks">{{ "{:,}".format(tick_count) }}</div>
        </div>
    </div>
    {% endif %}

    <div class="stats-grid">
        <div class="stat-card">
            <div class="number">{{ total_trades }}</div>
            <div class="label">Total Trades</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ "{:.1f}".format(win_rate) }}%</div>
            <div class="label">Win Rate</div>
        </div>
        <div class="stat-card">
            <div class="number {{ 'positive' if total_profit >= 0 else 'negative' }}">
                ${{ "{:,.2f}".format(total_profit) }}
            </div>
            <div class="label">Total P/L</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ pending_trades }}</div>
            <div class="label">Pending</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ windows_processed }}</div>
            <div class="label">Windows</div>
        </div>
    </div>

    <div class="chart-container">
        <h3>Cumulative Profit by Series</h3>
        <canvas id="profitChart" height="200"></canvas>
    </div>

    <div class="section-header">
        <h2>Bot Performance</h2>
        <div class="btn-group">
            <button class="btn active" onclick="filterBots('all')">All</button>
            <button class="btn" onclick="filterBots('s1')">Series 1</button>
            <button class="btn" onclick="filterBots('s2')">Series 2</button>
            <button class="btn" onclick="filterBots('s3')">Series 3</button>
            <a class="btn" href="/download/json">JSON</a>
            <a class="btn" href="/download/csv">CSV</a>
        </div>
    </div>

    <table class="bot-table" id="botTable">
        <thead>
            <tr>
                <th>Bot</th>
                <th>Trades</th>
                <th>Win%</th>
                <th>P/L</th>
                <th class="hide-mobile">ROI</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {% for bot in bots %}
            <tr data-series="{{ bot.bot_id[:2] }}" onclick="window.location='/bot/{{ bot.bot_id }}'">
                <td class="bot-name">{{ bot.name }}</td>
                <td>{{ bot.trades }}</td>
                <td>{{ "{:.0f}".format(bot.win_rate) }}%</td>
                <td class="{{ 'positive' if bot.profit >= 0 else 'negative' }}">
                    ${{ "{:.2f}".format(bot.profit) }}
                </td>
                <td class="hide-mobile {{ 'positive' if bot.roi >= 0 else 'negative' }}">
                    {{ "{:.1f}".format(bot.roi) }}%
                </td>
                <td>
                    {% if bot.pending %}
                        <span class="status-badge status-pending">PENDING</span>
                    {% elif bot.last_skip_reason %}
                        <span class="skip-reason" title="{{ bot.last_skip_reason }}">{{ bot.last_skip_reason[:30] }}...</span>
                    {% else %}
                        <span class="status-badge status-waiting">WAITING</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="footer">
        Last update: {{ last_update }} | Runtime: {{ runtime }}
    </div>

    <script>
        const seriesData = {{ series_data | safe }};

        new Chart(document.getElementById('profitChart'), {
            type: 'bar',
            data: {
                labels: ['Fixed Minute (S1)', 'Dynamic Edge (S2)', 'Sentiment (S3)'],
                datasets: [{
                    label: 'Profit ($)',
                    data: [seriesData.s1, seriesData.s2, seriesData.s3],
                    backgroundColor: [
                        seriesData.s1 >= 0 ? 'rgba(0, 210, 106, 0.7)' : 'rgba(255, 71, 87, 0.7)',
                        seriesData.s2 >= 0 ? 'rgba(0, 210, 106, 0.7)' : 'rgba(255, 71, 87, 0.7)',
                        seriesData.s3 >= 0 ? 'rgba(0, 210, 106, 0.7)' : 'rgba(255, 71, 87, 0.7)'
                    ],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: '#2a2a3a' }, ticks: { color: '#888' } },
                    x: { grid: { display: false }, ticks: { color: '#888' } }
                }
            }
        });

        function filterBots(series) {
            document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');

            document.querySelectorAll('#botTable tbody tr').forEach(row => {
                if (series === 'all' || row.dataset.series === series) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }

        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
"""

BOT_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ bot.name }} - Polymarket</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-dark: #0a0a0f;
            --bg-card: #12121a;
            --bg-card-hover: #1a1a25;
            --border: #2a2a3a;
            --text-primary: #e0e0e0;
            --text-secondary: #888;
            --green: #00d26a;
            --red: #ff4757;
            --blue: #4a9eff;
            --purple: #a855f7;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 16px;
        }

        .back-link {
            display: inline-block;
            color: var(--blue);
            text-decoration: none;
            margin-bottom: 16px;
            font-size: 0.9rem;
        }

        .header {
            margin-bottom: 24px;
        }

        .header h1 {
            font-size: 1.6rem;
            margin-bottom: 8px;
        }

        .header .description {
            color: var(--text-secondary);
            font-size: 0.95rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px;
            text-align: center;
        }

        .stat-card .number {
            font-size: 1.4rem;
            font-weight: 700;
        }

        .stat-card .label {
            font-size: 0.7rem;
            color: var(--text-secondary);
            margin-top: 4px;
            text-transform: uppercase;
        }

        .positive { color: var(--green); }
        .negative { color: var(--red); }

        .config-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .config-section h3 {
            font-size: 1rem;
            margin-bottom: 12px;
            color: var(--purple);
        }

        .config-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }

        .config-item {
            font-size: 0.85rem;
        }

        .config-item .key {
            color: var(--text-secondary);
        }

        .chart-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .chart-container h3 {
            font-size: 1rem;
            margin-bottom: 16px;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.85rem;
            text-decoration: none;
        }

        .btn:hover {
            background: var(--bg-card-hover);
            border-color: var(--blue);
        }

        .trade-table {
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
            font-size: 0.85rem;
        }

        .trade-table th, .trade-table td {
            padding: 10px 8px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }

        .trade-table th {
            background: var(--bg-card-hover);
            font-size: 0.7rem;
            text-transform: uppercase;
            color: var(--text-secondary);
        }

        .outcome-win { color: var(--green); font-weight: 600; }
        .outcome-loss { color: var(--red); font-weight: 600; }

        .pending-trade {
            background: var(--bg-card);
            border: 2px solid var(--purple);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }

        .pending-trade h3 {
            color: var(--purple);
            margin-bottom: 12px;
        }

        @media (max-width: 768px) {
            .stat-card .number { font-size: 1.2rem; }
            .trade-table { font-size: 0.75rem; }
            .trade-table th, .trade-table td { padding: 8px 4px; }
            .hide-mobile { display: none; }
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">&larr; Back to Dashboard</a>

    <div class="header">
        <h1>{{ bot.name }}</h1>
        <div class="description">{{ bot.description }}</div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="number">{{ bot.trades }}</div>
            <div class="label">Trades</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ bot.wins }}</div>
            <div class="label">Wins</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ bot.losses }}</div>
            <div class="label">Losses</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ "{:.0f}".format(bot.win_rate) }}%</div>
            <div class="label">Win Rate</div>
        </div>
        <div class="stat-card">
            <div class="number {{ 'positive' if bot.profit >= 0 else 'negative' }}">
                ${{ "{:.2f}".format(bot.profit) }}
            </div>
            <div class="label">Profit</div>
        </div>
        <div class="stat-card">
            <div class="number {{ 'positive' if bot.roi >= 0 else 'negative' }}">
                {{ "{:.1f}".format(bot.roi) }}%
            </div>
            <div class="label">ROI</div>
        </div>
        <div class="stat-card">
            <div class="number">${{ "{:.2f}".format(bot.bankroll) }}</div>
            <div class="label">Bankroll</div>
        </div>
        <div class="stat-card">
            <div class="number">${{ "{:.2f}".format(bot.total_fees) }}</div>
            <div class="label">Fees Paid</div>
        </div>
    </div>

    <div class="config-section">
        <h3>Strategy Configuration</h3>
        <div class="config-grid">
            {% if config.target_minute %}
            <div class="config-item"><span class="key">Target Minute:</span> {{ config.target_minute }}</div>
            {% endif %}
            {% if config.min_wait_minutes is not none %}
            <div class="config-item"><span class="key">Min Wait:</span> {{ config.min_wait_minutes }}m</div>
            {% endif %}
            {% if config.min_edge %}
            <div class="config-item"><span class="key">Min Edge:</span> {{ "{:.0f}".format(config.min_edge * 100) }}%</div>
            {% endif %}
            {% if config.odds_threshold %}
            <div class="config-item"><span class="key">Odds Threshold:</span> {{ config.odds_threshold }}c</div>
            {% endif %}
            {% if config.true_probability %}
            <div class="config-item"><span class="key">True Prob:</span> {{ "{:.1f}".format(config.true_probability * 100) }}%</div>
            {% endif %}
            <div class="config-item"><span class="key">Bet Size:</span> ${{ config.bet_size }}</div>
            {% if config.scale_with_edge %}
            <div class="config-item"><span class="key">Scaling:</span> Enabled</div>
            {% endif %}
        </div>
    </div>

    {% if pending_trade %}
    <div class="pending-trade">
        <h3>Pending Trade</h3>
        <div class="config-grid">
            <div class="config-item"><span class="key">Direction:</span> {{ pending_trade.direction }}</div>
            <div class="config-item"><span class="key">Entry:</span> {{ pending_trade.entry_price }}c</div>
            <div class="config-item"><span class="key">Contracts:</span> {{ pending_trade.contracts }}</div>
            <div class="config-item"><span class="key">Bet Size:</span> ${{ "{:.2f}".format(pending_trade.bet_size) }}</div>
            <div class="config-item"><span class="key">Strike:</span> ${{ "{:,.2f}".format(pending_trade.strike) }}</div>
            <div class="config-item"><span class="key">BTC at Entry:</span> ${{ "{:,.2f}".format(pending_trade.btc_price) }}</div>
        </div>
    </div>
    {% endif %}

    {% if trade_history %}
    <div class="chart-container">
        <h3>Bankroll Over Time</h3>
        <canvas id="bankrollChart" height="150"></canvas>
    </div>

    <div class="section-header">
        <h3>Trade History</h3>
        <a class="btn" href="/download/bot/{{ bot_id }}">Download CSV</a>
    </div>

    <table class="trade-table">
        <thead>
            <tr>
                <th>Time</th>
                <th>Dir</th>
                <th>Entry</th>
                <th class="hide-mobile">Edge</th>
                <th>Result</th>
                <th>P/L</th>
                <th class="hide-mobile">Bankroll</th>
            </tr>
        </thead>
        <tbody>
            {% for trade in trade_history|reverse %}
            <tr>
                <td>{{ trade.timestamp[:16] if trade.timestamp else '-' }}</td>
                <td>{{ trade.direction }}</td>
                <td>{{ trade.entry_price }}c</td>
                <td class="hide-mobile">{{ "{:.1f}".format(trade.edge * 100) if trade.edge else '-' }}%</td>
                <td class="{{ 'outcome-win' if trade.outcome == 'win' else 'outcome-loss' }}">
                    {{ trade.outcome|upper if trade.outcome else 'PENDING' }}
                </td>
                <td class="{{ 'positive' if trade.profit and trade.profit >= 0 else 'negative' }}">
                    ${{ "{:.2f}".format(trade.profit) if trade.profit else '-' }}
                </td>
                <td class="hide-mobile">${{ "{:.2f}".format(trade.bankroll_after) if trade.bankroll_after else '-' }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p style="color: var(--text-secondary); text-align: center; padding: 40px;">No trades yet</p>
    {% endif %}

    <script>
        {% if trade_history %}
        const bankrollData = {{ bankroll_history | safe }};

        new Chart(document.getElementById('bankrollChart'), {
            type: 'line',
            data: {
                labels: bankrollData.map((_, i) => i + 1),
                datasets: [{
                    label: 'Bankroll',
                    data: bankrollData,
                    borderColor: '#4a9eff',
                    backgroundColor: 'rgba(74, 158, 255, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: '#2a2a3a' }, ticks: { color: '#888' } },
                    x: { grid: { display: false }, ticks: { color: '#888' } }
                }
            }
        });
        {% endif %}
    </script>
</body>
</html>
"""

# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
@requires_auth
def dashboard():
    state = load_state()
    if not state:
        return "No data yet. Worker may not be running."

    bots_data = state.get('bots', {})
    bots = []

    series_profit = {'s1': 0, 's2': 0, 's3': 0}

    for bot_id, data in bots_data.items():
        bot = SimpleNamespace(
            bot_id=bot_id,
            name=data.get('name', bot_id),
            trades=data.get('trades', 0),
            wins=data.get('wins', 0),
            losses=data.get('losses', 0),
            win_rate=data.get('win_rate', 0),
            bankroll=data.get('bankroll', 1000),
            profit=data.get('profit', 0),
            roi=data.get('roi', 0),
            pending=data.get('pending', False),
            last_skip_reason=data.get('last_skip_reason'),
        )
        bots.append(bot)

        series = bot_id[:2]
        if series in series_profit:
            series_profit[series] += data.get('profit', 0)

    # Sort by profit descending
    bots.sort(key=lambda b: b.profit, reverse=True)

    total_trades = sum(b.trades for b in bots)
    total_wins = sum(b.wins for b in bots)
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    total_profit = sum(b.profit for b in bots)
    pending_trades = sum(1 for b in bots if b.pending)

    market = None
    if state.get('market'):
        market = SimpleNamespace(**state['market'])

    runtime_secs = state.get('runtime_seconds', 0)
    hours = int(runtime_secs // 3600)
    mins = int((runtime_secs % 3600) // 60)
    runtime = f"{hours}h {mins}m"

    return render_template_string(
        MAIN_TEMPLATE,
        bots=bots,
        bot_count=len(bots),
        total_trades=total_trades,
        win_rate=win_rate,
        total_profit=total_profit,
        pending_trades=pending_trades,
        windows_processed=state.get('windows_processed', 0),
        market=market,
        tick_count=state.get('tick_count', 0),
        last_update=state.get('last_update', 'Unknown')[:19],
        runtime=runtime,
        series_data=json.dumps(series_profit)
    )


@app.route('/bot/<bot_id>')
@requires_auth
def bot_detail(bot_id):
    state = load_state()
    if not state:
        return "No data available"

    bot_data = state.get('bots', {}).get(bot_id)
    if not bot_data:
        return f"Bot {bot_id} not found"

    bot = SimpleNamespace(
        bot_id=bot_id,
        name=bot_data.get('name', bot_id),
        description=bot_data.get('description', ''),
        trades=bot_data.get('trades', 0),
        wins=bot_data.get('wins', 0),
        losses=bot_data.get('losses', 0),
        win_rate=bot_data.get('win_rate', 0),
        bankroll=bot_data.get('bankroll', 1000),
        profit=bot_data.get('profit', 0),
        roi=bot_data.get('roi', 0),
        total_fees=bot_data.get('total_fees', 0),
    )

    config_data = bot_data.get('config', {})
    config = SimpleNamespace(
        target_minute=config_data.get('target_minute'),
        min_wait_minutes=config_data.get('min_wait_minutes'),
        min_edge=config_data.get('min_edge'),
        odds_threshold=config_data.get('odds_threshold'),
        true_probability=config_data.get('true_probability'),
        bet_size=config_data.get('bet_size', 10),
        scale_with_edge=config_data.get('scale_with_edge', False),
    )

    trade_history = bot_data.get('trade_history', [])
    pending_trade = bot_data.get('pending_trade')

    bankroll_history = [1000]  # Start with initial
    for trade in trade_history:
        if trade.get('bankroll_after'):
            bankroll_history.append(trade['bankroll_after'])

    return render_template_string(
        BOT_DETAIL_TEMPLATE,
        bot=bot,
        bot_id=bot_id,
        config=config,
        trade_history=trade_history,
        pending_trade=pending_trade,
        bankroll_history=json.dumps(bankroll_history)
    )


@app.route('/download/json')
@requires_auth
def download_json():
    state = load_state()
    if not state:
        return "No data", 404
    return Response(
        json.dumps(state, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment;filename=polymarket_bot_state.json'}
    )


@app.route('/download/csv')
@requires_auth
def download_csv():
    state = load_state()
    if not state:
        return "No data", 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bot ID', 'Name', 'Series', 'Trades', 'Wins', 'Losses', 'Win Rate', 'Bankroll', 'Profit', 'ROI', 'Fees'])

    for bot_id, data in state.get('bots', {}).items():
        writer.writerow([
            bot_id,
            data.get('name', ''),
            data.get('series', ''),
            data.get('trades', 0),
            data.get('wins', 0),
            data.get('losses', 0),
            f"{data.get('win_rate', 0):.1f}%",
            f"${data.get('bankroll', 1000):.2f}",
            f"${data.get('profit', 0):.2f}",
            f"{data.get('roi', 0):.1f}%",
            f"${data.get('total_fees', 0):.2f}",
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=polymarket_bot_summary.csv'}
    )


@app.route('/download/bot/<bot_id>')
@requires_auth
def download_bot_csv(bot_id):
    state = load_state()
    if not state:
        return "No data", 404

    bot_data = state.get('bots', {}).get(bot_id)
    if not bot_data:
        return f"Bot {bot_id} not found", 404

    trades = bot_data.get('trade_history', [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Window', 'Direction', 'Entry Price', 'Contracts', 'Bet Size', 'Fee', 'Edge', 'Outcome', 'Profit', 'Bankroll After'])

    for trade in trades:
        writer.writerow([
            trade.get('timestamp', ''),
            trade.get('window_id', ''),
            trade.get('direction', ''),
            trade.get('entry_price', ''),
            trade.get('contracts', ''),
            f"${trade.get('bet_size', 0):.2f}",
            f"${trade.get('fee', 0):.2f}",
            f"{trade.get('edge', 0) * 100:.1f}%" if trade.get('edge') else '',
            trade.get('outcome', ''),
            f"${trade.get('profit', 0):.2f}" if trade.get('profit') is not None else '',
            f"${trade.get('bankroll_after', 0):.2f}" if trade.get('bankroll_after') else '',
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={bot_id}_trades.csv'}
    )


@app.route('/download/all-trades')
@requires_auth
def download_all_trades():
    state = load_state()
    if not state:
        return "No data", 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bot ID', 'Bot Name', 'Timestamp', 'Window', 'Direction', 'Entry Price', 'Contracts', 'Bet Size', 'Fee', 'Edge', 'Outcome', 'Profit', 'Bankroll After'])

    for bot_id, data in state.get('bots', {}).items():
        for trade in data.get('trade_history', []):
            writer.writerow([
                bot_id,
                data.get('name', ''),
                trade.get('timestamp', ''),
                trade.get('window_id', ''),
                trade.get('direction', ''),
                trade.get('entry_price', ''),
                trade.get('contracts', ''),
                f"${trade.get('bet_size', 0):.2f}",
                f"${trade.get('fee', 0):.2f}",
                f"{trade.get('edge', 0) * 100:.1f}%" if trade.get('edge') else '',
                trade.get('outcome', ''),
                f"${trade.get('profit', 0):.2f}" if trade.get('profit') is not None else '',
                f"${trade.get('bankroll_after', 0):.2f}" if trade.get('bankroll_after') else '',
            ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=polymarket_all_trades.csv'}
    )


@app.route('/api/state')
@requires_auth
def api_state():
    state = load_state()
    return jsonify(state or {})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
