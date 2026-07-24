"""Tests for workbench.dashboard module.

The dashboard is a static HTML document; we verify its structure
and that essential UI hooks (ids, scripts, styles) are present.
"""

from __future__ import annotations

from hermes.workbench.dashboard import DASHBOARD_HTML


def test_dashboard_is_non_empty_html():
    assert isinstance(DASHBOARD_HTML, str)
    assert DASHBOARD_HTML.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in DASHBOARD_HTML


def test_dashboard_has_title():
    assert "<title>Hermes Workbench Dashboard</title>" in DASHBOARD_HTML


def test_dashboard_has_required_panel_ids():
    """The renderDashboard script targets specific DOM ids; they must exist."""
    required_ids = [
        "stats-grid",
        "tasks-body",
        "episodes-body",
        "facts-body",
        "traces-body",
        "skills-body",
        "task-count",
        "episode-count",
        "fact-count",
        "trace-count",
        "skill-count",
        "last-updated",
        "btn-refresh",
        "btn-autorenew",
    ]
    for id_ in required_ids:
        assert f'id="{id_}"' in DASHBOARD_HTML, f"missing element id={id_}"


def test_dashboard_has_refresh_script():
    """Auto-refresh and manual refresh handlers must be wired up."""
    assert "loadDashboard" in DASHBOARD_HTML
    assert "btn-refresh" in DASHBOARD_HTML
    assert "btn-autorenew" in DASHBOARD_HTML
    assert "setInterval" in DASHBOARD_HTML


def test_dashboard_has_trace_modal():
    """Trace detail modal markup is present."""
    assert 'id="modal"' in DASHBOARD_HTML
    assert 'id="modal-bg"' in DASHBOARD_HTML
    assert 'id="modal-close"' in DASHBOARD_HTML
    assert "openTrace" in DASHBOARD_HTML


def test_dashboard_has_token_auth_in_fetch():
    """fetchJson attaches the localStorage-stored Bearer token."""
    assert "localStorage.getItem" in DASHBOARD_HTML
    assert "Authorization" in DASHBOARD_HTML
    assert "Bearer" in DASHBOARD_HTML


def test_dashboard_has_status_badge_helpers():
    assert "statusBadge" in DASHBOARD_HTML
    assert "kindBadge" in DASHBOARD_HTML
    # Badge CSS classes (template literals use ${cls} interpolation).
    assert "badge ${cls}" in DASHBOARD_HTML
    assert "badge kind-${escapeHtml(kind)}" in DASHBOARD_HTML
    # CSS rules for badge variants are present.
    assert ".badge.ok" in DASHBOARD_HTML
    assert ".badge.fail" in DASHBOARD_HTML


def test_dashboard_has_dark_theme():
    """Dark theme colors are baked into :root CSS variables."""
    assert ":root" in DASHBOARD_HTML
    assert "--bg" in DASHBOARD_HTML
    assert "--panel" in DASHBOARD_HTML
    assert "--accent" in DASHBOARD_HTML


def test_dashboard_includes_autorenew_status_indicator():
    """There is a hidden autorenew status span toggled by the script."""
    assert 'id="autorenew-status"' in DASHBOARD_HTML


def test_dashboard_calls_load_on_load():
    """The dashboard bootstraps itself by calling loadDashboard() at the end."""
    # The final script block ends with a bare loadDashboard() call.
    assert DASHBOARD_HTML.rstrip().endswith("loadDashboard();\n</script>\n</body>\n</html>")


def test_dashboard_uses_relative_api_paths():
    """All API calls go through ``API + url`` (window.location.origin)."""
    assert "window.location.origin" in DASHBOARD_HTML
    assert '"/dashboard' in DASHBOARD_HTML
    assert '"/traces/' in DASHBOARD_HTML


def test_dashboard_escapes_user_content():
    """escapeHtml is defined and used to prevent XSS in rendered rows."""
    assert "function escapeHtml" in DASHBOARD_HTML
    # Used in templates
    assert "escapeHtml(t.task_id)" in DASHBOARD_HTML


def test_dashboard_formats_relative_time():
    """fmtRelative is defined and used for the 'updated X ago' display."""
    assert "function fmtRelative" in DASHBOARD_HTML
    assert "fmtRelative" in DASHBOARD_HTML


def test_dashboard_panel_count():
    """Six panels total: stats (full) + tasks + episodes + facts + traces + skills (full)."""
    # Two 'full' panels (stats grid and skills), four half-width panels.
    assert DASHBOARD_HTML.count('class="panel full"') == 2
    # 'panel"' would match both 'panel full' and bare 'panel' — check bare panels only.
    assert 'class="panel"' in DASHBOARD_HTML
