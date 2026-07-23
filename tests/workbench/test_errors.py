"""Tests for hermes.workbench.errors hierarchy and status_code_for()."""

from __future__ import annotations

from hermes.workbench.errors import (
    AuthError,
    NotFoundError,
    StateError,
    UpstreamError,
    ValidationError,
    WorkbenchError,
    status_code_for,
)


def test_auth_error_is_workbench_error() -> None:
    assert issubclass(AuthError, WorkbenchError)


def test_validation_error_is_workbench_error() -> None:
    assert issubclass(ValidationError, WorkbenchError)


def test_not_found_error_is_workbench_error() -> None:
    assert issubclass(NotFoundError, WorkbenchError)


def test_state_error_is_workbench_error() -> None:
    assert issubclass(StateError, WorkbenchError)


def test_upstream_error_is_workbench_error() -> None:
    assert issubclass(UpstreamError, WorkbenchError)


def test_status_code_for_validation_error() -> None:
    assert status_code_for(ValidationError("bad")) == 400


def test_status_code_for_auth_error() -> None:
    assert status_code_for(AuthError("nope")) == 401


def test_status_code_for_not_found_error() -> None:
    assert status_code_for(NotFoundError("missing")) == 404


def test_status_code_for_state_error() -> None:
    assert status_code_for(StateError("conflict")) == 409


def test_status_code_for_upstream_error() -> None:
    assert status_code_for(UpstreamError("boom")) == 502


def test_status_code_for_generic_exception_is_500() -> None:
    assert status_code_for(RuntimeError("generic")) == 500


def test_status_code_for_base_workbench_error_is_500() -> None:
    assert status_code_for(WorkbenchError("base")) == 500
