#!/usr/bin/env python3
"""Read-only host metadata. Never exports credentials, environments or raw log output.

Run on aiserver as the normal logged-in service owner. It lists relevant
systemd units, follows only their process trees, hashes known application code,
and emits allowlisted failure markers (not messages). No network or service
changes. Only named non-secret connection fields are projected from matched service processes.
Unknown custom launchers are reported as a gap, not guessed.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

NAMES = ("contentswarm", "custom-tools", "orphusbot")
CODE = (
    "phone_agent/api.py",
    "phone_agent/agent.py",
    "phone_agent/phone_pool.py",
    "phone_agent/bridge.py",
    "phone_agent/actions/handler.py",
    "phone_agent/review_queue.py",
    "social_worker.py",
    "social_delivery.py",
    "phone_agent/flows.py",
    "phone_agent/model/client.py",
    "phone_agent/adb/screenshot.py",
    "phone_agent/task_control.py",
    "contentswarm_cli.py",
)
MARKERS = (
    "Max steps reached",
    "Model error",
    "Final account/body check failed",
    "Expected one exact app control",
    "Invalid delivery lease",
    "Phone clock unavailable",
    "Existing composer left untouched",
    "Human takeover required",
    "Typing outcome uncertain",
    "Tap outcome uncertain",
    "Screenshot unavailable",
)


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def relevant(name):
    return any(part in name.lower() for part in NAMES)


def units(user):
    prefix = ["--user"] if user else []
    code, text = command(
        [
            "systemctl",
            *prefix,
            "list-units",
            "--all",
            "--no-pager",
            "--output=json",
            "--type=service,timer",
        ]
    )
    if code:
        return [], {"scope": "user" if user else "system", "list_exit": code}
    try:
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ValueError("expected unit list")
        return [
            row["unit"]
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("unit"), str)
            and relevant(row["unit"])
        ], None
    except (ValueError, KeyError, TypeError):
        return [], {
            "scope": "user" if user else "system",
            "error": "unreadable systemd listing",
        }


def failure_summary(row):
    """Never return free-text messages, content, URLs, tokens or traceback lines."""
    if not isinstance(row, dict):
        return None
    message = str(row.get("MESSAGE", ""))
    if not re.search(
        r"fail|error|timeout|cancel|denied|uncertain|blocked", message, re.I
    ):
        return None
    return {
        "journal_timestamp": str(row.get("__REALTIME_TIMESTAMP", "")),
        "markers": [item for item in MARKERS if item in message],
        "error_types": sorted(
            set(
                re.findall(
                    r"\b(?:RuntimeError|ValueError|TimeoutError|ConnectionError|PermissionError|TaskCancelled|TaskTimeout)\b",
                    message,
                )
            )
        ),
        "task_ids": re.findall(r'\btask_id["\s:=]+([a-fA-F0-9-]{8,36})\b', message)[:4],
        "message_withheld": True,
    }


def journal(unit, user):
    args = [
        "journalctl",
        *(["--user"] if user else []),
        "-u",
        unit,
        "--since",
        "7 days ago",
        "-n",
        "200",
        "--no-pager",
        "--output=json",
    ]
    code, text = command(args)
    entries = []
    for line in text.splitlines():
        try:
            item = failure_summary(json.loads(line))
            if item:
                entries.append(item)
        except (ValueError, TypeError):
            continue
    return {
        "exit": code,
        "source": f"journalctl {'--user ' if user else ''}-u {unit}",
        "failure_summaries": entries,
        "raw_messages_exported": False,
    }


def source_metadata(directory):
    root = Path(directory).resolve()
    hashes = {}
    for name in CODE:
        path = root / name
        if (
            path.resolve().is_relative_to(root)
            and path.is_file()
            and path.stat().st_size < 2_000_000
        ):
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Git revision only when this directory is itself a checkout, not a parent repo.
    revision = None
    if (root / ".git").exists():
        code, text = command(["git", "-C", str(root), "rev-parse", "HEAD"])
        if code == 0 and re.fullmatch(r"[0-9a-f]{40,64}", text.strip()):
            revision = text.strip()
    return {"directory": str(root), "revision": revision, "source_sha256": hashes}


def binding_metadata(path):
    """Project only non-secret fields of an explicitly referenced MCP JSON file."""
    try:
        if (
            path.suffix != ".json"
            or re.search(r"credential|secret|token|keyring|oauth", path.name, re.I)
            or path.stat().st_size > 2_000_000
        ):
            return None
        data = json.loads(path.read_text())
        servers = data.get("mcpServers", data.get("mcp", {}).get("servers", {}))
        entry = servers.get("custom-tools")
        if not isinstance(entry, dict):
            return None
        result = {"config_file": str(path), "server": "custom-tools"}
        for field in ("url", "endpoint", "base_url", "baseUrl"):
            value = entry.get(field)
            if not isinstance(value, str):
                continue
            parsed = urlsplit(value)
            if parsed.scheme in ("http", "https") and parsed.hostname:
                # Origin only: omit userinfo, path, query and fragments.
                result["origin"] = {
                    "scheme": parsed.scheme,
                    "hostname": parsed.hostname,
                    "port": parsed.port,
                }
        if isinstance(entry.get("command"), str):
            result["command_executable"] = Path(entry["command"].split()[0]).name
        if entry.get("transport") in ("stdio", "http", "sse", "streamable-http"):
            result["transport"] = entry["transport"]
        return result
    except (OSError, ValueError, AttributeError, TypeError, IndexError):
        return None


# Only connection settings, never key/token/password values, may be projected.
CONNECTION_KEYS = {
    b"CONTENTSWARM_API_URL",
    b"CONTENTSWARM_URL",
    b"CONTENTSWARM_BASE_URL",
    b"ORPHUSBOT_CONTENTSWARM_URL",
    b"CONTENTSWARM_HOST",
    b"CONTENTSWARM_PORT",
    b"CONTENTSWARM_STATE_DIR",
    b"CONTENTSWARM_DELIVERY_ENABLED",
}


def project_connection_fields(raw):
    result = {}
    for item in raw.split(b"\0"):
        key, separator, value = item.partition(b"=")
        if not separator or key not in CONNECTION_KEYS:
            continue  # Non-allowlisted values are never decoded or exported.
        name = key.decode("ascii")
        text = value.decode(errors="replace")
        if name.endswith("URL"):
            try:
                url = urlsplit(text)
                if url.scheme in ("http", "https") and url.hostname:
                    result[name] = {
                        "scheme": url.scheme,
                        "hostname": url.hostname,
                        "port": url.port,
                    }
            except ValueError:
                result[name] = "invalid URL (withheld)"
        elif name == "CONTENTSWARM_PORT" and text.isdigit():
            result[name] = text
        elif name == "CONTENTSWARM_DELIVERY_ENABLED":
            result[name] = text if text in ("0", "1") else "unrecognized (withheld)"
        elif name == "CONTENTSWARM_HOST" and re.fullmatch(r"[A-Za-z0-9.:-]+", text):
            result[name] = text
        elif name == "CONTENTSWARM_STATE_DIR" and re.fullmatch(r"/[\w./ -]+", text):
            result[name] = text
    return result


def connection_metadata(root):
    result = {"configured_fields": {}, "listening_ports": []}
    try:
        # Read only the confirmed service's environment and immediately project
        # named connection fields. No credential key/value is decoded/exported.
        result["configured_fields"] = project_connection_fields(
            (root / "environ").read_bytes()
        )
    except OSError:
        result["environment_projection_error"] = "permission denied or process exited"
    try:
        inodes = set()
        for entry in (root / "fd").iterdir():
            try:
                match = re.fullmatch(r"socket:\[(\d+)\]", os.readlink(entry))
                if match:
                    inodes.add(match[1])
            except OSError:
                continue
        for table in ("tcp", "tcp6"):
            for line in (root / "net" / table).read_text().splitlines()[1:]:
                cells = line.split()
                if len(cells) > 9 and cells[3] == "0A" and cells[9] in inodes:
                    result["listening_ports"].append(
                        int(cells[1].rsplit(":", 1)[1], 16)
                    )
        result["listening_ports"] = sorted(set(result["listening_ports"]))
    except (OSError, ValueError):
        result["socket_metadata_error"] = "permission denied, exited, or unavailable"
    return result


def adapter_source_metadata(root):
    """Known live checkout only, static references, not arbitrary host search."""
    root = root.resolve()
    if not (root / ".git").exists():
        return []
    code, text = command(["git", "-C", str(root), "ls-files", "--", "src", "crates"])
    if code:
        return []
    result = []
    for name in text.splitlines():
        if not re.search(r"phone|mcp|tools|config|contentswarm", name, re.I):
            continue
        path = root / name
        if (
            not path.resolve().is_relative_to(root)
            or path.suffix not in (".rs", ".py", ".js", ".ts")
            or not path.is_file()
            or path.stat().st_size > 1_000_000
        ):
            continue
        data = path.read_text(errors="replace")
        if not re.search(r"contentswarm|custom-tools", data, re.I):
            continue
        row = {
            "file": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reference_lines": [
                i
                for i, line in enumerate(data.splitlines(), 1)
                if re.search(r"contentswarm|custom-tools", line, re.I)
            ][:25],
            "connection_key_names": sorted(
                key.decode("ascii")
                for key in CONNECTION_KEYS
                if key.decode("ascii") in data
            ),
            "literal_origins": [],
        }
        for literal in re.findall(r'https?://[^\s"\'<>]+', data):
            try:
                url = urlsplit(literal.rstrip("),;"))
                if url.hostname:
                    row["literal_origins"].append(
                        {
                            "scheme": url.scheme,
                            "hostname": url.hostname,
                            "port": url.port,
                        }
                    )
            except ValueError:
                continue
        result.append(row)
        if len(result) >= 20:
            break
    return result


def source_review_bundle(root):
    """Return source-reference/connection metadata for review, never source text.

    No regex can reliably redact credentials from arbitrary application code.
    Keep the existing report field, but make its contents metadata-only.
    """
    return adapter_source_metadata(root)


def task_trace_metadata(directory):
    """Summarize only the known Phone session directory, with no message text."""
    root = Path(directory)
    if root.name != "work" or root.parent.name != "phone":
        return []
    session = root.parent
    paths = []
    # Bounded to direct and one-level child session files, not a host scan.
    for pattern in ("*.jsonl", "*/*.jsonl"):
        paths.extend(
            p
            for p in session.glob(pattern)
            if p.resolve().is_relative_to(session.resolve())
        )
    rows = []
    for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[:4]:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 200_000))
            text = handle.read(200_000).decode(errors="replace")
        records = []
        for number, line in enumerate(text.splitlines(), 1):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            encoded = json.dumps(item)
            markers = [m for m in MARKERS if m in encoded]
            if re.search(
                r"policy|permission|not allowed|forbidden|barred", encoded, re.I
            ) and re.search(r"\bPost\b|\bsend\b", encoded):
                markers.append("posting_permission_reference")
            if markers:
                records.append(
                    {
                        "tail_record": number,
                        "markers": markers,
                        "record_type": str(item.get("type", ""))[:40],
                        "message_withheld": True,
                    }
                )
        rows.append(
            {
                "file": str(path),
                "tail_bytes_examined": min(path.stat().st_size, 200_000),
                "matching_records": records,
            }
        )
    return rows


def process_metadata(pid, seen=None):
    """Follow matched service PIDs; project only named non-secret connection settings."""
    seen = set() if seen is None else seen
    if not pid or pid in seen or len(seen) >= 64:
        return []
    seen.add(pid)
    root = Path("/proc") / str(pid)
    try:
        cwd = str((root / "cwd").resolve(strict=True))
        argv = (root / "cmdline").read_bytes().decode(errors="replace").split("\0")
        # Only executable/script/config paths, never full arguments or shell text.
        # Known option syntax may carry the referenced file after '='.
        candidates = [
            arg.split("=", 1)[-1]
            if arg.startswith(("--config=", "--mcp-config="))
            else arg
            for arg in argv
        ]
        paths = [
            arg
            for arg in candidates
            if arg.startswith("/")
            and "\n" not in arg
            and re.fullmatch(r"/[\w./@+ -]+\.(?:py|js|mjs|cjs|json)", arg)
            and not re.search(
                r"credential|secret|token|keyring|oauth", Path(arg).name, re.I
            )
        ]
        item = {
            "pid": pid,
            "cwd": cwd,
            "executable": str((root / "exe").resolve(strict=True)),
            "entry_files": paths[:12],
            "source": source_metadata(cwd),
        }
        # Static references identify a handler candidate, not proof of runtime routing.
        item["connections"] = connection_metadata(root)
        item["adapter_source_references"] = adapter_source_metadata(Path(cwd))
        item["adapter_source_review"] = item["adapter_source_references"]
        item["phone_task_trace"] = task_trace_metadata(cwd)
        item["registered_bindings"] = [
            binding for path in paths if (binding := binding_metadata(Path(path)))
        ]
        item["phone_binding_references"] = []
        for path in paths:
            p = Path(path)
            if (
                p.suffix not in (".py", ".js", ".mjs", ".cjs")
                or not p.is_file()
                or p.stat().st_size > 2_000_000
            ):
                continue
            hits = [
                i
                for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
                if "phone" in line.lower()
                and any(key in line for key in ("tool", "ContentSwarm", "contentswarm"))
            ]
            if hits:
                item["phone_binding_references"].append(
                    {
                        "file": path,
                        "lines": hits[:12],
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                )
        children = (root / "task" / str(pid) / "children").read_text().split()
        rows = [item]
        for child in children:
            rows.extend(process_metadata(int(child), seen))
        return rows
    except (OSError, ValueError):
        return [{"pid": pid, "error": "process metadata unavailable or exited"}]


def collect():
    report = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "network_calls": False,
        "environment_read": "allowlisted connection-field projection only",
        "services": [],
        "gaps": [],
    }
    for user in (True, False):
        names, error = units(user)
        if error:
            report["gaps"].append(error)
        for unit in names[:30]:
            args = [
                "systemctl",
                *(["--user"] if user else []),
                "show",
                unit,
                "--property=MainPID,WorkingDirectory,FragmentPath,ActiveState,SubState,User",
            ]
            code, text = command(args)
            fields = (
                dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
                if code == 0
                else {}
            )
            try:
                pid = int(fields.get("MainPID", "0") or 0)
            except ValueError:
                pid = 0
                report["gaps"].append(
                    {"unit": unit, "error": "invalid MainPID; process metadata skipped"}
                )
            report["services"].append(
                {
                    "scope": "user" if user else "system",
                    "unit": unit,
                    "properties": fields,
                    "processes": process_metadata(pid),
                    "journal": journal(unit, user),
                }
            )
    if not report["services"]:
        report["gaps"].append(
            "No matching systemd unit visible to this user; custom launcher mapping is not inferred"
        )
    report["gaps"].append(
        "Only explicitly referenced MCP JSON registration is projected; source references are candidates, not proof of runtime routing. Only named connection fields were projected from matched service environments; no credential files were opened"
    )
    return report


def shared_root(primary=Path("/shared"), script=None):
    if primary.is_dir():
        return primary.resolve()
    # Host bind-mount metadata identifies this team volume. Accept only a
    # collector physically placed in that volume's diagnostics directory.
    source = Path(__file__ if script is None else script).resolve()
    candidate = source.parent.parent
    if (
        source.parent.name == "diagnostics"
        and candidate.name == "_data"
        and candidate.parent.name == "orphusbot-team"
        and candidate.parent.parent.name == "volumes"
        and candidate.is_dir()
    ):
        return candidate
    raise ValueError(
        "Shared team volume unavailable; run the collector from its diagnostics folder"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    try:
        shared = shared_root()
    except ValueError as exc:
        parser.error(str(exc))
    boundary = (shared / "diagnostics").resolve()
    output = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else boundary / "phone-runtime"
    )
    if not output.is_relative_to(boundary):
        parser.error("output must be under the shared team's diagnostics folder")
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    report = collect()
    with path.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print("Read-only diagnostic saved to " + str(path))
    print(
        "No services changed or network calls made. Only named connection settings and redacted failure markers exported."
    )


if __name__ == "__main__":
    main()
