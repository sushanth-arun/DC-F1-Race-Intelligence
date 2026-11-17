import csv
import io
import os
import sys
import tempfile
import zipfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validator import REQUIRED_FILES, NUMERIC_FIELDS, BOOLEAN_FIELDS
from bundle_validator import validate_bundle


def create_test_race_zip(path):

    common = {
        "race_id": "2025_01_TEST",
        "season": "2025",
        "round": "1",
        "circuit_id": "test_circuit",
        "driver_id": "driver_1",
        "driver_number": "1",
        "driver_code": "TST",
        "driver_name": "Test Driver",
        "constructor_id": "team_1",
        "constructor_name": "Test Team",
        "data_origin": "SYNTHETIC"
    }

    with zipfile.ZipFile(path, "w") as archive:

        for filename, columns in REQUIRED_FILES.items():

            row = {}

            for column in columns:
                if column in NUMERIC_FIELDS:
                    row[column] = "1"
                elif column in BOOLEAN_FIELDS:
                    row[column] = "false"
                else:
                    row[column] = "Test"

            row.update(common)

            if filename == "race_results.csv":
                row.update({
                    "finish_position": "1",
                    "is_winner": "true",
                    "is_podium": "true",
                    "status": "Finished"
                })

            elif filename == "qualifying_results.csv":
                row.update({
                    "qualifying_position": "1",
                    "is_pole_position": "true"
                })

            elif filename == "driver_of_the_day.csv":
                row.update({
                    "is_dotd_winner": "true",
                    "voting_position": "1"
                })

            elif filename == "constructor_standings.csv":
                row.update({
                    "championship_position": "1"
                })

            clean_row = {
                column: row.get(column, "")
                for column in columns
            }

            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=columns)
            writer.writeheader()
            writer.writerow(clean_row)

            archive.writestr(
                "test_race/" + filename,
                buffer.getvalue()
            )


def main():

    with tempfile.TemporaryDirectory() as temp:

        race_zip = os.path.join(temp, "test_race.zip")
        bundle_zip = os.path.join(temp, "test_bundle.zip")

        create_test_race_zip(race_zip)

        with zipfile.ZipFile(bundle_zip, "w") as bundle:
            bundle.write(race_zip, "test_race.zip")

        report = validate_bundle(bundle_zip)

        print("\n========== VALIDATOR TEST ==========")
        print("STATUS:", report["status"])
        print("TOTAL:", report["total_races"])
        print("VALIDATED:", report["validated_races"])
        print("REJECTED:", report["rejected_races"])

        if report["status"] != "VALIDATED":
            for race in report["races"]:
                for error in race["errors"]:
                    print("ERROR:", error)
            raise SystemExit(1)

        print("\nVALIDATOR TEST PASSED")


if __name__ == "__main__":
    main()
