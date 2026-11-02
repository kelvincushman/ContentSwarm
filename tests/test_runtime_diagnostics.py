"""Read-only host collector tests using fake service/process/log metadata."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import collect_phone_runtime as diag


def test_failure_logs_never_export_free_text_or_secrets():
    value = diag.failure_summary(
        {
            "MESSAGE": "RuntimeError: Model error task_id=abcdef12 token=SUPERSECRET private post text",
            "__REALTIME_TIMESTAMP": "123",
        }
    )
    encoded = json.dumps(value)
    assert value["markers"] == ["Model error"]
    assert value["task_ids"] == ["abcdef12"]
    assert value["message_withheld"]
    assert "SUPERSECRET" not in encoded and "private post" not in encoded


def test_only_relevant_actual_units_are_collected(monkeypatch):
    monkeypatch.setattr(
        diag,
        "command",
        lambda _: (
            0,
            json.dumps(
                [
                    {"unit": "ssh.service"},
                    {"unit": "custom-tools.service"},
                    {"unit": "contentswarm.service"},
                ]
            ),
        ),
    )
    units, error = diag.units(True)
    assert error is None
    assert units == ["custom-tools.service", "contentswarm.service"]


def test_collector_uses_only_readonly_commands_and_no_environment_properties(
    monkeypatch,
):
    calls = []

    def command(args):
        calls.append(args)
        if "list-units" in args:
            return 0, json.dumps([{"unit": "custom-tools.service"}])
        if "show" in args:
            return 0, "MainPID=0\nWorkingDirectory=/service\n"
        return 0, ""

    monkeypatch.setattr(diag, "command", command)
    report = diag.collect()
    assert (
        report["read_only"]
        and not report["network_calls"]
        and not report["environment_read"]
    )
    assert all(call[0] in ("systemctl", "journalctl") for call in calls)
    assert not any(
        word in {"start", "stop", "restart", "enable", "disable", "daemon-reload"}
        for call in calls
        for word in call
    )
    assert not any(
        "Environment" in word or "ExecStart" in word for call in calls for word in call
    )


def test_command_is_bounded_and_never_uses_shell(monkeypatch):
    def run(args, **kwargs):
        assert kwargs == dict(capture_output=True, text=True, timeout=15)
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(diag.subprocess, "run", run)
    assert diag.command(["systemctl", "show", "actual.service"]) == (0, "ok")


def test_timeout_becomes_gap_not_raw_command_output(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 15, stderr="secret")

    monkeypatch.setattr(diag.subprocess, "run", run)
    assert diag.command(["systemctl", "show", "actual.service"]) == (-1, "")


def test_source_metadata_hashes_code_without_reading_credentials(tmp_path):
    file = tmp_path / "social_worker.py"
    file.write_text('print("code")')
    (tmp_path / ".env").write_text("TOKEN=SECRET")
    result = diag.source_metadata(tmp_path)
    assert result["revision"] is None
    assert list(result["source_sha256"]) == ["social_worker.py"]
    assert "SECRET" not in json.dumps(result)


def test_registered_binding_projects_only_origin_and_executable(tmp_path):
    path = tmp_path / "explicit-config.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "custom-tools": {
                        "url": "https://user:SECRET@server.test:443/private/TOKEN?key=SECRET",
                        "transport": "sse",
                        "env": {"API_TOKEN": "SECRET"},
                        "command": "/usr/bin/node",
                        "args": ["--secret=SECRET"],
                    }
                }
            }
        )
    )
    result = diag.binding_metadata(path)
    assert result["origin"] == {
        "scheme": "https",
        "hostname": "server.test",
        "port": 443,
    }
    assert result["command_executable"] == "node"
    assert result["transport"] == "sse"
    assert all(
        value not in json.dumps(result)
        for value in ("SECRET", "TOKEN", "private", "user:")
    )


def test_unrecognized_config_is_not_guessed(tmp_path):
    path = tmp_path / "explicit-config.json"
    path.write_text('{"something_else":{"url":"https://example.test"}}')
    assert diag.binding_metadata(path) is None


@pytest.mark.parametrize("value", [None, [], 42, "text"])
def test_nonobject_journal_records_are_ignored(value):
    assert diag.failure_summary(value) is None


def test_bad_pid_is_reported_as_a_gap_not_a_crash(monkeypatch):
    monkeypatch.setattr(
        diag,
        "units",
        lambda user: (["custom-tools.service"], None) if user else ([], None),
    )
    monkeypatch.setattr(
        diag,
        "command",
        lambda args: (0, "MainPID=not-a-number\n") if "show" in args else (0, ""),
    )
    report = diag.collect()
    assert report["services"][0]["processes"] == []
    assert any(
        isinstance(gap, dict) and "MainPID" in gap.get("error", "")
        for gap in report["gaps"]
    )


def test_output_outside_diagnostics_is_rejected(monkeypatch):
    monkeypatch.setattr("sys.argv", ["collector", "--output-dir", "/shared/other"])
    with pytest.raises(SystemExit) as result:
        diag.main()
    assert result.value.code == 2


def test_host_team_volume_is_resolved_from_collector_location(tmp_path):
    shared = tmp_path / "volumes/orphusbot-team/_data"
    folder = shared / "diagnostics"
    folder.mkdir(parents=True)
    script = folder / "collect-phone-runtime.py"
    script.write_text("")
    assert diag.shared_root(primary=tmp_path / "absent", script=script) == shared


def test_arbitrary_download_location_is_not_accepted_as_shared_root(tmp_path):
    script = tmp_path / "Downloads/collector.py"
    script.parent.mkdir()
    script.write_text("")
    with pytest.raises(ValueError, match="Shared team volume unavailable"):
        diag.shared_root(primary=tmp_path / "absent", script=script)


def test_named_credential_files_are_not_opened(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_a, **_k: pytest.fail("credential file must not be opened"),
    )
    assert diag.binding_metadata(path) is None
