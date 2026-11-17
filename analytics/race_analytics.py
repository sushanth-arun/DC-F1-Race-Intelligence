import csv
import io
import subprocess
from collections import Counter, defaultdict


def number(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def integer(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def truth(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def read_hdfs_csv(path):
    result = subprocess.run(
        ["hdfs", "dfs", "-cat", path],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not read {path}: {result.stderr.strip()}"
        )
    return list(csv.DictReader(io.StringIO(result.stdout)))


def chart(rows, label_key, value_key, limit=None):
    selected = rows[:limit] if limit else rows
    return {
        "labels": [str(row.get(label_key, "")) for row in selected],
        "values": [number(row.get(value_key)) for row in selected]
    }


def analyze_race(hdfs_path):
    # Support both HDFS directory layouts.
    check = subprocess.run(
        ["hdfs", "dfs", "-test", "-e", hdfs_path + "/race_results.csv"]
    )
    if check.returncode != 0:
        hdfs_path = hdfs_path.rstrip("/") + "/race"

    race = read_hdfs_csv(hdfs_path + "/race_results.csv")
    qualifying = read_hdfs_csv(hdfs_path + "/qualifying_results.csv")
    pits = read_hdfs_csv(hdfs_path + "/pit_stops.csv")
    laps = read_hdfs_csv(hdfs_path + "/lap_times.csv")
    dotd = read_hdfs_csv(hdfs_path + "/driver_of_the_day.csv")
    constructors = read_hdfs_csv(hdfs_path + "/constructor_standings.csv")

    if not race:
        raise ValueError("Race results CSV contains no records.")

    # Main race classification.
    results = []
    for row in race:
        results.append({
            "driver_id": row["driver_id"],
            "driver": row["driver_name"],
            "code": row.get("driver_code", ""),
            "constructor": row["constructor_name"],
            "grid": integer(row.get("grid_position")),
            "position": integer(row.get("finish_position")),
            "points": number(row.get("points")),
            "laps": integer(row.get("laps_completed")),
            "status": row.get("status", ""),
            "time": row.get("total_time_formatted", ""),
            "fastest_lap": row.get("fastest_lap_time_formatted", "")
        })

    results.sort(
        key=lambda r: r["position"] if r["position"] > 0 else 999
    )

    winner = next(
        (r for r in results if r["position"] == 1), None
    )

    # Driver points and position gain.
    driver_points = sorted(
        results, key=lambda r: r["points"], reverse=True
    )

    position_gains = []
    for row in results:
        if row["grid"] > 0 and row["position"] > 0:
            position_gains.append({
                "driver": row["driver"],
                "code": row["code"],
                "grid": row["grid"],
                "finish": row["position"],
                "gain": row["grid"] - row["position"]
            })

    position_gains.sort(key=lambda r: r["gain"], reverse=True)
    biggest_gain = position_gains[0] if position_gains else None
    biggest_loss = (
        min(position_gains, key=lambda r: r["gain"])
        if position_gains else None
    )

    # Constructor points and championship position.
    team_points = defaultdict(float)
    for row in results:
        team_points[row["constructor"]] += row["points"]

    team_chart = sorted(
        [{"team": team, "points": round(points, 2)}
         for team, points in team_points.items()],
        key=lambda r: r["points"],
        reverse=True
    )

    constructor_standings = sorted(
        [{
            "team": row["constructor_name"],
            "race_points": number(row.get("race_points")),
            "cumulative_points": number(row.get("cumulative_points")),
            "position": integer(row.get("championship_position")),
            "wins": integer(row.get("cumulative_wins")),
            "podiums": integer(row.get("cumulative_podiums"))
        } for row in constructors],
        key=lambda r: r["position"] if r["position"] > 0 else 999
    )

    # Fan vote / Driver of the Day.
    fan_votes = sorted(
        [{
            "driver": row["driver_name"],
            "team": row["constructor_name"],
            "votes": integer(row.get("votes")),
            "percentage": number(row.get("vote_percentage")),
            "position": integer(row.get("voting_position")),
            "winner": truth(row.get("is_dotd_winner"))
        } for row in dotd],
        key=lambda r: r["votes"],
        reverse=True
    )
    fan_favourite = next(
        (r for r in fan_votes if r["winner"]),
        fan_votes[0] if fan_votes else None
    )

    # Pit stop analysis. Stationary time represents the actual stop.
    pit_rows = []
    for row in pits:
        stationary = number(row.get("stationary_duration_seconds"))
        total = number(row.get("duration_seconds"))
        pit_rows.append({
            "driver": row["driver_name"],
            "team": row["constructor_name"],
            "stop": integer(row.get("stop_number")),
            "lap": integer(row.get("lap_number")),
            "stationary": stationary,
            "duration": total,
            "tyre_in": row.get("compound_in", ""),
            "tyre_out": row.get("compound_out", "")
        })

    pit_rows.sort(
        key=lambda r: r["stationary"] if r["stationary"] > 0 else 999
    )
    best_pit = pit_rows[0] if pit_rows else None

    pit_by_driver = defaultdict(list)
    for row in pit_rows:
        if row["stationary"] > 0:
            pit_by_driver[row["driver"]].append(row["stationary"])

    pit_averages = sorted(
        [{
            "driver": driver,
            "average": round(sum(times) / len(times), 3),
            "stops": len(times)
        } for driver, times in pit_by_driver.items()],
        key=lambda r: r["average"]
    )

    # Lap pace: average lap time per driver and lap-by-lap trend.
    lap_by_driver = defaultdict(list)
    lap_by_number = defaultdict(list)
    tyre_usage = Counter()
    fastest_laps = []

    for row in laps:
        seconds = number(row.get("lap_time_seconds"))
        lap_number = integer(row.get("lap_number"))

        if row.get("tyre_compound"):
            tyre_usage[row["tyre_compound"]] += 1

        if seconds <= 0:
            continue

        lap_by_driver[row["driver_name"]].append(seconds)

        if lap_number > 0:
            lap_by_number[lap_number].append(seconds)

        if truth(row.get("is_fastest_lap")):
            fastest_laps.append({
                "driver": row["driver_name"],
                "team": row["constructor_name"],
                "lap": lap_number,
                "seconds": seconds,
                "time": row.get("lap_time_formatted", "")
            })

    lap_averages = sorted(
        [{
            "driver": driver,
            "average": round(sum(times) / len(times), 3),
            "laps": len(times)
        } for driver, times in lap_by_driver.items()],
        key=lambda r: r["average"]
    )

    # Keep the lap trend readable: show the five leading finishers.
    leading_names = [r["driver"] for r in results[:5]]
    lap_trend = []
    for driver in leading_names:
        by_lap = {}
        for row in laps:
            if row["driver_name"] == driver:
                lap_no = integer(row.get("lap_number"))
                seconds = number(row.get("lap_time_seconds"))
                if lap_no > 0 and seconds > 0:
                    by_lap[lap_no] = seconds

        lap_trend.append({
            "driver": driver,
            "values": by_lap
        })

    lap_numbers = sorted(lap_by_number)
    lap_series = {
        "labels": lap_numbers,
        "datasets": [
            {
                "label": item["driver"],
                "values": [
                    item["values"].get(lap_no)
                    for lap_no in lap_numbers
                ]
            }
            for item in lap_trend
        ]
    }

    fastest_lap = (
        min(fastest_laps, key=lambda r: r["seconds"])
        if fastest_laps else None
    )

    # Qualifying vs race finish.
    qualifying_rows = []
    race_by_id = {r["driver_id"]: r for r in results}

    for row in qualifying:
        race_row = race_by_id.get(row["driver_id"])
        qualifying_rows.append({
            "driver": row["driver_name"],
            "team": row["constructor_name"],
            "qualifying_position": integer(
                row.get("qualifying_position")
            ),
            "qualifying_time": row.get(
                "best_qualifying_time_formatted", ""
            ),
            "qualifying_millis": integer(
                row.get("best_qualifying_time_millis")
            ),
            "race_position": race_row["position"] if race_row else None,
            "gain": (
                integer(row.get("qualifying_position"))
                - race_row["position"]
                if race_row and race_row["position"] > 0 else None
            ),
            "pole": truth(row.get("is_pole_position"))
        })

    qualifying_rows.sort(
        key=lambda r: r["qualifying_position"]
        if r["qualifying_position"] > 0 else 999
    )

    pole = next(
        (r for r in qualifying_rows if r["pole"]),
        qualifying_rows[0] if qualifying_rows else None
    )

    # Consistency: standard deviation of valid lap times.
    consistency = []
    for driver, times in lap_by_driver.items():
        if len(times) >= 2:
            mean = sum(times) / len(times)
            variance = sum((x - mean) ** 2 for x in times) / len(times)
            consistency.append({
                "driver": driver,
                "average": round(mean, 3),
                "deviation": round(variance ** 0.5, 3),
                "laps": len(times)
            })
    consistency.sort(key=lambda r: r["deviation"])

    metadata = race[0]

    return {
        "race": {
            "race_id": metadata["race_id"],
            "season": metadata["season"],
            "round": metadata["round"],
            "circuit_id": metadata["circuit_id"]
        },
        "overview": {
            "winning_time": winner["time"] if winner else "Unavailable",
            "drivers": len(results),
            "constructors": len(team_points),
            "laps": sum(r["laps"] for r in results),
            "pit_stops": len(pit_rows)
        },
        "winner": winner["driver"] if winner else "Unavailable",
        "winner_team": winner["constructor"] if winner else "",
        "fastest_lap": fastest_lap,
        "best_pit_stop": best_pit,
        "fan_favourite": fan_favourite,
        "biggest_gain": biggest_gain,
        "biggest_loss": biggest_loss,
        "pole": pole,
        "driver_points": {
            "labels": [r["driver"] for r in driver_points],
            "values": [r["points"] for r in driver_points]
        },
        "constructor_points": {
            "labels": [r["team"] for r in team_chart],
            "values": [r["points"] for r in team_chart]
        },
        "finishing_positions": {
            "labels": [r["driver"] for r in results],
            "values": [r["position"] for r in results]
        },
        "position_gains": {
            "labels": [r["driver"] for r in position_gains],
            "values": [r["gain"] for r in position_gains]
        },
        "pit_stops": {
            "labels": [r["driver"] for r in pit_averages],
            "values": [r["average"] for r in pit_averages]
        },
        "pit_stop_leaderboard": pit_rows,
        "lap_times": {
            "labels": [r["driver"] for r in lap_averages],
            "values": [r["average"] for r in lap_averages]
        },
        "lap_trend": lap_series,
        "tyre_usage": {
            "labels": list(tyre_usage.keys()),
            "values": list(tyre_usage.values())
        },
        "qualifying": qualifying_rows,
        "driver_of_the_day": fan_votes,
        "constructor_standings": constructor_standings,
        "race_results": results,
        "consistency": consistency,
        "sector_data_available": False,
        "sector_message": (
            "Sector times are not present in the uploaded six CSV files."
        )
    }
