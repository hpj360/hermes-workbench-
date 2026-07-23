"""Tests for hermes.logging setup_logging()."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from hermes.logging import setup_logging


@pytest.fixture(autouse=True)
def clear_hermes_logger():
    """Clear the 'hermes' logger handlers before and after each test."""
    logger = logging.getLogger("hermes")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


def test_setup_logging_returns_logger() -> None:
    logger = setup_logging()
    assert isinstance(logger, logging.Logger)
    assert logger.name == "hermes"


def test_setup_logging_sets_level_debug() -> None:
    logger = setup_logging(level="DEBUG")
    assert logger.level == logging.DEBUG


def test_setup_logging_default_level_info() -> None:
    logger = setup_logging()
    assert logger.level == logging.INFO


def test_setup_logging_clears_existing_handlers() -> None:
    setup_logging()
    setup_logging()
    logger = logging.getLogger("hermes")
    assert len(logger.handlers) == 1


def test_setup_logging_adds_console_handler() -> None:
    setup_logging()
    logger = logging.getLogger("hermes")
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_setup_logging_adds_file_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "hermes.log"
    setup_logging(log_file=log_file)
    logger = logging.getLogger("hermes")
    assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    assert len(logger.handlers) == 2


def test_setup_logging_creates_parent_dir(tmp_path: Path) -> None:
    log_file = tmp_path / "deep" / "nested" / "logs" / "hermes.log"
    setup_logging(log_file=log_file)
    assert log_file.parent.exists()


def test_setup_logging_file_writable(tmp_path: Path) -> None:
    log_file = tmp_path / "hermes.log"
    logger = setup_logging(log_file=log_file)
    logger.info("hello world")
    for h in logger.handlers:
        h.flush()
    assert log_file.exists()
    assert "hello world" in log_file.read_text(encoding="utf-8")


def test_setup_logging_invalid_level_falls_back_to_info() -> None:
    logger = setup_logging(level="NOPE")
    assert logger.level == logging.INFO
