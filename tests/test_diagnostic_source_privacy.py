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
        marker in encoded
        for marker in (
            "SYNTHETIC_RUST_SECRET",
            "SYNTHETIC_JSON_SECRET",
            "SYNTHETIC_HEADER_SECRET",
            "MY_CONTENTSWARM_SECRET_VALUE",
            "PRIVATE_SOURCE_MARKER",
            "fn phone",
        )
    )
    assert rows[0]["sha256"]
    assert rows[0]["reference_lines"]
