"""
Notifications cross-platform.
macOS → popup desktop. Cloud/Linux → log uniquement.
"""
import sys
import subprocess
from datetime import datetime, timezone

def send(title: str, message: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] 🔔 {title}: {message}", flush=True)

    if sys.platform == "darwin":
        try:
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3)
        except Exception:
            pass
