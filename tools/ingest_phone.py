"""
ingest_phone.py — Universal ADB Screen-Scraper for Android Chat Ingestion.

Captures the currently visible conversation from any Android messaging app
(Google Messages, Tinder, Hinge, WhatsApp, Signal, etc.) via ADB UI hierarchy
dump, then formats the thread as a structured Markdown note for the Brain Vault.

No third-party apps required on the phone. Just USB Debugging enabled.

Usage:
    python tools/ingest_phone.py                        # Capture current screen
    python tools/ingest_phone.py --screens 5            # Scroll up & capture 5 screens
    python tools/ingest_phone.py -o my_chat.md          # Custom output path
    python tools/ingest_phone.py --screens 10 --raw     # Raw text, no markdown formatting

Prerequisites:
    - ADB installed and on PATH (Android SDK Platform Tools)
    - USB Debugging enabled on the Android device
    - Device connected via USB or wireless ADB
"""
import argparse
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VAULT_ROOT = Path(__file__).resolve().parent.parent / "Vault"
INBOX_DIR = VAULT_ROOT / "0. Inbox"

APP_NAMES = {
    "com.google.android.apps.messaging": "Google Messages",
    "com.tinder": "Tinder",
    "co.hinge.app": "Hinge",
    "com.whatsapp": "WhatsApp",
    "org.thoughtcrime.securesms": "Signal",
    "com.facebook.orca": "Messenger",
    "com.instagram.android": "Instagram",
    "com.snapchat.android": "Snapchat",
    "com.discord": "Discord",
    "org.telegram.messenger": "Telegram",
    "com.bumble.app": "Bumble",
}

SYSTEM_PACKAGES = {
    "com.android.systemui",
    "com.google.android.inputmethod.latin",
    "com.android.inputmethod.latin",
    "com.samsung.android.honeyboard",
}

MIN_MESSAGE_LENGTH = 2

# ──────────────────────────────────────────────
# ADB Utilities
# ──────────────────────────────────────────────

def run_adb(args: list, device: str = None) -> str:
    """Run an ADB command and return stdout."""
    cmd = ["adb"]
    if device:
        cmd.extend(["-s", device])
    cmd.extend(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        print("❌ ADB not found. Install Android SDK Platform Tools and add to PATH.")
        print("   https://developer.android.com/tools/releases/platform-tools")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("❌ ADB command timed out. Is the device connected and authorized?")
        sys.exit(1)

    if result.returncode != 0 and "error" in result.stderr.lower():
        print(f"❌ ADB error: {result.stderr.strip()}")
        sys.exit(1)

    return result.stdout


def check_device(device: str = None) -> str:
    """Verify a device is connected. Returns device serial."""
    output = run_adb(["devices"], device)
    lines = [l.strip() for l in output.strip().splitlines()[1:] if l.strip()]

    devices = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])

    if not devices:
        print("❌ No authorized Android devices found.")
        print("   1. Enable USB Debugging: Settings → Developer Options → USB Debugging")
        print("   2. Connect via USB and tap 'Allow' on the authorization dialog")
        print("   3. Or use wireless ADB: Settings → Developer Options → Wireless Debugging")
        sys.exit(1)

    selected = device or devices[0]
    if device and device not in devices:
        print(f"❌ Device '{device}' not found. Available: {', '.join(devices)}")
        sys.exit(1)
    if len(devices) > 1 and not device:
        print(f"⚠️  Multiple devices detected. Using: {selected}")
        print(f"   Specify with --device. Available: {', '.join(devices)}")

    return selected


def get_foreground_app(device: str) -> str:
    """Get the current foreground app package name."""
    output = run_adb(["shell", "dumpsys", "activity", "activities"], device)
    for line in output.splitlines():
        if "mResumedActivity" in line or "ResumedActivity" in line:
            match = re.search(r'u0\s+(\S+)/', line)
            if match:
                return match.group(1)
    # Fallback
    output2 = run_adb(["shell", "dumpsys", "activity", "recents"], device)
    for line in output2.splitlines():
        if "topActivity" in line:
            match = re.search(r'(\S+)/', line)
            if match:
                return match.group(1)
    return "unknown"


def get_screen_size(device: str) -> tuple:
    """Get the device screen size (width, height) in pixels."""
    output = run_adb(["shell", "wm", "size"], device)
    match = re.search(r'(\d+)x(\d+)', output)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1080, 2400  # Sensible Pixel default


def dump_ui(device: str) -> str:
    """Dump the UI hierarchy XML from the device."""
    output = run_adb(["exec-out", "uiautomator", "dump", "/dev/tty"], device)

    # Strip the trailing status message uiautomator appends
    xml_end = output.rfind("</hierarchy>")
    if xml_end != -1:
        output = output[:xml_end + len("</hierarchy>")]

    xml_start = output.find("<?xml")
    if xml_start == -1:
        xml_start = output.find("<hierarchy")
    if xml_start == -1:
        print("❌ Failed to capture UI hierarchy. Is the screen on and unlocked?")
        sys.exit(1)

    return output[xml_start:]


def scroll_up(device: str, screen_width: int, screen_height: int):
    """Scroll to reveal older messages (swipe finger downward on screen)."""
    cx = screen_width // 2
    start_y = int(screen_height * 0.30)
    end_y = int(screen_height * 0.70)
    run_adb(["shell", "input", "swipe",
             str(cx), str(start_y), str(cx), str(end_y), "300"], device)


def scroll_to_bottom(device: str, screen_width: int, screen_height: int):
    """Scroll to the bottom of the chat (newest messages) before capture."""
    cx = screen_width // 2
    start_y = int(screen_height * 0.70)
    end_y = int(screen_height * 0.30)
    # Fast fling down several times to reach the bottom
    for _ in range(5):
        run_adb(["shell", "input", "swipe",
                 str(cx), str(start_y), str(cx), str(end_y), "150"], device)
        time.sleep(0.3)

# ──────────────────────────────────────────────
# XML Parsing & Message Extraction
# ──────────────────────────────────────────────

def parse_bounds(bounds_str: str):
    """Parse '[left,top][right,bottom]' → (left, top, right, bottom) or None."""
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if match:
        return tuple(int(x) for x in match.groups())
    return None


def extract_messages(xml_str: str, app_package: str,
                     screen_width: int, screen_height: int) -> list:
    """
    Extract message-like text nodes from the UI hierarchy.
    Returns list of dicts: {text, sender, y_pos}
    sender is 'me', 'them', or 'system' based on horizontal alignment.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        print(f"⚠️  XML parse error: {e}")
        return []

    messages = []
    screen_mid_x = screen_width // 2

    # Safe vertical zone — skip status bar, toolbar area, input bar, nav bar
    safe_top = int(screen_height * 0.10)
    safe_bottom = int(screen_height * 0.93)  # Wide to avoid clipping last message

    for node in root.iter("node"):
        text = node.get("text", "").strip()
        package = node.get("package", "")
        resource_id = node.get("resource-id", "")
        bounds_str = node.get("bounds", "")

        if package in SYSTEM_PACKAGES:
            continue
        if app_package != "unknown" and package and package != app_package:
            continue
        if not text or len(text) < MIN_MESSAGE_LENGTH:
            continue

        # Skip input fields
        rid_lower = resource_id.lower()
        if any(kw in rid_lower for kw in ("compose", "input", "edit_text", "send")):
            continue

        bounds = parse_bounds(bounds_str)
        if not bounds:
            continue

        left, top, right, bottom = bounds
        y_center = (top + bottom) // 2

        if y_center < safe_top or y_center > safe_bottom:
            continue

        x_center = (left + right) // 2
        msg_width = right - left

        # Skip full-width elements (likely headers, not messages)
        if msg_width > screen_width * 0.90:
            continue

        # Sender detection via horizontal alignment
        if x_center > screen_mid_x + (screen_width * 0.05):
            sender = "me"
        elif x_center < screen_mid_x - (screen_width * 0.05):
            sender = "them"
        else:
            sender = "system"

        messages.append({
            "text": text,
            "sender": sender,
            "y_pos": y_center,
        })

    messages.sort(key=lambda m: m["y_pos"])
    return messages


def detect_contact_name(xml_str: str, app_package: str,
                        screen_height: int) -> str:
    """Try to detect the contact name from the app toolbar area."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    toolbar_bottom = int(screen_height * 0.10)
    candidates = []

    for node in root.iter("node"):
        text = node.get("text", "").strip()
        package = node.get("package", "")
        bounds_str = node.get("bounds", "")

        if not text or package in SYSTEM_PACKAGES:
            continue
        if app_package != "unknown" and package and package != app_package:
            continue

        bounds = parse_bounds(bounds_str)
        if not bounds:
            continue

        _, top, _, bottom = bounds
        y_center = (top + bottom) // 2

        if y_center < toolbar_bottom and len(text) > 1:
            skip_words = {"back", "menu", "search", "call", "video", "more",
                          "navigate up", "details", "voice call", "video call"}
            if text.lower() in skip_words:
                continue
            if re.match(r'^\d{1,2}:\d{2}', text):
                continue
            # Real contact names are short — reject long message-like text
            if len(text) > 30:
                continue
            candidates.append((text, y_center))

    if candidates:
        candidates.sort(key=lambda c: c[1])
        for name, _ in candidates:
            if len(name) > 1 and not name.isdigit():
                return name
    return None

# ──────────────────────────────────────────────
# Multi-Screen Capture with Deduplication
# ──────────────────────────────────────────────

def capture_conversation(device: str, num_screens: int,
                         scroll_delay: float) -> tuple:
    """
    Capture a full conversation across multiple screens.
    Returns (all_messages, app_package, contact_name).
    """
    screen_width, screen_height = get_screen_size(device)
    app_package = get_foreground_app(device)
    app_name = APP_NAMES.get(app_package, app_package)

    print(f"📱 Device: {device}")
    print(f"📐 Screen: {screen_width}×{screen_height}")
    print(f"📦 App: {app_name} ({app_package})")
    print(f"📄 Screens to capture: {num_screens}")
    print()

    # Auto-scroll to bottom so capture starts from newest messages
    print("   ⬇️  Scrolling to bottom of thread...")
    scroll_to_bottom(device, screen_width, screen_height)
    time.sleep(0.5)

    all_messages = []
    seen_texts = set()
    contact_name = None
    screen_batches = []  # Each entry is one screen's unique messages
    empty_screens = 0

    for i in range(num_screens):
        if i > 0:
            print(f"   ↑ Scrolling up for screen {i + 1}...")
            scroll_up(device, screen_width, screen_height)
            time.sleep(scroll_delay)

        print(f"   📸 Capturing screen {i + 1}/{num_screens}...")
        xml_str = dump_ui(device)

        # Detect contact name from the first screen
        if contact_name is None:
            contact_name = detect_contact_name(
                xml_str, app_package, screen_height)

        screen_msgs = extract_messages(
            xml_str, app_package, screen_width, screen_height)

        # Deduplicate across screens, collect this screen's unique messages
        batch = []
        for msg in screen_msgs:
            if msg["text"] not in seen_texts:
                seen_texts.add(msg["text"])
                batch.append(msg)

        screen_batches.append(batch)
        print(f"   ✅ Found {len(screen_msgs)} nodes, {len(batch)} new messages")

        if len(batch) == 0 and i > 0:
            empty_screens += 1
            if empty_screens >= 3:
                print("   ⏹️  No new messages found for 3 screens — reached top of thread.")
                break
        else:
            empty_screens = 0

    # Screen 1 = newest (bottom of thread), last screen = oldest (top).
    # Reverse screen order so oldest screen comes first, then flatten.
    # Within each screen, messages are already sorted by y_pos (top→bottom = chronological).
    for batch in reversed(screen_batches):
        all_messages.extend(batch)

    return all_messages, app_package, contact_name

# ──────────────────────────────────────────────
# Markdown Formatting
# ──────────────────────────────────────────────

def format_markdown(messages: list, app_package: str,
                    contact_name: str, num_screens: int) -> str:
    """Format extracted messages into a structured Markdown note."""
    app_name = APP_NAMES.get(app_package, app_package)
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M %p")
    contact_display = contact_name or "Unknown"

    lines = [
        "---",
        "aliases: []",
        "tags:",
        "  - capture",
        "  - chat",
        f"type: capture/chat",
        f"source: {app_name}",
        f"contact: \"{contact_display}\"",
        f"captured: {now.isoformat(timespec='seconds')}",
        "---",
        "",
        f"# Chat Capture: {app_name} — {contact_display}",
        "",
        f"> Captured via ADB screen scrape on {date_str} at {time_str}",
        f"> Screens captured: {num_screens}",
        "",
        "---",
        "",
    ]

    if not messages:
        lines.append("*No messages were extracted. The screen may have been "
                      "empty or the app layout was not recognized.*")
    else:
        prev_sender = None
        for msg in messages:
            sender = msg["sender"]
            text = msg["text"]

            if sender == "system":
                # Timestamps render as divider lines between message groups
                lines.append("")
                lines.append(f"---  *{text}*  ---")
                lines.append("")
                prev_sender = None  # Reset so next message gets spacing
            elif sender == "me":
                if prev_sender != "me":
                    lines.append("")
                lines.append(f"**Me:** {text}")
                prev_sender = "me"
            else:
                if prev_sender != "them":
                    lines.append("")
                label = contact_display if contact_name else "Them"
                lines.append(f"**{label}:** {text}")
                prev_sender = "them"

    return "\n".join(lines) + "\n"


def format_raw(messages: list) -> str:
    """Format messages as plain text."""
    lines = []
    for msg in messages:
        prefix = {"me": "[Me]", "them": "[Them]", "system": "[---]"}
        lines.append(f"{prefix.get(msg['sender'], '[?]')} {msg['text']}")
    return "\n".join(lines) + "\n"

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Universal ADB screen-scraper for Android chat ingestion."
    )
    parser.add_argument(
        "--screens", type=int, default=1,
        help="Number of screens to capture. Scrolls up for older messages. (default: 1)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path. Default: auto-save to Vault/0. Inbox/"
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Output raw text without Markdown formatting."
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Print to stdout instead of saving to a file."
    )
    parser.add_argument(
        "--scroll-delay", type=float, default=1.5,
        help="Seconds to wait between scroll actions. (default: 1.5)"
    )
    parser.add_argument(
        "--device",
        help="ADB device serial (for multiple connected devices)."
    )

    args = parser.parse_args()

    # Force UTF-8 for Windows console (emoji support)
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

    print("🧠 Brain 2 — Phone Chat Ingestion")
    print("=" * 40)

    device = check_device(args.device)
    messages, app_package, contact_name = capture_conversation(
        device, args.screens, args.scroll_delay
    )

    print()
    print(f"📊 Total messages extracted: {len(messages)}")
    if contact_name:
        print(f"👤 Contact detected: {contact_name}")

    if not messages:
        print("⚠️  No messages extracted. Make sure a chat thread is open on screen.")
        sys.exit(1)

    # Format output
    if args.raw:
        output = format_raw(messages)
    else:
        output = format_markdown(
            messages, app_package, contact_name, args.screens)

    # Write output
    if args.stdout:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        print(output)
    else:
        if args.output:
            out_path = Path(args.output)
        else:
            # Auto-generate inbox path
            app_name = APP_NAMES.get(app_package, "Chat")
            safe_contact = re.sub(r'[^\w\s-]', '', contact_name or "Unknown")
            safe_contact = safe_contact.strip().replace(" ", " ")
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            filename = f"Capture - {app_name} - {safe_contact} - {timestamp}.md"
            out_path = INBOX_DIR / filename

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"\n✅ Saved to: {out_path}")
        print(f"   Open in Obsidian or feed to /ask_brain for advice!")


if __name__ == "__main__":
    main()
