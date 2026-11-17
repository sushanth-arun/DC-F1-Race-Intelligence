import os
import tempfile
import zipfile

from test_validator import create_test_race_zip
from bundle_validator import validate_bundle


def main():

    with tempfile.TemporaryDirectory() as temp:

        original = os.path.join(temp, "original.zip")
        incomplete = os.path.join(temp, "incomplete.zip")
        bundle_path = os.path.join(temp, "bundle.zip")

        create_test_race_zip(original)

        # Remove race_results.csv to simulate an invalid race
        with zipfile.ZipFile(original, "r") as source:
            with zipfile.ZipFile(incomplete, "w") as target:

                for item in source.infolist():

                    if item.filename.endswith("race_results.csv"):
                        continue

                    target.writestr(
                        item.filename,
                        source.read(item.filename)
                    )

        with zipfile.ZipFile(bundle_path, "w") as bundle:
            bundle.write(incomplete, "test_race.zip")

        report = validate_bundle(bundle_path)

        print("\n========== NEGATIVE TEST ==========")
        print("TEST STATUS:", report["status"])
        print("TOTAL RACES:", report["total_races"])
        print("VALIDATED:", report["validated_races"])
        print("REJECTED:", report["rejected_races"])

        if report["status"] == "REJECTED":
            print("\nNEGATIVE TEST PASSED")
        else:
            raise SystemExit("NEGATIVE TEST FAILED")


if __name__ == "__main__":
    main()
