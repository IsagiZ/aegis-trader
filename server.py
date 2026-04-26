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
from agents.agent_macro import run as macro_run
from agents.agent_exec  import run as exec_run
from auto_scanner       import main as signal_run

for fn, name in [(macro_run, "MACRO"), (exec_run, "EXEC")]:
    t = threading.Thread(target=_run_agent, args=(fn, name), daemon=True)
    t.start()

# SIGNAL dans son propre thread (boucle principale)
signal_thread = threading.Thread(target=_run_agent, args=(signal_run, "SIGNAL"), daemon=True)
signal_thread.start()

# ── Démarrer Streamlit (processus principal) ───────────────────
port = os.environ.get("PORT", "8501")

proc = subprocess.Popen([
    sys.executable, "-m", "streamlit", "run", "dashboard.py",
    "--server.port",    port,
    "--server.address", "0.0.0.0",
    "--server.headless","true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
])

print(f"Aegis démarré sur port {port}", flush=True)
proc.wait()
