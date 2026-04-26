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


# ── Agents en background ───────────────────────────────────────
for agent_name, module_path, fn_name in [
    ("MACRO",  "agents.agent_macro", "run"),
    ("EXEC",   "agents.agent_exec",  "run"),
    ("SIGNAL", "auto_scanner",       "main"),
]:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        fn  = getattr(mod, fn_name)
        threading.Thread(target=_run_agent, args=(fn, agent_name), daemon=True).start()
        print(f"[{agent_name}] thread lancé", flush=True)
    except Exception as e:
        print(f"[{agent_name}] import error: {e}", flush=True)

# ── Streamlit ──────────────────────────────────────────────────
port = os.environ.get("PORT", "8501")
print(f"Démarrage Streamlit sur port {port}...", flush=True)

os.execv(sys.executable, [
    sys.executable, "-m", "streamlit", "run", "dashboard.py",
    "--server.port",    str(port),
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--server.enableWebsocketCompression", "false",
])
