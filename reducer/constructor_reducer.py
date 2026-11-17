
#!/usr/bin/env python3

import sys

current_constructor = None
total_points = 0

for line in sys.stdin:
    line = line.strip()

    if not line:
        continue

    try:
        constructor, points = line.split("\t")
        points = int(points)

        if current_constructor == constructor:
            total_points += points

        else:
            if current_constructor is not None:
                print(f"{current_constructor}\t{total_points}")

            current_constructor = constructor
            total_points = points

    except ValueError:
        print(f"Invalid input: {line}", file=sys.stderr)

# Output the final constructor
if current_constructor is not None:
    print(f"{current_constructor}\t{total_points}")
