import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import subprocess
from analytics.race_analytics import read_hdfs_csv

BASE = (
    "/f1_data/raw/races/season=2025/"
    "round=3_2025_03_JPN/race"
)

files = {
    "race": {
        "race": "race_results.csv",
        "qualifying": "qualifying_results.csv",
        "constructors": "constructor_standings.csv"
    },
    "laps": {
        "laps": "lap_times.csv",
        "race": "race_results.csv"
    },
    "pits": {
        "pits": "pit_stops.csv"
    },
    "fan": {
        "dotd": "driver_of_the_day.csv"
    }
}

os.makedirs("yarn_jobs/input", exist_ok=True)

for task, mapping in files.items():
    payload = {}

    for key, filename in mapping.items():
        payload[key] = read_hdfs_csv(BASE + "/" + filename)

    record = {"name": task, "data": payload}

    with open("yarn_jobs/input/" + task + ".json", "w") as f:
        f.write(json.dumps(record) + "\n")

    print("Prepared:", task)
