import pytest

from contentswarm_cli import read_text_argument


def test_body_file_errors_become_user_facing_value_errors(tmp_path):
    with pytest.raises(ValueError, match="cannot read text file"):
        read_text_argument(None, str(tmp_path / "missing"))

    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="cannot read text file"):
        read_text_argument(None, str(invalid))


def test_body_file_reads_utf8(tmp_path):
    body = tmp_path / "body.txt"
    body.write_text("hello ✓", encoding="utf-8")
    assert read_text_argument(None, str(body)) == "hello ✓"
