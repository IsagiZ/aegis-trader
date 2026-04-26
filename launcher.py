"""
Aegis Launcher — démarre/arrête tous les agents en parallèle.
Appelé par le dashboard Streamlit et par ligne de commande.
"""
import os
import sys
import signal
import subprocess
from pathlib import Path
from shared_state import load_state, save_state, set_bot_running, update_agent

BASE = Path(__file__).parent
PYTHON = sys.executable

AGENTS = {
    "SIGNAL": BASE / "auto_scanner.py",
    "EXEC":   BASE / "agents" / "agent_exec.py",
    "MACRO":  BASE / "agents" / "agent_macro.py",
}

PID_FILE = BASE / "pids.json"


def _save_pids(pids: dict):
    import json
    with open(PID_FILE, "w") as f:
        json.dump(pids, f)


def _load_pids() -> dict:
    import json
    if not PID_FILE.exists():
        return {}
    with open(PID_FILE) as f:
        return json.load(f)


def start_all():
    """Lance tous les agents en arrière-plan."""
    pids = {}
    for name, script in AGENTS.items():
        log = BASE / f"{name.lower()}_agent.log"
        proc = subprocess.Popen(
            [PYTHON, str(script)],
            stdout=open(log, "a"),
            stderr=subprocess.STDOUT,
            cwd=str(BASE),
        )
        pids[name] = proc.pid
        update_agent(name, "ACTIVE", "Démarré")
        print(f"  [{name}] PID {proc.pid} — log: {log.name}")

    _save_pids(pids)
    set_bot_running(pids.get("SIGNAL"))
    print("Tous les agents démarrés.")
    return pids


def stop_all():
    """Arrête tous les agents."""
    import json
    pids = _load_pids()
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            update_agent(name, "OFFLINE", "Arrêté")
            print(f"  [{name}] PID {pid} arrêté.")
        except ProcessLookupError:
            update_agent(name, "OFFLINE", "Déjà arrêté")
    _save_pids({})
    set_bot_running(None)
    print("Tous les agents arrêtés.")


def status() -> dict:
    """Retourne le statut de chaque agent."""
    import psutil
    pids = _load_pids()
    result = {}
    for name, pid in pids.items():
        try:
            p = psutil.Process(pid)
            result[name] = "RUNNING" if p.is_running() else "DEAD"
        except Exception:
            result[name] = "DEAD"
    return result


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start":
        start_all()
    elif cmd == "stop":
        stop_all()
    elif cmd == "status":
        print(status())
