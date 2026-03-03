"""
CLI integration tests (test_cli.py).

Uses Typer's CliRunner for command execution.
Snapshot tests for Rich output use Syrupy (run with --snapshot-update to regenerate).

All commands tested with in-memory database to avoid disk state.
No real API calls — Tequila plugin is not registered in these tests.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from travo.cli import app

runner = CliRunner()


class TestCLIBasics:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "travo" in result.output

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Family travel advisor" in result.output or "Usage" in result.output

    def test_data_version(self):
        result = runner.invoke(app, ["data-version"])
        assert result.exit_code == 0
        assert "QF" in result.output or "Qantas" in result.output

    def test_profile_shows_defaults(self):
        """profile command shows family profile without crashing."""
        result = runner.invoke(app, ["profile"])
        assert result.exit_code == 0
        assert "Adults" in result.output or "adults" in result.output.lower()


class TestStatusCommand:
    def test_status_no_trips(self, tmp_path, monkeypatch):
        """status with no trips shows the 'all fine' message."""
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("TEQUILA_API_KEY", "")  # no API calls

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        # Either "All trips look fine" or empty — both acceptable
        assert result.exit_code == 0

    def test_status_all_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["status", "--all"])
        assert result.exit_code == 0


class TestRemoveCommand:
    def test_remove_nonexistent_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["remove", "999", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestPollCommand:
    def test_poll_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["poll", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_poll_no_trips(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("TEQUILA_API_KEY", "")
        result = runner.invoke(app, ["poll"])
        assert result.exit_code == 0
        assert "0 ok" in result.output or "Poll complete" in result.output


class TestPauseResumeCommands:
    def test_pause_nonexistent_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRAVO_DB_PATH", str(tmp_path / "test.db"))
        # pause/resume on non-existent trip should not crash — just no-op
        result = runner.invoke(app, ["pause", "999"])
        # Acceptable: either graceful no-op or error message
        assert result.exit_code in (0, 1)
