"""Diagnostics must not export source text, regardless of credential syntax."""

import json

import pytest

from scripts import collect_phone_runtime as diag


@pytest.mark.parametrize(
    "source",
    [
        'const API_KEY: &str = "SYNTHETIC_RUST_SECRET";',
        'let data = r#"{"password": "SYNTHETIC_JSON_SECRET"}"#;',
        'request.header("x-api-key", "SYNTHETIC_HEADER_SECRET");',
        'let token = "MY_CONTENTSWARM_SECRET_VALUE";',
        "// PRIVATE_SOURCE_MARKER\nfn phone() {}",
        'let endpoint = "https://SYNTHETIC_URL_SECRET.example.test/private";',
    ],
)
def test_review_bundle_exports_metadata_only(tmp_path, monkeypatch, source):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    path = root / "src/phone.rs"
    path.write_text("// contentswarm adapter\n" + source)
    monkeypatch.setattr(diag, "command", lambda _: (0, "src/phone.rs\n"))
    rows = diag.source_review_bundle(root)
    assert rows and rows[0]["file"] == str(path)
    encoded = json.dumps(rows)
    assert "source_for_review" not in encoded
    assert not any(
        marker.lower() in encoded.lower()
        for marker in (
            "SYNTHETIC_RUST_SECRET",
            "SYNTHETIC_JSON_SECRET",
            "SYNTHETIC_HEADER_SECRET",
            "MY_CONTENTSWARM_SECRET_VALUE",
            "PRIVATE_SOURCE_MARKER",
            "SYNTHETIC_URL_SECRET",
            "fn phone",
        )
    )
    assert rows[0]["sha256"]
    assert rows[0]["reference_lines"]


def test_rollout_checks_pinned_collector_before_running_it():
    import hashlib
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    guide = (root / "deploy/PHONE_RELIABILITY_ROLLOUT.md").read_text()
    expected = re.search(r"EXPECTED_COLLECTOR_SHA256=([0-9a-f]{64})", guide)
    assert expected
    assert (
        expected[1]
        == hashlib.sha256(
            (root / "scripts/collect_phone_runtime.py").read_bytes()
        ).hexdigest()
    )
    check = guide.index("sha256sum --check -; then")
    run = guide.index('python3 "$COLLECTOR"')
    assert check < run
    assert "STOP: collector hash differs. Do not run or deploy it;" in guide
