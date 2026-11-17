#!/usr/bin/env python3
import csv
import sys

reader = csv.reader(sys.stdin)

for row in reader:
    if not row or row[0].strip() == "race_id":
        continue

    if len(row) < 14:
        continue

    try:
        driver_id = row[0].strip()
        driver_name = row[7].strip()
        points = float(row[12] or 0)
        finish_position = row[11].strip()

        wins = 1 if finish_position == "1" else 0
        podiums = 1 if finish_position in ("1", "2", "3") else 0

        if driver_id and driver_name:
            print(
                f"{driver_id}\t{driver_name}\t"
                f"{points}\t{wins}\t{podiums}\t1"
            )

    except (ValueError, IndexError):
        continue
