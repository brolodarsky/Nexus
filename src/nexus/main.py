"""
main.py — Universal coordinator and Mission Control for the Nexus Engine.
Handles CLI and Telegram interfaces with a persistent chat REPL.
"""
import sys
import os
import argparse
import threading
import logging
import time

# Fix Windows console emoji printing
sys.stdout.reconfigure(encoding='utf-8')

from nexus.agents.router.api import route_content

# Disable noisy logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

BOT_ONLINE = False

def start_telegram_interface():
    """Starts the telegram bot listener."""
    global BOT_ONLINE
    try:
        from nexus.interfaces.telegram import main as telegram_main
        BOT_ONLINE = True
        telegram_main()
    except Exception as e:
        BOT_ONLINE = False
        # Silent failure for background thread, we'll see it in status


def print_banner():
    """Print a one-time startup banner (no screen clear)."""
    print()
    print("  " + "═" * 45)
    print("  ║" + " " * 12 + "🧠 Nexus ENGINE" + " " * 13 + "║")
    print("  " + "═" * 45)
    print("  Chat Mode — type your query, 'exit' to quit.")
    print("  " + "─" * 45)
    print()


def print_agent_response(query: str, filters: dict = None):
    """Route a query through the multi-agent pipeline and print the result."""
    print()
    result = route_content(query, filters=filters)

    print()
    print("  " + "═" * 45)
    print("  🤖 Response:")
    print("  " + "═" * 45)
    print(result["response"])
    print("  " + "═" * 45)
    print()


def main():
    """
    Persistent chat REPL for the Nexus Engine.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--no-bot', action='store_true')
    args, remaining = parser.parse_known_args()

    # 1. Start Telegram Bot in background
    if not args.no_bot:
        threading.Thread(target=start_telegram_interface, daemon=True).start()

    # 2. If a query was passed directly via CLI, run it and exit
    if remaining:
        from nexus.interfaces.cli import parse_cli_args
        query, filters = parse_cli_args(remaining)
        if query:
            print_agent_response(query, filters)
        return

    # 3. Otherwise, enter the persistent chat REPL
    print_banner()

    while True:
        try:
            query = input("  You » ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  👋 Shutting down Nexus. See you in the vault.")
            break

        if not query:
            continue

        if query.lower() in ('exit', 'quit', 'q'):
            print("\n  👋 Shutting down Nexus. See you in the vault.")
            time.sleep(0.5)
            break

        print_agent_response(query)


if __name__ == "__main__":
    main()

