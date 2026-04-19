from __future__ import annotations

from click.testing import CliRunner

from cartoload.cli import main


def test_help_succeeds():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "cartoload" in result.output


def test_commands_listed():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ["build", "download", "split", "list"]:
        assert cmd in result.output


def test_build_help():
    runner = CliRunner()
    result = runner.invoke(main, ["build", "--help"])
    assert result.exit_code == 0
    assert "--sources" in result.output
    assert "--layers" in result.output
    assert "--exporter" in result.output
    assert "--quality" in result.output
