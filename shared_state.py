"""
Shared state file — tous les agents lisent/écrivent ici.
Sert aussi de source de vérité pour le dashboard.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_PATH = "agent_state.json"

_DEFAULT = {
    "agents": {
        "MACRO":  {"status": "OFFLINE", "message": "", "last_seen": None},
        "SIGNAL": {"status": "OFFLINE", "message": "", "last_seen": None},
        "RISK":   {"status": "OFFLINE", "message": "", "last_seen": None},
        "EXEC":   {"status": "OFFLINE", "message": "", "last_seen": None},
        "MEMORY": {"status": "OFFLINE", "message": "", "last_seen": None},
    },
    "macro":  {},
    "signal": {},
    "exec":   {},
    "bot_running": False,
    "bot_pid": None,
}


def load_state() -> dict:
    p = Path(STATE_PATH)
    if not p.exists():
        save_state(_DEFAULT)
        return _DEFAULT.copy()
    with open(p) as f:
        return json.load(f)


def save_state(data: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def update_agent(name: str, status: str, message: str = ""):
    state = load_state()
    state["agents"][name] = {
        "status":    status,
        "message":   message,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)


def set_bot_running(pid: Optional[int]):
    state = load_state()
    state["bot_running"] = pid is not None
    state["bot_pid"]     = pid
    save_state(state)
