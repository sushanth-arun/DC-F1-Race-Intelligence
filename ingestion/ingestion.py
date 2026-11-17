import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

from pathlib import PurePosixPath

from validation.validator import validate_race_zip
from validation.bundle_validator import validate_bundle
from validation.validator import REQUIRED_FILES


HDFS_BASE = "/f1_data"
MAX_RACE_SIZE = 100 * 1024 * 1024


def run_hdfs(args):
    return subprocess.run(
        ["hdfs", "dfs"] + args,
        capture_output=True,
        text=True
    )


def hdfs_exists(path):
    result = run_hdfs(["-test", "-e", path])
    return result.returncode == 0


def safe_slug(filename):

    name = os.path.splitext(os.path.basename(filename))[0]

    name = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        name.lower()
    )

    if not name:
        raise ValueError("Invalid race archive name")

    return name


def extract_race(race_data, destination):

    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:

        temp.write(race_data)
        temp.flush()

        with zipfile.ZipFile(temp.name) as archive:

            if archive.testzip():
                raise ValueError("Corrupt individual race ZIP")

            found = {}

            for info in archive.infolist():

                if info.is_dir():
                    continue

                path = PurePosixPath(info.filename)

                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe archive path")

                if "\\" in info.filename:
                    raise ValueError("Invalid archive path")

                basename = path.name

                if basename not in REQUIRED_FILES:
                    continue

                if basename in found:
                    raise ValueError(
                        "Duplicate CSV file: " + basename
                    )

                found[basename] = info

            missing = set(REQUIRED_FILES) - set(found)

            if missing:
                raise ValueError(
                    "Missing CSV files: " + ", ".join(sorted(missing))
                )

            for filename, info in found.items():

                if info.file_size > MAX_RACE_SIZE:
                    raise ValueError("CSV exceeds size limit")

                output_path = os.path.join(destination, filename)

                with archive.open(info) as source:
                    with open(output_path, "wb") as output:
                        shutil.copyfileobj(source, output)


def ingest_bundle(bundle_path, season, dry_run=False):

    print("\nValidating season bundle...")

    report = validate_bundle(bundle_path)

    if report["status"] != "VALIDATED":
        raise ValueError("Season bundle validation failed")

    print("Validation successful")

    race_archives = [
        item["archive"]
        for item in report["races"]
    ]

    season_path = f"{HDFS_BASE}/raw/season={season}"
    upload_id = str(uuid.uuid4())

    if not dry_run and hdfs_exists(season_path):
        raise FileExistsError(
            "Season already exists in HDFS: " + season_path
        )

    with zipfile.ZipFile(bundle_path) as bundle:

        with tempfile.TemporaryDirectory() as temp:

            staging_local = os.path.join(temp, "season")
            os.makedirs(staging_local)

            race_names = set()

            for archive_name in race_archives:

                race_name = safe_slug(archive_name)

                if race_name in race_names:
                    raise ValueError(
                        "Duplicate race archive names: " + race_name
                    )

                race_names.add(race_name)

                race_directory = os.path.join(
                    staging_local,
                    "race=" + race_name
                )

                os.makedirs(race_directory)

                race_data = bundle.read(archive_name)

                extract_race(race_data, race_directory)

                print(
                    "Prepared:",
                    race_name,
                    "->",
                    len(REQUIRED_FILES),
                    "CSV files"
                )

            manifest = {
                "season": season,
                "upload_id": upload_id,
                "race_count": len(race_names),
                "races": sorted(race_names),
                "files_per_race": sorted(REQUIRED_FILES.keys())
            }

            with open(
                os.path.join(staging_local, "manifest.json"),
                "w"
            ) as file:
                json.dump(manifest, file, indent=4)

            if dry_run:

                print("\nDRY RUN SUCCESSFUL")
                print("Season:", season)
                print("Races:", len(race_names))
                print("Destination:", season_path)

                return manifest

            staging_root = f"{HDFS_BASE}/staging/{upload_id}"

            try:

                result = run_hdfs(["-mkdir", "-p", staging_root])

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

                # Upload the contents of staging_local directly.
                # This avoids an unwanted nested season directory.
                result = run_hdfs([
                    "-put",
                    staging_local + "/.",
                    staging_root + "/"
                ])

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

                final_parent = f"{HDFS_BASE}/raw"

                result = run_hdfs(["-mkdir", "-p", final_parent])

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

                result = run_hdfs([
                    "-mv",
                    staging_root,
                    season_path
                ])

                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

                print("\nHDFS INGESTION SUCCESSFUL")
                print("Destination:", season_path)

                return manifest

            except Exception:

                run_hdfs([
                    "-rm",
                    "-r",
                    "-f",
                    staging_root
                ])

                raise


def main():

    parser = argparse.ArgumentParser(
        description="F1 Season ZIP HDFS Ingestion"
    )

    parser.add_argument("zip_path")
    parser.add_argument("--season", required=True)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not re.fullmatch(r"\d{4}", args.season):
        raise SystemExit("Season must be a four-digit year")

    try:

        ingest_bundle(
            args.zip_path,
            args.season,
            args.dry_run
        )

    except Exception as exc:

        print("\nINGESTION FAILED:", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
