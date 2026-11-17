import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import Counter, defaultdict

TASK = os.environ.get("WORKER_TASK", "")

def num(value, default=0.0):
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

def race_task(data):
    race = data["race"]
    qualifying = data["qualifying"]
    constructors = data["constructors"]

    results = [{
        "driver_id": row["driver_id"],
        "driver": row["driver_name"],
        "code": row.get("driver_code", ""),
        "constructor": row["constructor_name"],
        "grid": integer(row.get("grid_position")),
        "position": integer(row.get("finish_position")),
        "points": num(row.get("points")),
        "laps": integer(row.get("laps_completed")),
        "status": row.get("status", ""),
        "time": row.get("total_time_formatted", ""),
        "fastest_lap": row.get("fastest_lap_time_formatted", "")
    } for row in race]

    results.sort(key=lambda r: r["position"] if r["position"] > 0 else 999)
    winner = next((r for r in results if r["position"] == 1), None)

    driver_points = sorted(results, key=lambda r: r["points"], reverse=True)

    position_gains = []
    for row in results:
        if row["grid"] > 0 and row["position"] > 0:
            position_gains.append({
                "driver": row["driver"], "code": row["code"],
                "grid": row["grid"], "finish": row["position"],
                "gain": row["grid"] - row["position"]
            })
    position_gains.sort(key=lambda r: r["gain"], reverse=True)

    team_points = defaultdict(float)
    for row in results:
        team_points[row["constructor"]] += row["points"]
    team_chart = sorted(
        [{"team": team, "points": round(points, 2)}
         for team, points in team_points.items()],
        key=lambda r: r["points"], reverse=True
    )

    constructor_standings = sorted([{
        "team": row["constructor_name"],
        "race_points": num(row.get("race_points")),
        "cumulative_points": num(row.get("cumulative_points")),
        "position": integer(row.get("championship_position")),
        "wins": integer(row.get("cumulative_wins")),
        "podiums": integer(row.get("cumulative_podiums"))
    } for row in constructors],
      key=lambda r: r["position"] if r["position"] > 0 else 999)

    race_by_id = {r["driver_id"]: r for r in results}
    qualifying_rows = []
    for row in qualifying:
        race_row = race_by_id.get(row["driver_id"])
        qualifying_rows.append({
            "driver": row["driver_name"],
            "team": row["constructor_name"],
            "qualifying_position": integer(row.get("qualifying_position")),
            "qualifying_time": row.get("best_qualifying_time_formatted", ""),
            "qualifying_millis": integer(row.get("best_qualifying_time_millis")),
            "race_position": race_row["position"] if race_row else None,
            "gain": (integer(row.get("qualifying_position")) - race_row["position"]
                     if race_row and race_row["position"] > 0 else None),
            "pole": truth(row.get("is_pole_position"))
        })
    qualifying_rows.sort(
        key=lambda r: r["qualifying_position"]
        if r["qualifying_position"] > 0 else 999)
    pole = next((r for r in qualifying_rows if r["pole"]),
                qualifying_rows[0] if qualifying_rows else None)

    meta = race[0]
    return {
        "race_meta": {
            "race_id": meta["race_id"], "season": meta["season"],
            "round": meta["round"], "circuit_id": meta["circuit_id"]
        },
        "winner": winner["driver"] if winner else "Unavailable",
        "winner_team": winner["constructor"] if winner else "",
        "overview": {
            "winning_time": winner["time"] if winner else "Unavailable",
            "drivers": len(results), "constructors": len(team_points),
            "laps": sum(r["laps"] for r in results)
        },
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
        "biggest_gain": position_gains[0] if position_gains else None,
        "biggest_loss": min(position_gains, key=lambda r: r["gain"])
                        if position_gains else None,
        "constructor_standings": constructor_standings,
        "qualifying": qualifying_rows,
        "pole": pole,
        "race_results": results
    }

def lap_task(data):
    laps = data["laps"]
    race = data["race"]
    lap_by_driver = defaultdict(list)
    lap_by_number = defaultdict(list)
    tyre_usage = Counter()
    fastest_laps = []

    for row in laps:
        seconds = num(row.get("lap_time_seconds"))
        lap_no = integer(row.get("lap_number"))
        if row.get("tyre_compound"):
            tyre_usage[row["tyre_compound"]] += 1
        if seconds <= 0:
            continue
        lap_by_driver[row["driver_name"]].append(seconds)
        if lap_no > 0:
            lap_by_number[lap_no].append(seconds)
        if truth(row.get("is_fastest_lap")):
            fastest_laps.append({
                "driver": row["driver_name"],
                "team": row["constructor_name"],
                "lap": lap_no,
                "seconds": seconds,
                "time": row.get("lap_time_formatted", "")
            })

    lap_averages = sorted([{
        "driver": driver, "average": round(sum(times) / len(times), 3),
        "laps": len(times)
    } for driver, times in lap_by_driver.items()],
      key=lambda r: r["average"])

    leading_names = [r["driver_name"] for r in sorted(
        race, key=lambda r: integer(r.get("finish_position"))
        if integer(r.get("finish_position")) > 0 else 999)[:5]]
    lap_trend = []
    for driver in leading_names:
        by_lap = {}
        for row in laps:
            if row["driver_name"] == driver:
                lap_no = integer(row.get("lap_number"))
                seconds = num(row.get("lap_time_seconds"))
                if lap_no > 0 and seconds > 0:
                    by_lap[lap_no] = seconds
        lap_trend.append({"driver": driver, "values": by_lap})

    lap_numbers = sorted(lap_by_number)
    lap_series = {
        "labels": lap_numbers,
        "datasets": [{
            "label": item["driver"],
            "values": [item["values"].get(lap_no) for lap_no in lap_numbers]
        } for item in lap_trend]
    }

    consistency = []
    for driver, times in lap_by_driver.items():
        if len(times) >= 2:
            mean = sum(times) / len(times)
            variance = sum((x - mean) ** 2 for x in times) / len(times)
            consistency.append({
                "driver": driver, "average": round(mean, 3),
                "deviation": round(variance ** 0.5, 3), "laps": len(times)
            })
    consistency.sort(key=lambda r: r["deviation"])

    fastest = min(fastest_laps, key=lambda r: r["seconds"]) if fastest_laps else None
    return {
        "fastest_lap": fastest,
        "lap_times": {
            "labels": [r["driver"] for r in lap_averages],
            "values": [r["average"] for r in lap_averages]
        },
        "lap_trend": lap_series,
        "tyre_usage": {"labels": list(tyre_usage), "values": list(tyre_usage.values())},
        "consistency": consistency
    }

def pit_task(data):
    pits = data["pits"]
    pit_rows = []
    for row in pits:
        stationary = num(row.get("stationary_duration_seconds"))
        total = num(row.get("duration_seconds"))
        pit_rows.append({
            "driver": row["driver_name"], "team": row["constructor_name"],
            "stop": integer(row.get("stop_number")),
            "lap": integer(row.get("lap_number")),
            "stationary": stationary, "duration": total,
            "tyre_in": row.get("compound_in", ""),
            "tyre_out": row.get("compound_out", "")
        })
    pit_rows.sort(key=lambda r: r["stationary"] if r["stationary"] > 0 else 999)
    best = pit_rows[0] if pit_rows else None
    by_driver = defaultdict(list)
    for row in pit_rows:
        if row["stationary"] > 0:
            by_driver[row["driver"]].append(row["stationary"])
    averages = sorted([{
        "driver": driver, "average": round(sum(times) / len(times), 3),
        "stops": len(times)
    } for driver, times in by_driver.items()], key=lambda r: r["average"])
    return {
        "best_pit_stop": best,
        "pit_stops": {
            "labels": [r["driver"] for r in averages],
            "values": [r["average"] for r in averages]
        },
        "pit_stop_leaderboard": pit_rows,
        "pit_stop_count": len(pit_rows)
    }

def fan_task(data):
    rows = data["dotd"]
    votes = sorted([{
        "driver": row["driver_name"], "team": row["constructor_name"],
        "votes": integer(row.get("votes")),
        "percentage": num(row.get("vote_percentage")),
        "position": integer(row.get("voting_position")),
        "winner": truth(row.get("is_dotd_winner"))
    } for row in rows], key=lambda r: r["votes"], reverse=True)
    favourite = next((r for r in votes if r["winner"]),
                     votes[0] if votes else None)
    return {"fan_favourite": favourite, "driver_of_the_day": votes}

TASKS = {
    "race": race_task,
    "laps": lap_task,
    "pits": pit_task,
    "fan": fan_task
}

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"status": "healthy", "task": TASK})
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/process":
            return self.send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100 * 1024 * 1024:
                return self.send_json(413, {"error": "invalid payload size"})
            payload = json.loads(self.rfile.read(length))
            task = payload.get("task")
            if task != TASK or task not in TASKS:
                return self.send_json(400, {"error": "task does not match worker"})
            result = TASKS[task](payload.get("data", {}))
            return self.send_json(200, {"worker": TASK, "result": result})
        except Exception as exc:
            return self.send_json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("[%s] %s" % (TASK, fmt % args), flush=True)

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    print("Worker %s listening on :8000" % TASK, flush=True)
    server.serve_forever()
