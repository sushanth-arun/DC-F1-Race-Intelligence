#!/usr/bin/env python3

import sys

current_id = None
driver_name = ""
total_points = 0.0
total_wins = 0
total_podiums = 0
total_races = 0

def emit():
    if current_id is not None:
        print(
            f"{current_id}\t{driver_name}\t"
            f"{total_points:g}\t{total_wins}\t"
            f"{total_podiums}\t{total_races}"
        )

for line in sys.stdin:
    parts = line.rstrip("\n").split("\t")

    if len(parts) != 6:
        continue

    driver_id, name, points, wins, podiums, races = parts

    try:
        points = float(points)
        wins = int(wins)
        podiums = int(podiums)
        races = int(races)
    except ValueError:
        continue

    if current_id != driver_id:
        emit()

        current_id = driver_id
        driver_name = name
        total_points = 0.0
        total_wins = 0
        total_podiums = 0
        total_races = 0

    total_points += points
    total_wins += wins
    total_podiums += podiums
    total_races += races

emit()
