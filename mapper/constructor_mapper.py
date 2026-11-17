
#!/usr/bin/env python3

import sys

# Input format:
# Constructor_Name<TAB>Points

for line in sys.stdin:
    line = line.strip()

    if not line:
        continue

    try:
        constructor, points = line.split("\t")

        constructor = constructor.strip()
        points = int(points.strip())

        if constructor:
            print(f"{constructor}\t{points}")

    except ValueError:
        print(f"Invalid input: {line}", file=sys.stderr)
