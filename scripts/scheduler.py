"""Boucle de planification pour le conteneur `scheduler` (remplace les timers
systemd de deploy/ quand l'app tourne en Docker).

Déclenche :
- scraper.daily_transcripts   chaque jour à 06:30
- scraper.sync_members        chaque lundi à 05:00

Usage : python scripts/scheduler.py
"""
import subprocess
import sys
import time
from datetime import datetime

JOBS = [
    {"name": "daily_transcripts", "hour": 6, "minute": 30, "weekday": None,
     "module": "scraper.daily_transcripts"},
    {"name": "sync_members", "hour": 5, "minute": 0, "weekday": 0,
     "module": "scraper.sync_members"},
]


def run_job(module: str) -> None:
    print(f"[scheduler] {datetime.now().isoformat(timespec='seconds')} running {module}", flush=True)
    subprocess.run([sys.executable, "-m", module], check=False)


def is_due(job: dict, now: datetime) -> bool:
    if now.hour != job["hour"] or now.minute != job["minute"]:
        return False
    if job["weekday"] is not None and now.weekday() != job["weekday"]:
        return False
    return True


def main() -> None:
    print("[scheduler] started", flush=True)
    last_fired: dict[str, str] = {}
    while True:
        now = datetime.now()
        slot = now.strftime("%Y-%m-%d %H:%M")
        for job in JOBS:
            if is_due(job, now) and last_fired.get(job["name"]) != slot:
                last_fired[job["name"]] = slot
                run_job(job["module"])
        time.sleep(30)


if __name__ == "__main__":
    main()
