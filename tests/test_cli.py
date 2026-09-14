"""CLI tests — offline."""
from __future__ import annotations

import json

import pytest

from deepseek_web_shim import __version__
from deepseek_web_shim.__main__ import main


def test_selftest_reports_a_matching_backend(capsys):
    assert main([]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["match"] is True
    assert out["pure_answer"] == out["planted"]


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_session_capture_from_a_bare_token_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path))
    f = tmp_path / "tok.txt"
    f.write_text("Bearer abc.def.ghi\n")
    assert main(["--session", str(f)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["token_len"] == 11
    assert (tmp_path / "session.json").exists()


def test_session_capture_from_a_json_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path))
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"token": "tok-xyz", "cookies": {"aws-waf-token": "w"}}))
    assert main(["--session", str(f)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["token_len"] == 7
    assert out["cookies"] == 1


def test_session_capture_rejects_an_empty_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DSW_STATE_DIR", str(tmp_path))
    f = tmp_path / "empty.txt"
    f.write_text("   \n")
    assert main(["--session", str(f)]) == 1
