"""Tests for profile persistence: working-principles backfill, parsing, save semantics.

Covers the previously 0%-tested profile.py module, focusing on:
- _load_working_principles_from_doc parser robustness (Bug 5, --- truncation)
- load_profile backfill + non-persistence (Bug 3, Bug 4)
- save_profile does not poison local state with backfilled values
- _has_meaningful_principles edge cases ([null], [""], [])
- markdown rendering of multi-line principle bodies (render bug 3.2)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from hermes import profile as P


# ── _has_meaningful_principles ───────────────────────────────────────


def test_has_meaningful_principles_none() -> None:
    assert P._has_meaningful_principles(None) is False


def test_has_meaningful_principles_empty() -> None:
    assert P._has_meaningful_principles([]) is False


def test_has_meaningful_principles_null_values() -> None:
    # Bug 4: [null] / [None] should be treated as meaningless.
    assert P._has_meaningful_principles([None]) is False


def test_has_meaningful_principles_blank_strings() -> None:
    # Bug 4: [""] / ["   "] should be treated as meaningless.
    assert P._has_meaningful_principles([""]) is False
    assert P._has_meaningful_principles(["   "]) is False


def test_has_meaningful_principles_real_value() -> None:
    assert P._has_meaningful_principles(["从第一性原理出发"]) is True


# ── _load_working_principles_from_doc parser ─────────────────────────


def _write_doc(tmp_path: Path, content: str) -> Path:
    """Write a working-principles.md to a tmp knowledge dir and patch the path."""
    doc = tmp_path / "knowledge" / "working-principles.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(content, encoding="utf-8")
    return doc


def test_parse_doc_missing_returns_empty() -> None:
    with mock.patch.object(P, "_working_principles_doc_path", return_value=Path("/nonexistent/x.md")):
        assert P._load_working_principles_from_doc() == []


def test_parse_doc_two_rules(tmp_path: Path) -> None:
    content = (
        "# 标题\n\n"
        "## 规则一：第一性原理\n\n"
        "从本质出发。\n\n"
        "## 规则二：对抗审查\n\n"
        "多 Agent 审查。\n"
    )
    doc = _write_doc(tmp_path, content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        entries = P._load_working_principles_from_doc()
    assert len(entries) == 2
    assert "规则一：第一性原理" in entries[0]
    assert "从本质出发" in entries[0]
    assert "规则二：对抗审查" in entries[1]


def test_parse_doc_separator_inside_body_not_truncated(tmp_path: Path) -> None:
    # Bug 3.1: `---` inside a rule body must NOT end the rule early.
    content = (
        "## 规则一：含分隔符的规则\n\n"
        "第一段\n\n"
        "---\n\n"
        "第二段\n\n"
        "## 规则二：下一条\n\n"
        "body\n"
    )
    doc = _write_doc(tmp_path, content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        entries = P._load_working_principles_from_doc()
    assert len(entries) == 2
    # 第二段 must be preserved in rule one's body.
    assert "第二段" in entries[0], "body after --- was truncated (Bug 3.1 regression)"


def test_parse_doc_strict_rule_heading_prefix(tmp_path: Path) -> None:
    # Bug 5: `## 规则补充` / `## 规则附录` must NOT be treated as rule entries.
    content = (
        "## 规则一：真正的规则\n\n"
        "body1\n\n"
        "## 规则补充：额外说明\n\n"
        "notes\n\n"
        "## 规则二：另一条\n\n"
        "body2\n"
    )
    doc = _write_doc(tmp_path, content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        entries = P._load_working_principles_from_doc()
    # Only 规则一 and 规则二, NOT 规则补充.
    assert len(entries) == 2
    titles = [e.split("\n")[0] for e in entries]
    assert "规则一：真正的规则" in titles
    assert "规则二：另一条" in titles
    assert not any("规则补充" in t for t in titles)


def test_parse_doc_arabic_number_heading(tmp_path: Path) -> None:
    content = "## 规则1：阿拉伯数字\n\nbody\n"
    doc = _write_doc(tmp_path, content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        entries = P._load_working_principles_from_doc()
    assert len(entries) == 1
    assert "规则1：阿拉伯数字" in entries[0]


# ── load_profile backfill ────────────────────────────────────────────


@pytest.fixture
def isolated_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect profile path to a tmp location; ensure no real file leaks."""
    profile_file = tmp_path / "profile.json"
    monkeypatch.setattr(P, "_profile_path", lambda: profile_file)
    return profile_file


def test_load_profile_backfills_when_local_empty(isolated_profile: Path, tmp_path: Path) -> None:
    # No local profile.json exists -> default skeleton -> backfill from doc.
    doc_content = "## 规则一：测试规则\n\nbody\n"
    doc = _write_doc(tmp_path, doc_content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        profile = P.load_profile()
    principles = profile["work_style"]["working_principles"]
    assert len(principles) == 1
    assert "测试规则" in principles[0]
    # Backfill marker must be set so save_profile knows to strip it.
    assert profile["work_style"]["_working_principles_from_doc"] is True


def test_load_profile_no_backfill_when_local_has_value(isolated_profile: Path, tmp_path: Path) -> None:
    isolated_profile.write_text(
        json.dumps(
            {"work_style": {"working_principles": ["本地规则"]}, "version": 4},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    doc_content = "## 规则一：文档规则\n\nbody\n"
    doc = _write_doc(tmp_path, doc_content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        profile = P.load_profile()
    # Local value wins, no backfill marker.
    assert profile["work_style"]["working_principles"] == ["本地规则"]
    assert "_working_principles_from_doc" not in profile["work_style"]


def test_load_profile_backfills_when_local_has_null_values(
    isolated_profile: Path, tmp_path: Path
) -> None:
    # Bug 4: [null] / [None] local value should trigger backfill.
    isolated_profile.write_text(
        json.dumps(
            {"work_style": {"working_principles": [None]}, "version": 4},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    doc_content = "## 规则一：文档规则\n\nbody\n"
    doc = _write_doc(tmp_path, doc_content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        profile = P.load_profile()
    assert "文档规则" in profile["work_style"]["working_principles"][0]


# ── save_profile does not poison local state (Bug 3) ─────────────────


def test_save_profile_strips_backfilled_values(isolated_profile: Path, tmp_path: Path) -> None:
    # Bug 3: saving a backfilled profile must NOT persist the doc values;
    # local must stay empty so future doc updates keep flowing in.
    doc_content = "## 规则一：文档规则A\n\nbody\n"
    doc = _write_doc(tmp_path, doc_content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        profile = P.load_profile()
        assert profile["work_style"]["_working_principles_from_doc"] is True
        P.save_profile(profile)

    # Re-read the persisted file: working_principles must be empty, no marker.
    persisted = json.loads(isolated_profile.read_text(encoding="utf-8"))
    assert persisted["work_style"]["working_principles"] == []
    assert "_working_principles_from_doc" not in persisted["work_style"]


def test_save_profile_preserves_user_authored_values(isolated_profile: Path) -> None:
    # When user wrote their own values (no backfill marker), save must keep them.
    isolated_profile.write_text(
        json.dumps(
            {"work_style": {"working_principles": ["我的规则"]}, "version": 4},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profile = P.load_profile()
    P.save_profile(profile)
    persisted = json.loads(isolated_profile.read_text(encoding="utf-8"))
    assert persisted["work_style"]["working_principles"] == ["我的规则"]


def test_update_field_does_not_poison_backfill(isolated_profile: Path, tmp_path: Path) -> None:
    # Bug 3 end-to-end: update_field calls load+save; backfill must not leak.
    doc_content = "## 规则一：文档规则\n\nbody\n"
    doc = _write_doc(tmp_path, doc_content)
    with mock.patch.object(P, "_working_principles_doc_path", return_value=doc):
        P.update_field("basic_info", "name", "Tester")
    persisted = json.loads(isolated_profile.read_text(encoding="utf-8"))
    assert persisted["basic_info"]["name"] == "Tester"
    assert persisted["work_style"]["working_principles"] == []


# ── markdown rendering of multi-line bodies (render bug 3.2) ──────────


def test_render_work_style_indents_multiline_principle(isolated_profile: Path) -> None:
    isolated_profile.write_text(
        json.dumps(
            {
                "work_style": {
                    "working_principles": ["规则一：标题\n第一行\n第二行"],
                    "preferred_language": "中文",
                },
                "version": 4,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    md = P.get_profile_markdown()
    # The continuation lines must be indented (4 spaces) so they stay nested
    # under the list item instead of breaking the list structure.
    assert "    第一行" in md
    assert "    第二行" in md
    # The first line is the list item itself.
    assert "  - 规则一：标题" in md
