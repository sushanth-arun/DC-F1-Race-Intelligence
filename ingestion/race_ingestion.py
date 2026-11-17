import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

from pathlib import PurePosixPath
from validation.validator import validate_race_zip, REQUIRED_FILES

HDFS_BASE = "/f1_data"


def run_hdfs(args):
    return subprocess.run(
        ["hdfs", "dfs"] + args,
        capture_output=True,
        text=True
    )


def safe_name(value):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip())
    return value.strip("_") or "unknown"


def ingest_race(zip_path):
    print("Validating single-race ZIP...")

    report = validate_race_zip(zip_path)

    if report["status"] != "VALIDATED":
        raise ValueError(
            "Race validation failed: " +
            "; ".join(report["errors"])
        )

    race = report["race"]
    season = race["season"]
    round_number = race["round"]
    race_id = safe_name(race["race_id"])

    race_name = f"round={round_number}_{race_id}"
    destination = (
        f"{HDFS_BASE}/raw/races/season={season}/{race_name}"
    )

    check = run_hdfs(["-test", "-e", destination])
    if check.returncode == 0:
        print("Race already exists. Reusing HDFS data:", destination)
        return {
            "race": race,
            "hdfs_path": destination,
            "files": sorted(REQUIRED_FILES.keys()),
            "status": "EXISTS"
        }

    upload_id = str(uuid.uuid4())
    staging = f"{HDFS_BASE}/staging/{upload_id}"

    try:
        with tempfile.TemporaryDirectory() as temp:
            extracted = os.path.join(temp, "race")
            os.makedirs(extracted)

            with zipfile.ZipFile(zip_path) as archive:
                found = {}

                for info in archive.infolist():
                    if info.is_dir():
                        continue

                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("Unsafe ZIP path")

                    if "\\" in info.filename:
                        raise ValueError("Invalid ZIP path")

                    basename = path.name
                    if basename in REQUIRED_FILES:
                        if basename in found:
                            raise ValueError(
                                "Duplicate CSV: " + basename
                            )
                        found[basename] = info

                missing = set(REQUIRED_FILES) - set(found)
                if missing:
                    raise ValueError(
                        "Missing CSV files: " +
                        ", ".join(sorted(missing))
                    )

                for filename, info in found.items():
                    output_path = os.path.join(extracted, filename)
                    with archive.open(info) as source:
                        with open(output_path, "wb") as output:
                            shutil.copyfileobj(source, output)

            manifest = {
                "race": race,
                "hdfs_path": destination,
                "files": sorted(REQUIRED_FILES.keys()),
                "validation_status": report["status"]
            }

            with open(
                os.path.join(extracted, "manifest.json"),
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(manifest, file, indent=4)

            result = run_hdfs(["-mkdir", "-p", staging])
            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            result = run_hdfs([
                "-put", extracted + "/.", staging + "/"
            ])
            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            parent = os.path.dirname(destination)
            result = run_hdfs(["-mkdir", "-p", parent])
            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            result = run_hdfs(["-mv", staging, destination])
            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            print("RACE INGESTION SUCCESSFUL:", destination)

            return {
                "race": race,
                "hdfs_path": destination,
                "files": sorted(REQUIRED_FILES.keys()),
                "status": "INGESTED"
            }

    except Exception:
        run_hdfs(["-rm", "-r", "-f", staging])
        raise
