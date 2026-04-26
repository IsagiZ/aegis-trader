"""
Point d'entrée Render — démarre les agents + le dashboard Streamlit.
"""
import os
import sys
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


# ── Démarrer les agents en threads background ──────────────────
try:
    from agents.agent_macro import run as macro_run
    threading.Thread(target=_run_agent, args=(macro_run, "MACRO"), daemon=True).start()
except Exception as e:
    print(f"[MACRO] import error: {e}", flush=True)

try:
    from agents.agent_exec import run as exec_run
    threading.Thread(target=_run_agent, args=(exec_run, "EXEC"), daemon=True).start()
except Exception as e:
    print(f"[EXEC] import error: {e}", flush=True)

try:
    from auto_scanner import main as signal_run
    threading.Thread(target=_run_agent, args=(signal_run, "SIGNAL"), daemon=True).start()
except Exception as e:
    print(f"[SIGNAL] import error: {e}", flush=True)

# ── Démarrer Streamlit (processus principal) ───────────────────
port = os.environ.get("PORT", "8501")
print(f"Démarrage Streamlit sur port {port}...", flush=True)

proc = subprocess.Popen([
    sys.executable, "-m", "streamlit", "run", "dashboard.py",
    "--server.port",    str(port),
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--server.enableWebsocketCompression", "false",
])

print(f"Aegis actif sur port {port}", flush=True)
proc.wait()
