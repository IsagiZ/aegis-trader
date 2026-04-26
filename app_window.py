"""
Fenêtre native macOS pour Aegis — démarre Streamlit + ouvre une vraie fenêtre app.
"""
import subprocess
import sys
import time
import os
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).parent
PORT    = 8502
URL     = f"http://localhost:{PORT}"
PYTHON  = sys.executable


def start_server():
    """Démarre Streamlit en arrière-plan si pas déjà actif."""
    try:
        urllib.request.urlopen(URL, timeout=1)
        return  # déjà actif
    except Exception:
        pass

    log = open(PROJECT / "dashboard.log", "a")
    subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run", "dashboard.py",
         "--server.port", str(PORT),
         "--server.headless", "true",
         "--server.enableCORS", "false",
         "--server.enableXsrfProtection", "false"],
        cwd=str(PROJECT),
        stdout=log,
        stderr=log,
    )

    # Attendre que le serveur réponde
    for _ in range(20):
        time.sleep(1)
        try:
            urllib.request.urlopen(URL, timeout=1)
            return
        except Exception:
            pass


def main():
    start_server()

    try:
        import webview
        window = webview.create_window(
            title="⚡ Aegis Command Center",
            url=URL,
            width=1440,
            height=900,
            resizable=True,
            min_size=(900, 600),
            background_color="#060b14",
        )
        webview.start(debug=False)

    except ImportError:
        # Fallback : ouvrir dans Safari
        import subprocess
        subprocess.run(["open", URL])


if __name__ == "__main__":
    main()
