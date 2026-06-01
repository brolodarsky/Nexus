"""
main.py — Universal coordinator and Mission Control for the Nexus Engine.
Handles CLI, Voice, and Telegram interfaces and provides an interactive management menu.
"""
import sys
import os
import argparse
import threading
import logging
import time

# Fix Windows console emoji printing
sys.stdout.reconfigure(encoding='utf-8')
import logging
import time

from agents.router.agent import route_content

# Disable noisy logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

BOT_ONLINE = False

def start_telegram_interface():
    """Starts the telegram bot listener."""
    global BOT_ONLINE
    try:
        from interfaces.telegram import main as telegram_main
        BOT_ONLINE = True
        telegram_main()
    except Exception as e:
        BOT_ONLINE = False
        # Silent failure for background thread, we'll see it in status

def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("  " + "═" * 45)
    print("  ║" + " " * 12 + "🧠 Nexus ENGINE" + " " * 13 + "║")
    print("  " + "═" * 45)
    status = "🟢 ONLINE" if BOT_ONLINE else "⏳ STARTING"
    print(f"  [ Telegram Bot: {status} ]\n")

def show_menu():
    print("  1. 💬  Ask Brain (Text)")
    print("  2. 🎙️   Voice Query (Mic)")
    print("  3. ❌  Exit")
    print("\n  " + "─" * 45)

def print_agent_response(query: str, filters: dict = None):
    print(f"🧠 Querying Vault Agent: {query}")
    print("Agent is reasoning and routing...\n")
    
    result = route_content(query, filters=filters)
    
    # Optional: Display routing context
    if result["domain"]:
        print(f"  [Router Classifed: {result['domain']} | Confidence: {result['confidence']:.2f}]")
    
    print("\n" + "="*45)
    print("🤖 Response:")
    print("="*45)
    print(result["response"])
    print("="*45 + "\n")

def main():
    """
    Enduring terminal menu coordinator for the Nexus Engine.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--no-bot', action='store_true')
    args, remaining = parser.parse_known_args()

    # 1. Start Telegram Bot in background
    if not args.no_bot:
        threading.Thread(target=start_telegram_interface, daemon=True).start()

    # 2. If a query was passed directly via CLI, run it and exit
    if remaining:
        from interfaces.cli import parse_cli_args
        query, filters = parse_cli_args(remaining)
        if query:
            print_agent_response(query, filters)
        return

    # 3. Otherwise, enter the persistent menu
    while True:
        print_header()
        show_menu()
        
        choice = input("  Select option [1-3] » ").strip()

        if choice == '1':
            query = input("\n  💬 Query: ")
            if query.strip():
                print("\n" + "─" * 45)
                print_agent_response(query)
                input("\n  Press Enter to return to menu...")
        
        elif choice == '2':
            print("\n  🎙️ Starting local voice capture...")
            from interfaces.voice import capture_voice_query
            query = capture_voice_query()
            if query:
                print("\n" + "─" * 45)
                print_agent_response(query)
            input("\n  Press Enter to return to menu...")

        elif choice == '3' or choice.lower() in ['exit', 'q', 'quit']:
            print("\n  👋 Shutting down Nexus.0. See you in the vault.")
            time.sleep(1)
            break
        
        else:
            print("  ⚠️ Invalid choice.")
            time.sleep(1)

if __name__ == "__main__":
    main()
