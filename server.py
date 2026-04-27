"""
Point d'entrée Render — démarre les agents + le dashboard Streamlit.
os.execv est évité — il tuerait tous les threads (Telegram, SIGNAL, etc.)
"""
import os
import sys
import time
import threading
import subprocess
from pathlib import Path

os.chdir(Path(__file__).parent)


def _run_agent(fn, name):
    try:
        print(f"[{name}] démarré", flush=True)
        fn()
    except Exception as e:
        print(f"[{name}] ERREUR: {e}", flush=True)


# ── Initialiser l'état au démarrage ───────────────────────────
try:
    from shared_state import update_agent, set_bot_running
    for a in ["MACRO", "SIGNAL", "EXEC", "TELEGRAM", "MEMORY"]:
        update_agent(a, "ACTIVE", "Démarré")
    set_bot_running(os.getpid())
except Exception as e:
    print(f"[STATE] init error: {e}", flush=True)

# ── Message Telegram de démarrage ──────────────────────────────
try:
    import telegram_notify as tg
    tg.startup()
except Exception as e:
    print(f"[TELEGRAM] startup error: {e}", flush=True)

# ── Agents en threads daemon ───────────────────────────────────
for agent_name, module_path, fn_name in [
    ("MACRO",    "agents.agent_macro", "run"),
    ("EXEC",     "agents.agent_exec",  "run"),
    ("SIGNAL",   "auto_scanner",       "main"),
    ("TELEGRAM", "telegram_bot",       "run"),
]:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        fn  = getattr(mod, fn_name)
        t   = threading.Thread(target=_run_agent, args=(fn, agent_name), daemon=True)
        t.start()
        print(f"[{agent_name}] thread lancé", flush=True)
    except Exception as e:
        print(f"[{agent_name}] import error: {e}", flush=True)

# ── Streamlit en subprocess (NE PAS utiliser os.execv) ─────────
port = os.environ.get("PORT", "8501")
print(f"Démarrage Streamlit sur port {port}...", flush=True)

proc = subprocess.Popen([
    sys.executable, "-m", "streamlit", "run", "dashboard.py",
    "--server.port",     str(port),
    "--server.address",  "0.0.0.0",
    "--server.headless", "true",
    "--server.enableCORS",                "false",
    "--server.enableXsrfProtection",      "false",
    "--server.enableWebsocketCompression","false",
])

print(f"Aegis actif — port {port}", flush=True)
proc.wait()
