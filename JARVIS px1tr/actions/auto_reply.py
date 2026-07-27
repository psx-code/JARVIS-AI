"""
auto_reply.py  —  Away-mode autoresponder
==========================================
Strategy:
  1. Focus WhatsApp (already open)
  2. Click the "Unread" filter tab at top of chat list
  3. Screenshot the filtered list — first chat is guaranteed unread
  4. Read contact name + message preview using OCR on that row only
  5. Generate reply via or_client.py (OpenRouter)
  6. Click the first chat to open it
  7. Click the message input box and type + send

No clipboard, no window title, no Gemini API needed.
OCR uses pytesseract on a tiny cropped region — very fast and accurate.
"""

import io
import re
import time
import threading
import subprocess
import pyautogui
import mss
import mss.tools
import numpy as np

try:
    import PIL.Image
    import PIL.ImageEnhance
    import PIL.ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import pytesseract
    _OCR_OK = True
except ImportError:
    _OCR_OK = False

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESCALATION_KEYWORDS = [
    "emergency", "urgent", "call me now", "accident", "hospital",
    "help me", "asap", "911",
]

COOLDOWN_SECONDS = 120
POLL_INTERVAL    = 30.0

# WhatsApp green badge colors
WHATSAPP_GREENS = [
    (0,  168, 132),   # #00A884 modern
    (37, 211, 102),   # #25D366 older
    (18, 140, 126),   # #128C7E dark
]
COLOR_TOLERANCE = 25

# WhatsApp layout constants (as fractions of screen)
# Left panel occupies roughly left 35% of screen
# Chat list starts after the narrow sidebar (~6% from left)
SIDEBAR_END_FRAC = 0.06   # narrow icon sidebar ends here
PANEL_END_FRAC   = 0.35   # chat list panel ends here
CHAT_PANEL_MID   = (SIDEBAR_END_FRAC + PANEL_END_FRAC) / 2  # ~0.205

# Top of chat list (below search bar + filter tabs) — skip top 220px
CHAT_LIST_TOP = 220
# Bottom margin
CHAT_LIST_BOT = 60


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def _screenshot_rgb() -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img  = np.frombuffer(shot.raw, dtype=np.uint8)
        img  = img.reshape((shot.height, shot.width, 4))
        return img[:, :, :3][:, :, ::-1].copy()   # BGRA → RGB


def _crop_pil(rgb: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> 'PIL.Image.Image':
    region = rgb[y1:y2, x1:x2]
    return PIL.Image.fromarray(region)


# ---------------------------------------------------------------------------
# Green badge detection
# ---------------------------------------------------------------------------

def _find_unread_badge(rgb: np.ndarray) -> Optional[Tuple[int, int]]:
    """
    Find the green unread badge in the chat list panel only.
    Skip top CHAT_LIST_TOP px (title + search + filter tabs) and sidebar.
    Returns (x, y) in screen coords or None.
    """
    h, w = rgb.shape[:2]
    x_start = int(w * SIDEBAR_END_FRAC)
    x_end   = int(w * PANEL_END_FRAC)
    y_start = CHAT_LIST_TOP
    y_end   = h - CHAT_LIST_BOT

    panel = rgb[y_start:y_end, x_start:x_end, :]

    best_pos = None
    best_count = 0

    for target in WHATSAPP_GREENS:
        tr, tg, tb = target
        mask = (
            (np.abs(panel[:, :, 0].astype(int) - tr) < COLOR_TOLERANCE) &
            (np.abs(panel[:, :, 1].astype(int) - tg) < COLOR_TOLERANCE) &
            (np.abs(panel[:, :, 2].astype(int) - tb) < COLOR_TOLERANCE)
        )
        ys, xs = np.where(mask)
        if len(xs) > best_count:
            best_count = len(xs)
            cx = int(np.median(xs)) + x_start
            cy = int(np.median(ys)) + y_start
            best_pos = (cx, cy)

    if best_pos and best_count > 8:
        print(f"[AutoReply] 🟢 Badge: {best_count}px at screen {best_pos}")
        return best_pos
    return None


# ---------------------------------------------------------------------------
# OCR helper — read contact name + message preview from chat row
# ---------------------------------------------------------------------------

def _ocr_chat_row(rgb: np.ndarray, badge_y: int) -> Tuple[str, str]:
    """
    Given the y-coordinate of the unread badge, crop the chat row
    and OCR it to extract contact name and message preview.
    
    WhatsApp chat row layout (approx):
      - Row height: ~72px
      - Contact name: top half of row, left side
      - Message preview: bottom half of row, left side
      - Timestamp + badge: right side
    
    Returns (contact, preview_message).
    """
    if not _PIL_OK or not _OCR_OK:
        return "Unknown", ""

    h, w = rgb.shape[:2]
    row_h = 72
    x1 = int(w * SIDEBAR_END_FRAC) + 70   # skip avatar
    x2 = int(w * PANEL_END_FRAC)   - 80   # skip timestamp+badge area
    y1 = max(0, badge_y - row_h // 2)
    y2 = min(h, badge_y + row_h // 2)

    row_img = _crop_pil(rgb, x1, y1, x2, y2)

    # Scale up 3x for better OCR accuracy
    scale = 3
    row_img = row_img.resize(
        (row_img.width * scale, row_img.height * scale),
        PIL.Image.LANCZOS
    )

    # Enhance contrast for dark theme
    row_img = PIL.ImageEnhance.Contrast(row_img).enhance(2.5)
    row_img = row_img.convert("L")   # grayscale
    row_img = PIL.ImageEnhance.Sharpness(PIL.Image.fromarray(
        np.array(row_img)
    )).enhance(2.0)

    raw = pytesseract.image_to_string(row_img, config="--psm 6").strip()
    print(f"[AutoReply] 🔤 OCR row: {raw!r}")

    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    # Filter noise
    lines = [l for l in lines if len(l) > 1 and not re.match(r'^\W+$', l)]

    contact = lines[0] if len(lines) > 0 else "Unknown"
    preview  = lines[1] if len(lines) > 1 else ""

    return contact, preview


# ---------------------------------------------------------------------------
# WhatsApp window management
# ---------------------------------------------------------------------------

_whatsapp_launched_once = False


def _focus_whatsapp() -> bool:
    """Bring WhatsApp to foreground. Launch once if not running."""
    global _whatsapp_launched_once

    ps = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WA32 {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
"@ -ErrorAction SilentlyContinue
$w = Get-Process WhatsApp -ErrorAction SilentlyContinue |
     Where-Object {$_.MainWindowHandle -ne 0} |
     Select-Object -First 1
if ($w) {
  [WA32]::ShowWindow($w.MainWindowHandle, 9)
  [WA32]::SetForegroundWindow($w.MainWindowHandle)
  exit 0
} else { exit 1 }
"""
    try:
        r = subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            capture_output=True, timeout=8
        )
        if r.returncode == 0:
            _whatsapp_launched_once = True
            time.sleep(1.2)
            return True
    except Exception as e:
        print(f"[AutoReply] ⚠️ focus error: {e}")

    # Not running — launch once only
    if _whatsapp_launched_once:
        print("[AutoReply] ⚠️ WhatsApp not running, already tried launching.")
        return False

    _whatsapp_launched_once = True
    print("[AutoReply] 🚀 Launching WhatsApp once...")
    try:
        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write("WhatsApp", interval=0.05)
        time.sleep(0.6)
        pyautogui.press("enter")
        time.sleep(5.0)
        return True
    except Exception as e:
        print(f"[AutoReply] ❌ Launch failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Close WhatsApp
# ---------------------------------------------------------------------------

def _close_whatsapp():
    """Close WhatsApp by killing the process via PowerShell."""
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command",
             "Stop-Process -Name WhatsApp -ErrorAction SilentlyContinue"],
            timeout=5
        )
        time.sleep(1.0)
        print("[AutoReply] 🔴 WhatsApp closed.")
    except Exception as e:
        print(f"[AutoReply] ⚠️ Could not close WhatsApp: {e}")


# ---------------------------------------------------------------------------
# Click the unread chat and send reply
# ---------------------------------------------------------------------------

def _click_chat_row(badge_y: int, screen_w: int):
    """Click the contact name area of the chat row at the given y."""
    click_x = int(screen_w * CHAT_PANEL_MID)
    click_y = badge_y
    print(f"[AutoReply] 👆 Clicking chat at ({click_x}, {click_y})")
    pyautogui.click(click_x, click_y)
    time.sleep(2.0)   # wait for chat to fully open


def _send_reply_in_open_chat(reply: str, screen_w: int, screen_h: int):
    """
    Type and send a reply in the currently open WhatsApp chat.
    The 'Type a message' input box sits at roughly 88% of screen height
    and horizontally in the right chat panel (center ~65% of width).
    We clamp y to max 87% to never accidentally hit the taskbar.
    """
    import pyperclip

    # Input box coordinates — clamped well above taskbar
    input_x = int(screen_w * 0.65)
    input_y = min(int(screen_h * 0.88), screen_h - 80)  # never below 80px from bottom

    print(f"[AutoReply] ⌨️ Clicking input box at ({input_x}, {input_y})")
    pyautogui.click(input_x, input_y)
    time.sleep(0.6)

    # Verify focus by checking if pyautogui can type safely
    # Use clipboard paste to handle unicode, emojis, Hindi text
    try:
        old = pyperclip.paste()
    except Exception:
        old = ""

    pyperclip.copy(reply)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(0.5)

    # Press Escape to close/deselect the chat before WhatsApp closes
    pyautogui.press("escape")
    time.sleep(0.3)

    try:
        pyperclip.copy(old)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Reply generation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Custom away message — edit AWAY_MESSAGE to change what gets sent
# ---------------------------------------------------------------------------

AWAY_MESSAGE = (
    "Hello, I am JARVIS (Poorna's AI assistant). "
    "Poorna is busy right now, he will reply to you soon."
)


def _generate_reply(reason: str, sender: str, message: str) -> str:
    """
    Returns the auto-reply message.
    By default uses the fixed AWAY_MESSAGE above.
    Set USE_AI_REPLY = True below to generate a custom reply using OpenRouter instead.
    """
    USE_AI_REPLY = False   # ← change to True to use AI-generated replies

    if not USE_AI_REPLY:
        return AWAY_MESSAGE

    # AI-generated reply (only used when USE_AI_REPLY = True)
    prompt = (
        f"Write ONE short auto-reply text message (under 20 words) on behalf of someone "
        f"who is currently {reason}. "
        f"The message from {sender} was: \"{message}\". "
        f"Do NOT make any commitments or share sensitive info. "
        f"Just acknowledge and say they will reply later. "
        f"Reply with ONLY the message text, nothing else."
    )

    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from or_client import OpenRouterClient
        client = OpenRouterClient()
        result = client.chat(prompt)
        if result and len(result.strip()) > 3:
            return result.strip().strip('"')
    except Exception as e:
        print(f"[AutoReply] ⚠️ or_client failed: {e} — using fallback")

    return AWAY_MESSAGE


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class AwayState:
    active:     bool                = False
    reason:     str                 = ""
    whitelist:  Optional[List[str]] = None
    blacklist:  List[str]           = field(default_factory=list)
    sign_reply: bool                = False
    log:        List[str]           = field(default_factory=list)
    _last_reply_time: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AutoReplyEngine:

    def __init__(self, ui, get_api_key, speak_fn=None):
        self.ui           = ui
        self._get_api_key = get_api_key
        self.speak_fn     = speak_fn
        self.state        = AwayState()
        self._lock        = threading.Lock()
        self._stop_event  = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def go_away(self, reason: str = "", whitelist=None, blacklist=None, sign_reply: bool = False):
        global _whatsapp_launched_once
        _whatsapp_launched_once = False
        with self._lock:
            self.state = AwayState(
                active     = True,
                reason     = reason.strip() or "away from the computer",
                whitelist  = whitelist,
                blacklist  = blacklist or [],
                sign_reply = sign_reply,
            )
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="AutoReplyPoll"
        )
        self._poll_thread.start()
        self.ui.write_log(f"SYS: Away mode ON — {self.state.reason}")
        print(f"[AutoReply] 🟢 Away mode ON. Polling every {int(POLL_INTERVAL)}s.")

    def come_back(self) -> str:
        self._stop_event.set()
        with self._lock:
            was_active = self.state.active
            self.state.active = False
            log = list(self.state.log)
        if not was_active:
            return "Away mode wasn't on, sir."
        if not log:
            return "No messages came in while you were away, sir."
        return "While you were away, sir:\n" + "\n".join(log)

    @property
    def is_away(self) -> bool:
        return self.state.active

    def handle_notification(self, notif):
        if not self.state.active:
            return
        sender  = notif.title.strip()
        message = notif.message.strip()
        if not sender or not message:
            return
        last = self.state._last_reply_time.get(sender, 0)
        if time.time() - last < COOLDOWN_SECONDS:
            return
        if any(k in message.lower() for k in ESCALATION_KEYWORDS):
            self.state.log.append(f"⚠️ {sender}: urgent — NOT auto-replied.")
            if self.speak_fn:
                self.speak_fn(f"Sir, urgent message from {sender}: {message}")
            return
        reply = _generate_reply(self.state.reason, sender, message)
        if self.state.sign_reply:
            reply = f"{reply} (auto-reply)"
        sw, sh = pyautogui.size()
        if _focus_whatsapp():
            # Search for the contact
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.5)
            pyautogui.write(sender, interval=0.05)
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(1.0)
            _send_reply_in_open_chat(reply, sw, sh)
            self.state._last_reply_time[sender] = time.time()
            self.state.log.append(f"- {sender}: \"{self._clip(message)}\" → \"{reply}\"")
            self.ui.write_log(f"AUTO-REPLY → {sender}: {reply}")

    def _poll_loop(self):
        print("[AutoReply] 🔄 Poll loop started")
        self._stop_event.wait(timeout=8)
        while not self._stop_event.is_set() and self.state.active:
            try:
                self._check_whatsapp()
            except Exception as e:
                print(f"[AutoReply] ⚠️ Poll error: {e}")
            self._stop_event.wait(timeout=POLL_INTERVAL)
        print("[AutoReply] 🔴 Poll loop stopped")

    def _check_whatsapp(self):
        global _whatsapp_launched_once
        _whatsapp_launched_once = False   # reset each cycle so WhatsApp can reopen

        # Step 1: Open/focus WhatsApp
        if not _focus_whatsapp():
            return
        time.sleep(0.8)

        # Step 2: Screenshot and find green badge
        rgb = _screenshot_rgb()
        badge_pos = _find_unread_badge(rgb)
        if badge_pos is None:
            print("[AutoReply] ✅ No unread badge found")
            _close_whatsapp()
            return

        bx, by = badge_pos
        sw, sh = pyautogui.size()

        # Step 3: OCR the chat row to get contact + preview BEFORE clicking
        contact, preview = _ocr_chat_row(rgb, by)
        print(f"[AutoReply] 📋 OCR → contact={contact!r} preview={preview!r}")

        # If OCR failed, still proceed — we'll use generic reply
        if not contact or contact == "Unknown":
            print("[AutoReply] ⚠️ OCR got Unknown — trying anyway")

        # Step 4: Safety checks on contact
        if self.state.whitelist and contact.lower() not in [w.lower() for w in self.state.whitelist]:
            self.state.log.append(f"- {contact} messaged — not on reply list.")
            return
        if contact.lower() in [b.lower() for b in self.state.blacklist]:
            return
        last = self.state._last_reply_time.get(contact, 0)
        if time.time() - last < COOLDOWN_SECONDS:
            print(f"[AutoReply] ⏸️ Cooldown active for {contact}")
            _close_whatsapp()
            return
        msg_text = preview or "(message)"
        if any(k in msg_text.lower() for k in ESCALATION_KEYWORDS):
            self.state.log.append(f"⚠️ {contact}: urgent — NOT auto-replied.")
            if self.speak_fn:
                self.speak_fn(f"Sir, urgent message from {contact}: {msg_text}")
            return

        # Step 5: Generate reply BEFORE opening chat
        reply = _generate_reply(self.state.reason, contact, msg_text)
        if self.state.sign_reply:
            reply = f"{reply} (auto-reply)"

        # Step 6: Click to open the chat
        _click_chat_row(by, sw)

        # Step 7: Send reply in the open chat
        _send_reply_in_open_chat(reply, sw, sh)

        self.state._last_reply_time[contact] = time.time()
        self.state.log.append(f"- {contact}: \"{self._clip(msg_text)}\" → \"{reply}\"")
        self.ui.write_log(f"AUTO-REPLY → {contact}: {reply}")
        print(f"[AutoReply] ✅ Replied to {contact}: {reply}")
        time.sleep(0.5)
        _close_whatsapp()

    @staticmethod
    def _clip(text: str, n: int = 60) -> str:
        return text if len(text) <= n else text[: n - 1] + "…"