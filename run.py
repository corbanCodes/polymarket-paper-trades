#!/usr/bin/env python3
"""
Combined Runner - Runs both worker and dashboard

Usage:
    python run.py           # Runs both worker + dashboard
    python run.py worker    # Runs only worker
    python run.py dashboard # Runs only dashboard
"""

import sys
import threading
import time
import os

def run_worker():
    """Run the live trading worker"""
    from live_worker import LiveWorker
    worker = LiveWorker()
    worker.run()

def run_dashboard():
    """Run the Flask dashboard"""
    from web_dashboard import app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'

    if mode == 'worker':
        print("Starting worker only...")
        run_worker()

    elif mode == 'dashboard':
        print("Starting dashboard only...")
        run_dashboard()

    else:
        # Run both
        print("=" * 60)
        print("POLYMARKET PAPER TRADING - COMBINED MODE")
        print("=" * 60)
        print("Starting worker in background thread...")
        print("Starting web dashboard...")
        print("=" * 60 + "\n")

        # Start worker in background thread
        worker_thread = threading.Thread(target=run_worker, daemon=True)
        worker_thread.start()

        # Give worker a moment to initialize
        time.sleep(2)

        # Run dashboard in main thread (blocks)
        run_dashboard()

if __name__ == '__main__':
    main()
