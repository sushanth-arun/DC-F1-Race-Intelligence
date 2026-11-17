import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid

from analytics.race_analytics import analyze_race as local_analyze
from analytics.race_analytics import read_hdfs_csv

WORKERS = {
    "race": os.environ.get("F1_WORKER_RACE", "http://127.0.0.1:5101"),
    "laps": os.environ.get("F1_WORKER_LAPS", "http://127.0.0.1:5102"),
    "pits": os.environ.get("F1_WORKER_PITS", "http://127.0.0.1:5103"),
    "fan": os.environ.get("F1_WORKER_FAN", "http://127.0.0.1:5104"),
}
TIMEOUT = int(os.environ.get("F1_WORKER_TIMEOUT", "180"))

def _hdfs_exists(path):
    return subprocess.run(
        ["hdfs", "dfs", "-test", "-e", path],
        capture_output=True
    ).returncode == 0

def _worker_call(name, task, data):
    body = json.dumps({"task": task, "data": data}).encode()
    request = urllib.request.Request(
        WORKERS[name] + "/process",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode())
    if "result" not in payload:
        raise RuntimeError("%s worker returned no result" % name)
    return payload["result"]

def _save_json_to_hdfs(path, payload):
    parent = path.rsplit("/", 1)[0]
    mkdir = subprocess.run(
        ["hdfs", "dfs", "-mkdir", "-p", parent],
        capture_output=True, text=True
    )
    if mkdir.returncode:
        raise RuntimeError("Could not create HDFS output directory: " + mkdir.stderr)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                     delete=False) as handle:
        json.dump(payload, handle, separators=(",", ":"))
        local_path = handle.name
    try:
        result = subprocess.run(
            ["hdfs", "dfs", "-put", "-f", local_path, path],
            capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError("Could not save worker result to HDFS: " + result.stderr)
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


def _run_yarn_workers(payloads):
    """Run the four Docker-backed tasks as one Hadoop Streaming application."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    mapper = os.path.join(project_dir, "yarn_jobs", "worker_mapper.py")
    streaming_jar = os.path.join(
        os.environ["HADOOP_HOME"],
        "share", "hadoop", "tools", "lib",
        "hadoop-streaming-3.5.0.jar"
    )

    if not os.path.isfile(mapper):
        raise FileNotFoundError("YARN mapper not found: " + mapper)
    if not os.path.isfile(streaming_jar):
        raise FileNotFoundError("Hadoop Streaming JAR not found: " + streaming_jar)

    job_tag = "f1_race_" + uuid.uuid4().hex[:12]
    hdfs_base = "/f1_data/yarn_jobs/" + job_tag
    hdfs_input = hdfs_base + "/input"
    hdfs_output = hdfs_base + "/output"

    with tempfile.TemporaryDirectory(prefix="f1_yarn_") as temp_dir:
        for name, data in payloads.items():
            local_file = os.path.join(temp_dir, name + ".json")
            with open(local_file, "w", encoding="utf-8") as handle:
                json.dump(
                    {"name": name, "data": data},
                    handle,
                    separators=(",", ":")
                )
                handle.write("\n")

        mkdir = subprocess.run(
            ["hdfs", "dfs", "-mkdir", "-p", hdfs_input],
            capture_output=True, text=True
        )
        if mkdir.returncode:
            raise RuntimeError("YARN input directory creation failed: " + mkdir.stderr)

        for name in payloads:
            local_file = os.path.join(temp_dir, name + ".json")
            put = subprocess.run(
                ["hdfs", "dfs", "-put", local_file, hdfs_input + "/"],
                capture_output=True, text=True
            )
            if put.returncode:
                raise RuntimeError("Could not upload YARN input: " + put.stderr)

        command = [
            "hadoop", "jar", streaming_jar,
            "-D", "mapreduce.job.name=F1_RACE_ANALYTICS_" + job_tag,
            "-files", mapper,
            "-input", hdfs_input,
            "-output", hdfs_output,
            "-mapper", "python3 worker_mapper.py",
            "-reducer", "NONE"
        ]

        print("Submitting YARN application:", job_tag, flush=True)
        submitted = subprocess.run(
            command, capture_output=True, text=True, timeout=900,
            cwd=project_dir
        )

        if submitted.stdout:
            print(submitted.stdout, flush=True)
        if submitted.returncode:
            raise RuntimeError(
                "YARN application failed.\n"
                + submitted.stderr[-12000:]
            )

        output = subprocess.run(
            ["hdfs", "dfs", "-cat", hdfs_output + "/part-*"],
            capture_output=True, text=True
        )
        if output.returncode:
            raise RuntimeError("Could not read YARN results: " + output.stderr)

        results = {}
        for line in output.stdout.splitlines():
            if not line.strip():
                continue
            name, separator, result_json = line.partition("\t")
            if not separator:
                raise RuntimeError("Unexpected YARN output record: " + line[:200])
            results[name] = json.loads(result_json)

        expected = {"race", "laps", "pits", "fan"}
        missing = expected - set(results)
        if missing:
            raise RuntimeError(
                "YARN completed but results are missing: " + ", ".join(sorted(missing))
            )

        print("YARN worker results collected:", ", ".join(sorted(results)), flush=True)
        print("YARN output directory:", hdfs_output, flush=True)
        return results


def analyze_race_parallel(hdfs_path):
    # Preserve support for both existing HDFS directory layouts.
    if not _hdfs_exists(hdfs_path.rstrip("/") + "/race_results.csv"):
        hdfs_path = hdfs_path.rstrip("/") + "/race"

    filenames = [
        "race_results.csv", "qualifying_results.csv", "pit_stops.csv",
        "lap_times.csv", "driver_of_the_day.csv", "constructor_standings.csv"
    ]
    paths = {name: hdfs_path.rstrip("/") + "/" + name for name in filenames}

    # Read from HDFS concurrently; HDFS remains the authoritative source.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {name: pool.submit(read_hdfs_csv, path)
                   for name, path in paths.items()}
        tables = {name: future.result() for name, future in futures.items()}

    if not tables["race_results.csv"]:
        raise ValueError("Race results CSV contains no records.")

    payloads = {
        "race": {
            "race": tables["race_results.csv"],
            "qualifying": tables["qualifying_results.csv"],
            "constructors": tables["constructor_standings.csv"]
        },
        "laps": {
            "laps": tables["lap_times.csv"],
            "race": tables["race_results.csv"]
        },
        "pits": {"pits": tables["pit_stops.csv"]},
        "fan": {"dotd": tables["driver_of_the_day.csv"]}
    }

    # Submit the four worker tasks through YARN when enabled.
    if os.environ.get("F1_USE_YARN", "0") == "1":
        results = _run_yarn_workers(payloads)
    else:
        # Existing direct Docker-worker mode remains available.
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    name: pool.submit(_worker_call, name, name, payload)
                    for name, payload in payloads.items()
                }
                results = {name: future.result() for name, future in futures.items()}
        except Exception as exc:
            if os.environ.get("F1_ALLOW_LOCAL_FALLBACK", "1") == "1":
                print(
                    "DOCKER WORKER FALLBACK: %s; using existing local analytics." % exc,
                    flush=True
                )
                return local_analyze(hdfs_path)
            raise

    race = results["race"]
    lap = results["laps"]
    pit = results["pits"]
    fan = results["fan"]

    analytics = {
        "race": race["race_meta"],
        "overview": {
            **race["overview"],
            "pit_stops": pit["pit_stop_count"]
        },
        "winner": race["winner"],
        "winner_team": race["winner_team"],
        "fastest_lap": lap["fastest_lap"],
        "best_pit_stop": pit["best_pit_stop"],
        "fan_favourite": fan["fan_favourite"],
        "biggest_gain": race["biggest_gain"],
        "biggest_loss": race["biggest_loss"],
        "pole": race["pole"],
        "driver_points": race["driver_points"],
        "constructor_points": race["constructor_points"],
        "finishing_positions": race["finishing_positions"],
        "position_gains": race["position_gains"],
        "pit_stops": pit["pit_stops"],
        "pit_stop_leaderboard": pit["pit_stop_leaderboard"],
        "lap_times": lap["lap_times"],
        "lap_trend": lap["lap_trend"],
        "tyre_usage": lap["tyre_usage"],
        "qualifying": race["qualifying"],
        "driver_of_the_day": fan["driver_of_the_day"],
        "constructor_standings": race["constructor_standings"],
        "race_results": race["race_results"],
        "consistency": lap["consistency"],
        "sector_data_available": False,
        "sector_message": "Sector times are not present in the uploaded six CSV files."
    }

    # Persist each worker's result and the final aggregate in HDFS.
    season = str(race["race_meta"]["season"])
    round_no = str(race["race_meta"]["round"])
    race_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(race["race_meta"]["race_id"]))
    output_base = "/f1_data/processed/races/season=%s/round=%s_%s" % (
        season, round_no, race_id
    )
    for name, result in results.items():
        _save_json_to_hdfs(output_base + "/workers/" + name + ".json", result)
    _save_json_to_hdfs(output_base + "/analytics.json", analytics)

    return analytics
