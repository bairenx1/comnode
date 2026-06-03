from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8288"


def get_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{BASE}{path}") as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "__body__": e.read().decode("utf-8")}


def post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "__body__": e.read().decode("utf-8")}


def main() -> int:
    try:
        health = get_json("/api/health")
        print("health:", health)

        workflows = get_json("/api/workflows")
        print("workflows:", [w["workflow_id"] for w in workflows.get("workflows", [])])
        if not workflows.get("workflows"):
            raise RuntimeError("No workflows loaded.")

        queue = get_json("/api/queue")
        print("queue:", queue)
        if queue.get("__http_error__") not in (None, 503):
            raise RuntimeError(f"Unexpected queue response: {queue}")

        # Dry run submit with a tiny txt2img job
        submit = post_json(
            "/api/queue/batch",
            {
                "workflow_id": "txt2img",
                "jobs": [
                    {
                        "params": {
                            "prompt": "smoke test image",
                            "negative_prompt": "bad",
                            "width": 512,
                            "height": 512,
                            "steps": 5,
                            "cfg": 5.0,
                            "seed": 12345,
                        }
                    }
                ],
            },
        )
        print("submit:", submit)
        if submit.get("__http_error__") not in (None, 503):
            raise RuntimeError(f"Unexpected submit response: {submit}")
        print("PASS")
        return 0
    except urllib.error.HTTPError as e:
        print("HTTP ERROR:", e.code, e.reason)
        try:
            print(e.read().decode("utf-8"))
        except Exception:
            pass
        return 1
    except Exception as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
