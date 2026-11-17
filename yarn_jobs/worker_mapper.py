import json
import sys
import urllib.request

WORKERS = {
    "race": "http://127.0.0.1:5101",
    "laps": "http://127.0.0.1:5102",
    "pits": "http://127.0.0.1:5103",
    "fan": "http://127.0.0.1:5104",
}

for line in sys.stdin:
    try:
        task = json.loads(line)
        name = task["name"]

        if name not in WORKERS:
            raise ValueError("Unknown worker: " + name)

        body = json.dumps({
            "task": name,
            "data": task["data"]
        }).encode("utf-8")

        request = urllib.request.Request(
            WORKERS[name] + "/process",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))

        if "result" not in result:
            raise RuntimeError(name + " worker returned no result")

        print(name + "\t" + json.dumps(result["result"]))

    except Exception as exc:
        print("YARN_MAPPER_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
