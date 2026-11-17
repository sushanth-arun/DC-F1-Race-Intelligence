import csv
import io
import json
import os
import re
import stat
import tempfile
import zipfile

from pathlib import PurePosixPath
from collections import Counter


REQUIRED_FILES = {
    "race_results.csv": [
        "race_id", "season", "round", "circuit_id",
        "driver_id", "driver_number", "driver_code",
        "driver_name", "constructor_id", "constructor_name",
        "grid_position", "finish_position", "points",
        "laps_completed", "status", "total_time_millis",
        "total_time_formatted", "fastest_lap_time_millis",
        "fastest_lap_time_formatted", "fastest_lap_rank",
        "fastest_lap_point", "is_winner", "is_podium",
        "data_origin"
    ],

    "qualifying_results.csv": [
        "race_id", "season", "round", "circuit_id",
        "driver_id", "driver_number", "driver_code",
        "driver_name", "constructor_id", "constructor_name",
        "qualifying_position", "q1_time_millis",
        "q1_time_formatted", "q2_time_millis",
        "q2_time_formatted", "q3_time_millis",
        "q3_time_formatted", "best_qualifying_time_millis",
        "best_qualifying_time_formatted",
        "is_pole_position", "data_origin"
    ],

    "pit_stops.csv": [
        "race_id", "season", "round", "circuit_id",
        "driver_id", "driver_number", "driver_code",
        "driver_name", "constructor_id", "constructor_name",
        "stop_number", "lap_number", "duration_seconds",
        "duration_millis", "stationary_duration_seconds",
        "compound_in", "compound_out", "data_origin"
    ],

    "lap_times.csv": [
        "race_id", "season", "round", "circuit_id",
        "driver_id", "driver_number", "driver_code",
        "driver_name", "constructor_id", "constructor_name",
        "lap_number", "lap_time_millis", "lap_time_seconds",
        "lap_time_formatted", "running_position",
        "tyre_compound", "tyre_age_laps", "is_pit_lap",
        "is_personal_best", "is_fastest_lap", "data_origin"
    ],

    "driver_of_the_day.csv": [
        "race_id", "season", "round", "circuit_id",
        "driver_id", "driver_number", "driver_code",
        "driver_name", "constructor_id", "constructor_name",
        "votes", "vote_percentage", "voting_position",
        "is_dotd_winner", "data_origin"
    ],

    "constructor_standings.csv": [
        "race_id", "season", "round", "circuit_id",
        "constructor_id", "constructor_name",
        "race_points", "cumulative_points",
        "championship_position", "cumulative_wins",
        "cumulative_podiums", "data_origin"
    ]
}

MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 250 * 1024 * 1024

NUMERIC_FIELDS = {
    "season", "round", "grid_position", "finish_position",
    "points", "laps_completed", "total_time_millis",
    "fastest_lap_time_millis", "fastest_lap_rank",
    "fastest_lap_point", "qualifying_position",
    "q1_time_millis", "q2_time_millis", "q3_time_millis",
    "best_qualifying_time_millis", "stop_number",
    "lap_number", "duration_seconds", "duration_millis",
    "stationary_duration_seconds", "lap_time_millis",
    "lap_time_seconds", "running_position",
    "tyre_age_laps", "votes", "vote_percentage",
    "voting_position", "race_points", "cumulative_points",
    "championship_position", "cumulative_wins",
    "cumulative_podiums"
}

OPTIONAL_NUMERIC_FIELDS = {
    "grid_position", "finish_position", "total_time_millis",
    "fastest_lap_time_millis", "fastest_lap_rank",
    "q1_time_millis", "q2_time_millis", "q3_time_millis",
    "best_qualifying_time_millis", "running_position",
    "tyre_age_laps"
}

BOOLEAN_FIELDS = {
    "is_winner", "is_podium", "is_pole_position",
    "is_dotd_winner", "is_pit_lap",
    "is_personal_best", "is_fastest_lap"
}

VALID_BOOLEAN = {"true", "false", "1", "0"}


class ValidationError(Exception):
    pass


def add_error(errors, message):
    errors.append(message)


def read_csv_from_zip(archive, member, errors):
    try:
        raw = archive.read(member)
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            add_error(errors, f"{member}: missing CSV header")
            return []

        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            add_error(errors, f"{member}: duplicate column names")

        expected = REQUIRED_FILES[os.path.basename(member)]
        missing = sorted(set(expected) - set(reader.fieldnames))

        if missing:
            add_error(
                errors,
                f"{member}: missing columns: {', '.join(missing)}"
            )

        rows = []

        for line_number, row in enumerate(reader, start=2):
            if None in row:
                add_error(
                    errors,
                    f"{member}: extra CSV fields at line {line_number}"
                )
                continue

            if not any((value or "").strip() for value in row.values()):
                continue

            rows.append(row)

        return rows

    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        add_error(errors, f"{member}: cannot read CSV: {exc}")
        return []


def validate_zip_safety(zip_path):
    if not os.path.isfile(zip_path):
        raise ValidationError("ZIP file does not exist")

    if os.path.getsize(zip_path) > MAX_ARCHIVE_SIZE:
        raise ValidationError("ZIP exceeds 100 MB upload limit")

    if not zipfile.is_zipfile(zip_path):
        raise ValidationError("File is not a valid ZIP archive")

    with zipfile.ZipFile(zip_path) as archive:
        total_size = 0
        csv_members = []

        for info in archive.infolist():
            name = info.filename
            path = PurePosixPath(name)

            if path.is_absolute() or ".." in path.parts:
                raise ValidationError(
                    f"Unsafe archive path: {name}"
                )

            if "\\" in name:
                raise ValidationError(
                    f"Invalid archive path: {name}"
                )

            mode = info.external_attr >> 16

            if stat.S_ISLNK(mode):
                raise ValidationError(
                    f"Symbolic links are not permitted: {name}"
                )

            if info.flag_bits & 0x1:
                raise ValidationError(
                    "Encrypted ZIP entries are not supported"
                )

            if info.is_dir():
                continue

            total_size += info.file_size

            if total_size > MAX_UNCOMPRESSED_SIZE:
                raise ValidationError(
                    "Extracted archive exceeds 250 MB limit"
                )

            if name.lower().endswith(".csv"):
                csv_members.append(name)

        bad_member = archive.testzip()

        if bad_member:
            raise ValidationError(
                f"Corrupt ZIP member: {bad_member}"
            )

        return csv_members


def check_numeric_fields(filename, rows, errors):
    for index, row in enumerate(rows, start=2):
        for field in NUMERIC_FIELDS:
            if field not in row:
                continue

            value = (row[field] or "").strip()

            if not value:
                if field not in OPTIONAL_NUMERIC_FIELDS:
                    add_error(
                        errors,
                        f"{filename}, line {index}: "
                        f"{field} is empty"
                    )
                continue

            try:
                number = float(value)

                if not __import__("math").isfinite(number):
                    raise ValueError()

            except ValueError:
                add_error(
                    errors,
                    f"{filename}, line {index}: "
                    f"{field} is not a valid number"
                )

        for field in BOOLEAN_FIELDS:
            if field not in row:
                continue

            value = (row[field] or "").strip().lower()

            if value not in VALID_BOOLEAN:
                add_error(
                    errors,
                    f"{filename}, line {index}: "
                    f"invalid boolean in {field}: {value}"
                )


def check_metadata(all_rows, errors):
    reference = None

    for filename, rows in all_rows.items():
        for index, row in enumerate(rows, start=2):
            current = (
                row.get("race_id"),
                row.get("season"),
                row.get("round"),
                row.get("circuit_id")
            )

            if not all(current):
                add_error(
                    errors,
                    f"{filename}, line {index}: "
                    "missing race metadata"
                )
                continue

            if reference is None:
                reference = current
            elif current != reference:
                add_error(
                    errors,
                    f"{filename}, line {index}: "
                    "race metadata does not match other CSV files"
                )

    return reference


def check_relations(all_rows, errors):
    race = all_rows.get("race_results.csv", [])
    qualifying = all_rows.get("qualifying_results.csv", [])
    pits = all_rows.get("pit_stops.csv", [])
    laps = all_rows.get("lap_times.csv", [])
    dotd = all_rows.get("driver_of_the_day.csv", [])
    constructors = all_rows.get("constructor_standings.csv", [])

    race_drivers = [r.get("driver_id") for r in race]
    race_teams = [r.get("constructor_id") for r in race]

    if len(race_drivers) != len(set(race_drivers)):
        add_error(errors, "Duplicate driver in race_results.csv")

    if len(race_teams) != len(set(race_teams)):
        # Multiple drivers can share a constructor.
        # This is not necessarily an error.
        pass

    driver_ids = set(race_drivers)
    constructor_ids = set(race_teams)

    for filename, rows in [
        ("qualifying_results.csv", qualifying),
        ("pit_stops.csv", pits),
        ("lap_times.csv", laps),
        ("driver_of_the_day.csv", dotd)
    ]:
        for row in rows:
            if row.get("driver_id") not in driver_ids:
                add_error(
                    errors,
                    f"{filename}: unknown driver_id "
                    f"{row.get('driver_id')}"
                )

            if row.get("constructor_id") not in constructor_ids:
                add_error(
                    errors,
                    f"{filename}: unknown constructor_id "
                    f"{row.get('constructor_id')}"
                )

    if len({r.get("driver_id") for r in qualifying}) != len(qualifying):
        add_error(errors, "Duplicate driver in qualifying results")

    if len({r.get("driver_id") for r in dotd}) != len(dotd):
        add_error(errors, "Duplicate driver in DOTD results")

    if len({r.get("constructor_id") for r in constructors}) != len(constructors):
        add_error(errors, "Duplicate constructor in standings")

    winners = [
        r for r in race
        if (r.get("is_winner") or "").strip().lower() == "true"
    ]

    if len(winners) != 1 and race:
        add_error(
            errors,
            f"Expected one race winner, found {len(winners)}"
        )

    dotd_winners = [
        r for r in dotd
        if (r.get("is_dotd_winner") or "").strip().lower() == "true"
    ]

    if len(dotd_winners) != 1 and dotd:
        add_error(
            errors,
            f"Expected one DOTD winner, found {len(dotd_winners)}"
        )

    if race and len(constructors) == 0:
        add_error(errors, "Constructor standings are empty")


def validate_race_zip(zip_path):
    report = {
        "archive": os.path.basename(zip_path),
        "status": "REJECTED",
        "files": {},
        "errors": [],
        "warnings": [],
        "race": {},
        "provenance": {}
    }

    try:
        csv_members = validate_zip_safety(zip_path)

        by_basename = {}

        for member in csv_members:
            basename = os.path.basename(member)

            if basename in REQUIRED_FILES:
                if basename in by_basename:
                    raise ValidationError(
                        f"Duplicate required CSV: {basename}"
                    )
                by_basename[basename] = member

        missing = sorted(set(REQUIRED_FILES) - set(by_basename))

        if missing:
            raise ValidationError(
                "Missing required CSV files: " + ", ".join(missing)
            )

        if len(by_basename) != 6:
            raise ValidationError(
                "Archive must contain exactly the six required CSV datasets"
            )

        all_rows = {}

        with zipfile.ZipFile(zip_path) as archive:
            for filename, member in by_basename.items():
                rows = read_csv_from_zip(
                    archive, member, report["errors"]
                )

                all_rows[filename] = rows
                report["files"][filename] = {
                    "records": len(rows),
                    "archive_path": member
                }

                if not rows:
                    add_error(
                        report["errors"],
                        f"{filename}: no data records"
                    )

                check_numeric_fields(
                    filename, rows, report["errors"]
                )

        metadata = check_metadata(all_rows, report["errors"])

        check_relations(all_rows, report["errors"])

        origins = Counter()

        for rows in all_rows.values():
            for row in rows:
                origin = (row.get("data_origin") or "UNSPECIFIED").strip()
                origins[origin] += 1

        report["provenance"] = dict(origins)

        if origins.get("SYNTHETIC", 0):
            report["warnings"].append(
                "Dataset contains synthetic records. "
                "Do not present them as historical FIA results."
            )

        if origins.get("UNSPECIFIED", 0):
            report["warnings"].append(
                "Some records have no data_origin value."
            )

        if metadata:
            report["race"] = {
                "race_id": metadata[0],
                "season": metadata[1],
                "round": metadata[2],
                "circuit_id": metadata[3]
            }

        if report["errors"]:
            report["status"] = "REJECTED"
        else:
            report["status"] = "VALIDATED"

    except (ValidationError, zipfile.BadZipFile, OSError) as exc:
        report["errors"].append(str(exc))

    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate one F1 Grand Prix ZIP dataset"
    )

    parser.add_argument("zip_path", help="Path to Grand Prix ZIP")
    parser.add_argument(
        "--report",
        default="validation/reports/latest_validation.json",
        help="JSON report output path"
    )

    args = parser.parse_args()

    report = validate_race_zip(args.zip_path)

    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)

    with open(args.report, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    print(json.dumps(report, indent=4))

    print("\nVALIDATION STATUS:", report["status"])

    if report["status"] != "VALIDATED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
