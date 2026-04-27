"""
MACRO Agent — surveille VIX, DXY, calendrier économique.
Écrit dans shared_state.json toutes les 4h.
"""
import os, sys, json, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from broker import get_positions
from shared_state import update_agent, load_state, save_state

INTERVAL = 14400  # 4 heures

HIGH_IMPACT_KEYWORDS = ["GDP", "NFP", "CPI", "FOMC", "PCE", "Fed", "Payroll", "Inflation"]

def run():
    update_agent("MACRO", "ACTIVE", "Démarrage scan macro...")
    while True:
        try:
            now = datetime.now(timezone.utc)
            state = load_state()

            # Placeholder — dans une version prod, on fetcherait un vrai calendrier éco
            # Pour l'instant on encode les événements connus cette semaine
            upcoming_events = [
                {"date": "2026-04-30", "event": "GDP Q1 1st Release", "impact": "HIGH"},
                {"date": "2026-04-30", "event": "PCE Deflator",        "impact": "HIGH"},
                {"date": "2026-05-01", "event": "NFP",                 "impact": "HIGH"},
            ]

            # Vérifier si on est dans les 24h d'un événement HIGH
            from datetime import timedelta
            danger_zone = False
            next_event = None
            for ev in upcoming_events:
                ev_dt = datetime.fromisoformat(ev["date"]).replace(tzinfo=timezone.utc)
                delta = (ev_dt - now).total_seconds() / 3600
                if 0 < delta < 24:
                    danger_zone = True
                    next_event = ev
                    break
                if delta > 0 and (next_event is None):
                    next_event = {**ev, "hours_away": round(delta, 1)}

            state["macro"] = {
                "last_updated": now.isoformat(),
                "danger_zone": danger_zone,
                "next_event": next_event,
                "upcoming_events": upcoming_events,
                "recommendation": "HOLD CASH — événement HIGH dans <24h" if danger_zone else "Clear — aucun événement imminent",
            }
            save_state(state)
            update_agent("MACRO", "IDLE", f"Prochain event: {next_event['event'] if next_event else 'aucun'}")

        except Exception as e:
            update_agent("MACRO", "ERROR", str(e))

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
