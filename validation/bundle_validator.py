import json
import os
import tempfile
import zipfile

from pathlib import PurePosixPath
try:
    from .validator import validate_race_zip, MAX_UNCOMPRESSED_SIZE
except ImportError:
    from validator import validate_race_zip, MAX_UNCOMPRESSED_SIZE


MAX_BUNDLE_SIZE = 100 * 1024 * 1024
MAX_TOTAL_SIZE = 500 * 1024 * 1024


def validate_bundle(bundle_path):
    report = {
        "bundle": os.path.basename(bundle_path),
        "status": "REJECTED",
        "total_races": 0,
        "validated_races": 0,
        "rejected_races": 0,
        "races": [],
        "errors": [],
        "warnings": []
    }

    if not os.path.isfile(bundle_path):
        report["errors"].append("Bundle file does not exist")
        return report

    if os.path.getsize(bundle_path) > MAX_BUNDLE_SIZE:
        report["errors"].append("Bundle exceeds 100 MB limit")
        return report

    if not zipfile.is_zipfile(bundle_path):
        report["errors"].append("Invalid season ZIP")
        return report

    try:
        with zipfile.ZipFile(bundle_path) as bundle:

            total_size = 0
            race_archives = []

            for info in bundle.infolist():
                name = info.filename
                path = PurePosixPath(name)

                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe ZIP path: " + name)

                if "\\" in name:
                    raise ValueError("Invalid ZIP path: " + name)

                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted ZIP entry: " + name)

                total_size += info.file_size

                if total_size > MAX_TOTAL_SIZE:
                    raise ValueError("Bundle exceeds extraction size limit")

                if name.lower().endswith(".zip") and not info.is_dir():
                    race_archives.append(name)

            bad_file = bundle.testzip()

            if bad_file:
                raise ValueError("Corrupt ZIP member: " + bad_file)

            if not race_archives:
                raise ValueError("No individual race ZIP files found")

            report["total_races"] = len(race_archives)

            seen_race_ids = set()
            seen_rounds = set()
            seen_names = set()

            for race_archive in sorted(race_archives):

                if race_archive in seen_names:
                    raise ValueError("Duplicate race archive: " + race_archive)

                seen_names.add(race_archive)

                data = bundle.read(race_archive)

                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as temp:
                    temp.write(data)
                    temp_path = temp.name

                try:
                    race_report = validate_race_zip(temp_path)
                    race_report["archive"] = race_archive

                finally:
                    os.unlink(temp_path)

                if race_report["status"] == "VALIDATED":

                    race = race_report.get("race", {})
                    race_id = race.get("race_id")
                    round_number = race.get("round")

                    if race_id in seen_race_ids:
                        race_report["errors"].append(
                            "Duplicate race_id across season bundle"
                        )
                        race_report["status"] = "REJECTED"

                    if round_number in seen_rounds:
                        race_report["errors"].append(
                            "Duplicate race round across season bundle"
                        )
                        race_report["status"] = "REJECTED"

                    if race_id:
                        seen_race_ids.add(race_id)

                    if round_number:
                        seen_rounds.add(round_number)

                report["races"].append(race_report)

                if race_report["status"] == "VALIDATED":
                    report["validated_races"] += 1
                else:
                    report["rejected_races"] += 1

            if report["validated_races"] == report["total_races"]:
                report["status"] = "VALIDATED"
            else:
                report["status"] = "REJECTED"

    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        report["errors"].append(str(exc))

    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate a complete F1 season ZIP bundle"
    )

    parser.add_argument("zip_path")

    parser.add_argument(
        "--report",
        default="validation/reports/season_validation.json"
    )

    args = parser.parse_args()

    report = validate_bundle(args.zip_path)

    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)

    with open(args.report, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print(json.dumps(report, indent=4))

    print("\nSEASON VALIDATION:", report["status"])
    print("Total races:", report["total_races"])
    print("Validated:", report["validated_races"])
    print("Rejected:", report["rejected_races"])

    if report["status"] != "VALIDATED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
