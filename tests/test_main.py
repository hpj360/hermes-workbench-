"""Tests for hermes.main CLI entry point and build_parser()."""

from __future__ import annotations

import argparse

import pytest

from hermes import main as hermes_main
from hermes.main import build_parser, main


@pytest.fixture(autouse=True)
def reset_settings_around():
    from hermes import config as _config
    _config._hermes_settings = None
    yield
    _config._hermes_settings = None


def test_main_start_returns_zero() -> None:
    assert main(["start"]) == 0


def test_main_skills_list_returns_zero() -> None:
    assert main(["skills", "list"]) == 0


def test_main_knowledge_list_returns_zero() -> None:
    assert main(["knowledge", "list"]) == 0


def test_main_config_show_returns_zero() -> None:
    assert main(["config", "show"]) == 0


def test_main_doctor_returns_zero_or_one() -> None:
    rc = main(["doctor"])
    assert rc in (0, 1)


def test_main_profile_show_returns_zero(tmp_state_dir) -> None:
    assert main(["profile", "show"]) == 0


def test_main_profile_show_json_returns_zero(tmp_state_dir) -> None:
    assert main(["profile", "show", "--json"]) == 0


def test_main_no_args_returns_zero() -> None:
    # No command → defaults to cmd_start
    assert main([]) == 0


def test_build_parser_has_workbench_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["workbench", "skills", "list"])
    assert args.command == "workbench"


def test_main_workbench_skills_list_returns_zero() -> None:
    rc = main(["workbench", "skills", "list"])
    assert rc == 0


def test_main_returns_2_on_exception(monkeypatch) -> None:
    def boom(args: argparse.Namespace) -> int:
        raise RuntimeError("intentional")

    monkeypatch.setattr(hermes_main, "cmd_start", boom)
    # build_parser assigns cmd_start via set_defaults at parser-build time, so
    # patching the symbol first makes the parser bind the raising function.
    assert main(["start"]) == 2


def test_log_level_choices_exist() -> None:
    parser = build_parser()
    # Valid choices parse fine
    args = parser.parse_args(["--log-level", "DEBUG", "start"])
    assert args.log_level == "DEBUG"
    # Invalid choice causes SystemExit (argparse error)
    with pytest.raises(SystemExit):
        parser.parse_args(["--log-level", "BOGUS", "start"])
