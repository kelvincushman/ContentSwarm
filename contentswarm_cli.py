#!/usr/bin/env python3
"""
contentswarm - agent-native CLI for the ContentSwarm phone fleet.

Thin client over the ContentSwarm REST API. Designed to be driven by an
agent harness (Orphus) through its bash tool: every command prints JSON
to stdout and exits 0 on success, 1 on failure.

Configuration (flags override environment):
    CONTENTSWARM_API_URL    Base API URL (default: http://127.0.0.1:5000/api/v1)
    CONTENTSWARM_API_TOKEN  Bearer token, required if the server sets one

Examples:
    contentswarm status
    contentswarm phones
    contentswarm run phone_01 "Open TikTok and scroll the For You page" --wait
    contentswarm batch -t phone_01="Open TikTok" -t phone_02="Open Instagram"
    contentswarm task 1a2b3c4d
    contentswarm launch phone_01 TikTok
    contentswarm screenshot phone_01 -o screen.png
    contentswarm ui phone_01
    contentswarm current phone_01
    contentswarm apps
    contentswarm runs tiktok-post
"""

import argparse
import json
import os
import sys
import time

import requests

DEFAULT_API_URL = "http://127.0.0.1:5000/api/v1"
POLL_INTERVAL_SECONDS = 3


class ApiError(Exception):
    """API returned an error response."""


class Client:
    """Minimal HTTP client for the ContentSwarm API."""

    def __init__(self, api_url: str, token: str | None = None, timeout: int = 60):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, raw: bool = False):
        resp = requests.get(
            f"{self.api_url}{path}", headers=self.headers, timeout=self.timeout
        )
        return self._handle(resp, raw=raw)

    def post(self, path: str, body: dict | None = None):
        resp = requests.post(
            f"{self.api_url}{path}",
            json=body or {},
            headers=self.headers,
            timeout=self.timeout,
        )
        return self._handle(resp)

    def _handle(self, resp, raw: bool = False):
        if resp.status_code == 401:
            raise ApiError(
                "Unauthorized: set CONTENTSWARM_API_TOKEN to match the server"
            )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", resp.text)
            except ValueError:
                detail = resp.text
            raise ApiError(f"HTTP {resp.status_code}: {detail}")
        if raw:
            return resp
        return resp.json()


def output(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def wait_for_task(client: Client, task_id: str, timeout: int) -> dict:
    """Poll a task until it completes, fails, or the timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/tasks/{task_id}")
        if status.get("status") in ("completed", "failed"):
            return status
        time.sleep(POLL_INTERVAL_SECONDS)
    return {"task_id": task_id, "status": "timeout", "error": f"No result within {timeout}s"}


def parse_batch_tasks(pairs: list[str]) -> dict:
    """Parse repeated -t phone=task arguments into a dict."""
    tasks = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid task spec (expected phone=task): {pair}")
        phone, task = pair.split("=", 1)
        tasks[phone.strip()] = task.strip()
    return tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contentswarm",
        description="Control the ContentSwarm phone fleet from the command line.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CONTENTSWARM_API_URL", DEFAULT_API_URL),
        help="Base API URL (env: CONTENTSWARM_API_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CONTENTSWARM_API_TOKEN"),
        help="Bearer token (env: CONTENTSWARM_API_TOKEN)",
    )
    parser.add_argument(
        "--timeout", type=int, default=60, help="HTTP request timeout in seconds"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="System overview")
    sub.add_parser("phones", help="List phones and connection status")

    p = sub.add_parser("phone", help="Details for one phone")
    p.add_argument("name")

    p = sub.add_parser("run", help="Run a natural-language task on a phone (async)")
    p.add_argument("phone")
    p.add_argument("task")
    p.add_argument("--wait", action="store_true", help="Poll until the task finishes")
    p.add_argument(
        "--wait-timeout", type=int, default=600, help="Max seconds to wait (default 600)"
    )

    p = sub.add_parser("batch", help="Run tasks on multiple phones in parallel")
    p.add_argument(
        "-t",
        "--task",
        dest="tasks",
        action="append",
        required=True,
        metavar="PHONE=TASK",
        help="Repeatable: -t phone_01='Open TikTok'",
    )
    p.add_argument("--wait", action="store_true", help="Poll until all tasks finish")
    p.add_argument("--wait-timeout", type=int, default=600)

    p = sub.add_parser("task", help="Status of one async task")
    p.add_argument("task_id")

    sub.add_parser("tasks", help="List all tracked tasks")
    sub.add_parser("apps", help="List apps that can be launched by name")

    p = sub.add_parser("launch", help="Launch an app on a phone directly (no LLM)")
    p.add_argument("phone")
    p.add_argument("app")

    p = sub.add_parser("current", help="Foreground app on a phone")
    p.add_argument("phone")

    p = sub.add_parser(
        "ui",
        help="Dump the UI element tree of a phone's screen - every element's "
             "text, id, desc, bounds, and center (semantic, no vision model)",
    )
    p.add_argument("phone")

    p = sub.add_parser("screenshot", help="Capture a phone's screen as PNG")
    p.add_argument("phone")
    p.add_argument("-o", "--output", help="Output file (default: <phone>_<ts>.png)")

    p = sub.add_parser("installed", help="Discover apps installed on a phone")
    p.add_argument("phone")

    p = sub.add_parser(
        "learn",
        help="Learn a flow: the vision model drives the task once while "
             "every action is recorded with its exact press points",
    )
    p.add_argument("phone")
    p.add_argument("task")
    p.add_argument("--name", required=True, help="Name to save the flow under")
    p.add_argument("--wait", action="store_true", help="Poll until learning finishes")
    p.add_argument("--wait-timeout", type=int, default=900)

    p = sub.add_parser(
        "replay",
        help="Replay a learned flow deterministically (exact presses, no LLM)",
    )
    p.add_argument("phone")
    p.add_argument("flow")
    p.add_argument("--speed", type=float, default=1.0, help="Delay multiplier (2.0 = twice as fast)")
    p.add_argument("--wait", action="store_true", help="Poll until replay finishes")
    p.add_argument("--wait-timeout", type=int, default=600)

    sub.add_parser("flows", help="List learned flows")

    p = sub.add_parser("flow", help="Show the recorded steps of one flow")
    p.add_argument("name")

    p = sub.add_parser(
        "runs",
        help="Replay run reports for a flow - what each replay actually did "
             "versus what the flow intended, step by step",
    )
    p.add_argument("flow")

    return parser


def run_command(args, client: Client) -> None:
    if args.command == "status":
        output(client.get("/status"))

    elif args.command == "phones":
        output(client.get("/phones"))

    elif args.command == "phone":
        output(client.get(f"/phones/{args.name}"))

    elif args.command == "run":
        result = client.post(f"/phones/{args.phone}/task", {"task": args.task})
        if args.wait:
            result = wait_for_task(client, result["task_id"], args.wait_timeout)
        output(result)
        if result.get("status") in ("failed", "timeout"):
            sys.exit(1)

    elif args.command == "batch":
        tasks = parse_batch_tasks(args.tasks)
        result = client.post("/phones/batch", {"tasks": tasks})
        if args.wait:
            results = {
                phone: wait_for_task(client, task_id, args.wait_timeout)
                for phone, task_id in result["task_ids"].items()
            }
            output({"results": results})
            if any(r.get("status") in ("failed", "timeout") for r in results.values()):
                sys.exit(1)
        else:
            output(result)

    elif args.command == "task":
        output(client.get(f"/tasks/{args.task_id}"))

    elif args.command == "tasks":
        output(client.get("/tasks"))

    elif args.command == "apps":
        output(client.get("/apps"))

    elif args.command == "launch":
        output(client.post(f"/phones/{args.phone}/app", {"app": args.app}))

    elif args.command == "current":
        output(client.get(f"/phones/{args.phone}/current_app"))

    elif args.command == "ui":
        output(client.get(f"/phones/{args.phone}/ui"))

    elif args.command == "runs":
        output(client.get(f"/flows/{args.flow}/runs"))

    elif args.command == "installed":
        output(client.get(f"/phones/{args.phone}/installed"))

    elif args.command == "learn":
        result = client.post(
            f"/phones/{args.phone}/learn",
            {"task": args.task, "flow_name": args.name},
        )
        if args.wait:
            result = wait_for_task(client, result["task_id"], args.wait_timeout)
        output(result)
        if result.get("status") in ("failed", "timeout"):
            sys.exit(1)

    elif args.command == "replay":
        result = client.post(
            f"/phones/{args.phone}/replay",
            {"flow_name": args.flow, "speed": args.speed},
        )
        if args.wait:
            result = wait_for_task(client, result["task_id"], args.wait_timeout)
        output(result)
        if result.get("status") in ("failed", "timeout"):
            sys.exit(1)

    elif args.command == "flows":
        output(client.get("/flows"))

    elif args.command == "flow":
        output(client.get(f"/flows/{args.name}"))

    elif args.command == "screenshot":
        resp = client.get(f"/phones/{args.phone}/screenshot", raw=True)
        out_path = args.output or f"{args.phone}_{int(time.time())}.png"
        with open(out_path, "wb") as f:
            f.write(resp.content)
        output({
            "phone": args.phone,
            "file": os.path.abspath(out_path),
            "width": resp.headers.get("X-Screen-Width"),
            "height": resp.headers.get("X-Screen-Height"),
            "sensitive": resp.headers.get("X-Sensitive") == "true",
        })


def main() -> None:
    args = build_parser().parse_args()
    client = Client(args.api_url, args.token, args.timeout)

    try:
        run_command(args, client)
    except ApiError as e:
        output({"error": str(e)})
        sys.exit(1)
    except requests.ConnectionError:
        output({"error": f"Cannot reach ContentSwarm API at {args.api_url}"})
        sys.exit(1)
    except requests.Timeout:
        output({"error": f"Request to {args.api_url} timed out"})
        sys.exit(1)
    except ValueError as e:
        output({"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
