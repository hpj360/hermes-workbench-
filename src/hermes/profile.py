"""User profile management for Hermes.

Stores and retrieves personal information, interests, skills, and preferences
in a structured JSON file under the project data/ directory.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes.config import get_settings


def _profile_path() -> Path:
    settings = get_settings()
    return settings.hermes_profile_path


def _working_principles_doc_path() -> Path:
    """Path to the project-level persisted working principles document."""
    return Path(__file__).resolve().parents[2] / "knowledge" / "working-principles.md"


# Strict pattern: only `## 规则N：` / `## 规则N:` (N = 中文数字 or arabic) is a rule
# heading. This avoids matching `## 规则补充` / `## 规则附录` (Bug 5).
_RULE_HEADING_RE = re.compile(r"^##\s*规则[一二三四五六七八九十百\d]+\s*[:：]")
_HEADING_RE = re.compile(r"^#+\s")


def _load_working_principles_from_doc() -> list[str]:
    """Parse principle entries from knowledge/working-principles.md.

    Each entry is `## 规则N：标题` followed by a body. The body runs until the
    next rule heading, any other markdown heading (which starts a non-rule
    section and must NOT leak into the rule body), or end of document.
    Trailing ``---`` separator lines (markdown thematic breaks that delimit
    sections but aren't part of the rule content) are stripped from the end
    of each rule body.

    Fenced code blocks (``` / ~~~) are tracked so `#` comment lines inside
    them are not mistaken for markdown headings, and `## 规则N：` text inside
    a code block is not parsed as a rule heading.

    Returns an empty list if the document is missing or unreadable.
    """
    path = _working_principles_doc_path()
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[str] = []
    current_title: str | None = None
    current_body: list[str] = []
    in_code_block = False

    def _flush() -> None:
        nonlocal current_title, current_body
        if current_title is not None:
            # Strip trailing `---` thematic-break lines (and surrounding blank
            # lines) that delimit sections but aren't part of the rule's actual
            # content. A blank line often separates `---` from the next heading.
            body_lines = list(current_body)
            while body_lines and body_lines[-1].strip() in ("", "---"):
                body_lines.pop()
            body = "\n".join(body_lines).strip()
            entries.append(current_title if not body else f"{current_title}\n{body}")
        current_title = None
        current_body = []

    for line in text.splitlines():
        stripped = line.lstrip()
        # Track fenced code blocks — inside ```/~~~ blocks, # lines are
        # comments, not markdown headings.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            if current_title is not None:
                current_body.append(line)
            continue
        if in_code_block:
            if current_title is not None:
                current_body.append(line)
            continue
        if _RULE_HEADING_RE.match(line):
            _flush()
            current_title = line.lstrip("# ").strip()
            current_body = []
        elif _HEADING_RE.match(line):
            # Any other heading ends the current rule's body so trailing
            # non-rule sections (e.g. `## 加载机制`) don't leak in.
            _flush()
        elif current_title is not None:
            current_body.append(line)
    _flush()
    return entries


def _has_meaningful_principles(values: list[Any] | None) -> bool:
    """True if `values` contains at least one non-empty, non-null string."""
    if not values:
        return False
    return any(isinstance(p, str) and p.strip() for p in values)


def load_profile() -> dict[str, Any]:
    """Load the user profile from disk. Returns an empty skeleton if missing.

    If `work_style.working_principles` is empty/meaningless, backfill from the
    persisted project-level document `knowledge/working-principles.md` so that
    any cloned environment inherits the rules. A non-empty local value always
    wins. Backfilled values are NOT persisted by save_profile — the original
    local value (empty) is preserved so future document updates keep flowing
    in (fixes Bug 3 where backfill was written back and broke inheritance).
    """
    path = _profile_path()
    if not path.exists():
        profile = dict(_default_profile())
    else:
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            profile = data
    # Backfill persisted working principles only if local has no meaningful value.
    work_style = profile.setdefault("work_style", {})
    local_principles = work_style.get("working_principles")
    if not _has_meaningful_principles(local_principles):
        doc_principles = _load_working_principles_from_doc()
        if doc_principles:
            # Store backfilled values under a separate key so save_profile can
            # avoid persisting them (keeps local "empty" state for future doc updates).
            work_style["working_principles"] = doc_principles
            work_style["_working_principles_from_doc"] = True
    return profile


def save_profile(profile: dict[str, Any]) -> None:
    """Persist the user profile to disk and update the timestamp.

    Backfilled working_principles (marked with `_working_principles_from_doc`)
    are stripped before writing so the local profile stays "empty" and future
    document updates keep flowing in. This preserves the inheritance mechanism
    (fixes Bug 3 where the first save_profile call poisoned local state).
    """
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    work_style = profile.get("work_style")
    if isinstance(work_style, dict) and work_style.get("_working_principles_from_doc"):
        # Restore local to empty so doc updates remain visible on next load.
        work_style["working_principles"] = []
        work_style.pop("_working_principles_from_doc", None)
    with path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def update_field(section: str, key: str, value: Any) -> dict[str, Any]:
    """Update a single field in the profile and save. Returns the updated profile."""
    profile = load_profile()
    if section not in profile:
        profile[section] = {}
    profile[section][key] = value
    save_profile(profile)
    return profile


def append_to_list(section: str, key: str, items: list[str]) -> dict[str, Any]:
    """Append items to a list field, avoiding duplicates. Returns the updated profile."""
    profile = load_profile()
    if section not in profile:
        profile[section] = {}
    existing: list[str] = profile[section].get(key, []) or []
    for item in items:
        item = item.strip()
        if item and item not in existing:
            existing.append(item)
    profile[section][key] = existing
    save_profile(profile)
    return profile


def get_profile_markdown() -> str:
    """Render the user profile as a human-readable Markdown string."""
    p = load_profile()
    lines: list[str] = ["# 用户画像 / User Profile", ""]

    _render_basic(lines, p)
    _render_pets(lines, p)
    _render_contact(lines, p)
    _render_social_accounts(lines, p)
    _render_career(lines, p)
    _render_skills(lines, p)
    _render_alcohol(lines, p)
    _render_interests(lines, p)
    _render_content(lines, p)
    _render_work_style(lines, p)
    _render_projects(lines, p)
    _render_goals(lines, p)
    _render_notes(lines, p)

    updated = p.get("updated_at", "")
    if updated:
        lines.append(f"---\n*最后更新: {updated}*")

    return "\n".join(lines)


def _join(items: list[str] | None) -> str:
    if not items:
        return "未设置"
    return ", ".join(str(i) for i in items if i)


def _render_basic(lines: list[str], p: dict[str, Any]) -> None:
    basic = p.get("basic_info", {})
    lines.append("## 基本信息")
    lines.append("")
    lines.append(f"- **姓名**: {basic.get('name') or '未设置'}")
    lines.append(f"- **称呼/昵称**: {basic.get('nickname') or '未设置'}")
    lines.append(f"- **性别**: {basic.get('gender') or '未设置'}")
    lines.append(f"- **年龄段**: {basic.get('age_range') or '未设置'}")
    lines.append(f"- **MBTI**: {basic.get('mbti') or '未设置'}")
    lines.append(f"- **所在地**: {basic.get('location') or '未设置'}")
    if basic.get("city_district"):
        lines.append(f"- **常用活动区域**: {basic['city_district']}")
    lines.append(f"- **就业状态**: {basic.get('employment_status') or '未设置'}")
    lines.append(f"- **时区**: {basic.get('timezone') or 'Asia/Shanghai'}")
    lines.append(f"- **职业**: {basic.get('occupation') or '未设置'}")
    lines.append(f"- **行业**: {basic.get('industry') or '未设置'}")
    if basic.get("work_experience_years"):
        lines.append(f"- **工作年限**: {basic['work_experience_years']}年")
    if basic.get("current_base_salary"):
        lines.append(f"- **当前base**: {basic['current_base_salary']}")
    if basic.get("expected_salary"):
        lines.append(f"- **期望薪资**: {basic['expected_salary']}")
    lines.append(f"- **教育背景**: {basic.get('education') or '未设置'}")
    lines.append("")


def _render_pets(lines: list[str], p: dict[str, Any]) -> None:
    pets = p.get("pets", [])
    if not pets:
        return
    lines.append("## 萌宠 🐱")
    lines.append("")
    for pet in pets:
        if isinstance(pet, dict):
            name = pet.get("name", "?")
            gender = pet.get("gender", "")
            age = pet.get("age", "")
            note = pet.get("note", "")
            parts = [f"**{name}**"]
            if gender:
                parts.append(gender)
            if age:
                parts.append(f"{age}岁")
            line = "- " + " · ".join(parts)
            if note:
                line += f"  — {note}"
            lines.append(line)
        else:
            lines.append(f"- {pet}")
    lines.append("")


def _render_contact(lines: list[str], p: dict[str, Any]) -> None:
    contact = p.get("contact", {})
    basic = p.get("basic_info", {})
    lines.append("## 联系方式")
    lines.append("")
    if basic.get("phone"):
        lines.append(f"- **电话**: {basic['phone']}")
    lines.append(f"- **Email**: {contact.get('email') or '未设置'}")
    if contact.get("wechat"):
        lines.append(f"- **微信**: {contact['wechat']}")
    lines.append(f"- **GitHub**: {contact.get('github') or '未设置'}")
    blog_or_site = contact.get("blog") or contact.get("website")
    lines.append(f"- **博客/网站**: {blog_or_site or '未设置'}")
    lines.append("")


def _render_social_accounts(lines: list[str], p: dict[str, Any]) -> None:
    accounts = p.get("social_accounts", {})
    if not accounts:
        return
    lines.append("## 自媒体账号矩阵")
    lines.append("")
    for key, acc in accounts.items():
        if not isinstance(acc, dict):
            continue
        platform = acc.get("platform", key)
        acc_id = acc.get("id") or "未设置"
        fans = acc.get("fans") or "未统计"
        status = acc.get("status") or ""
        line = f"- **{platform}**: `{acc_id}`"
        if fans and fans != "未统计":
            line += f"  · 粉丝：{fans}"
        if status:
            line += f"  · {status}"
        lines.append(line)
    lines.append("")


def _render_skills(lines: list[str], p: dict[str, Any]) -> None:
    skills = p.get("skills", {})
    lines.append("## 技能栈")
    lines.append("")
    lines.append(f"- **编程语言**: {_join(skills.get('programming_languages', []))}")
    lines.append(f"- **框架/库**: {_join(skills.get('frameworks', []))}")
    lines.append(f"- **工具**: {_join(skills.get('tools', []))}")
    lines.append(f"- **领域专长**: {_join(skills.get('domains', []))}")
    lines.append(f"- **自然语言**: {_join(skills.get('languages_spoken', []))}")
    lines.append("")


def _render_career(lines: list[str], p: dict[str, Any]) -> None:
    career = p.get("career")
    if not career:
        return
    lines.append("## 职业履历")
    lines.append("")
    if career.get("summary"):
        lines.append(f"> {career['summary']}")
        lines.append("")
    if career.get("tags"):
        lines.append(f"- **标签**: {_join(career['tags'])}")
    sd = career.get("skills_detail", {})
    if sd:
        lines.append(f"- **SQL与数据能力**: {_join(sd.get('sql_and_data', []))}")
        lines.append(f"- **大数据生态**: {_join(sd.get('big_data_ecosystem', []))}")
        lines.append(f"- **常用平台/工具**: {_join(sd.get('platforms_and_tools', []))}")
    lines.append("")

    work = career.get("work_experience", [])
    if work:
        lines.append("### 工作经历")
        lines.append("")
        for w in work:
            lines.append(f"**{w.get('company', '')}** · {w.get('title', '')}  ({w.get('period', '')})")
            for h in w.get("highlights", []):
                lines.append(f"  - {h}")
            lines.append("")

    proj = career.get("projects", [])
    if proj:
        lines.append("### 项目经历")
        lines.append("")
        for pr in proj:
            lines.append(f"**{pr.get('name', '')}** · {pr.get('role', '')}  ({pr.get('period', '')})")
            if pr.get("description"):
                lines.append(f"  - {pr['description']}")
            lines.append("")

    campus = career.get("campus_experience", [])
    if campus:
        lines.append("### 校园经历")
        lines.append("")
        for c in campus:
            lines.append(f"- {c}")
        lines.append("")


def _render_alcohol(lines: list[str], p: dict[str, Any]) -> None:
    alcohol = p.get("alcohol_preferences")
    if not alcohol:
        return
    lines.append("## 酒类偏好 🍸")
    lines.append("")
    if alcohol.get("identity"):
        lines.append(f"> {alcohol['identity']}")
        lines.append("")

    cb = alcohol.get("craft_beer_ranking", [])
    if cb:
        lines.append(f"- **精酿偏好排名**: {' > '.join(cb)}")

    wk = alcohol.get("whiskey_preference", {})
    if wk:
        wk_rank = wk.get("ranking", [])
        if wk_rank:
            lines.append(f"- **威士忌偏好**: {' > '.join(wk_rank)}")
        fav_dist = wk.get("favorite_distilleries", [])
        fav_bot = wk.get("favorite_bottles", [])
        if fav_dist:
            lines.append(f"  - 喜欢酒厂: {_join(fav_dist)}")
        if fav_bot:
            lines.append(f"  - 喜欢款: {_join(fav_bot)}")

    ct = alcohol.get("cocktail", {})
    if ct:
        ct_style = ct.get("style")
        home_bar = ct.get("home_bar")
        ct_note = ct.get("note", "")
        if ct_style:
            home_marker = "（家里有调酒原料🏠）" if home_bar else ""
            lines.append(f"- **鸡尾酒**: {ct_style}{home_marker}")
            if ct_note:
                lines.append(f"  - {ct_note}")

    gin = alcohol.get("gin", {})
    if gin:
        gin_pref = gin.get("preference")
        gin_brands = gin.get("favorite_brands", [])
        if gin_pref:
            lines.append(f"- **金酒**: {gin_pref}")
        if gin_brands:
            lines.append(f"  - 喜欢品牌: {_join(gin_brands)}")

    lines.append("")


def _render_interests(lines: list[str], p: dict[str, Any]) -> None:
    interests = p.get("interests", {})
    lines.append("## 兴趣爱好")
    lines.append("")
    lines.append(f"- **技术兴趣**: {_join(interests.get('tech_interests', []))}")
    lines.append(f"- **日常爱好**: {_join(interests.get('hobbies', []))}")

    food = interests.get("food")
    if food and isinstance(food, dict):
        pref = food.get("preference")
        sig = food.get("signature_dishes")
        parts = []
        if pref:
            parts.append(pref)
        if sig:
            parts.append(f"拿手：{sig}")
        lines.append(f"- **美食**: {'；'.join(parts)}")
    elif interests.get("food"):
        lines.append(f"- **美食**: {interests['food']}")

    photo = interests.get("photography")
    if photo and isinstance(photo, dict):
        subj = _join(photo.get("subjects", []))
        equip = _join(photo.get("equipment", []))
        lines.append(f"- **摄影**: 拍{subj}（设备：{equip}）")

    fitness = interests.get("fitness")
    if fitness and isinstance(fitness, dict):
        goal = fitness.get("goal")
        freq = fitness.get("frequency")
        parts = []
        if goal:
            parts.append(f"目标：{goal}")
        if freq:
            parts.append(freq)
        lines.append(f"- **健身**: {'，'.join(parts)}")

    ski = interests.get("ski_resorts")
    if ski:
        lines.append(f"- **滑雪常去**: {_join(ski)}")

    sk = interests.get("script_kill")
    if sk and isinstance(sk, dict):
        lines.append(f"- **剧本杀**: 偏好{_join(sk.get('preferred_types', []))}")
    elif interests.get("script_kill"):
        lines.append(f"- **剧本杀**: {interests['script_kill']}")

    if interests.get("theater"):
        lines.append(f"- **话剧**: {interests['theater']}")

    if interests.get("film_directors") or interests.get("film_genres"):
        film_parts = []
        if interests.get("film_directors"):
            film_parts.append(f"喜欢导演：{_join(interests['film_directors'])}")
        if interests.get("film_genres"):
            film_parts.append(f"偏好类型：{_join(interests['film_genres'])}")
        lines.append(f"- **电影**: {'；'.join(film_parts)}")

    lines.append(f"- **音乐**: {_join(interests.get('music', []))}")
    lines.append(f"- **阅读**: {_join(interests.get('reading', []))}")

    if interests.get("investing"):
        lines.append(f"- **投资理财**: {_join(interests['investing'])}")

    other = interests.get("other_interests", [])
    if other:
        lines.append(f"- **其他**: {_join(other)}")
    lines.append("")


def _render_content(lines: list[str], p: dict[str, Any]) -> None:
    cc = p.get("content_creation") or p.get("content_plans")
    if not cc:
        return
    lines.append("## 内容创业计划 🚀")
    lines.append("")
    lines.append(f"- **状态**: {cc.get('status') or '未设置'}")
    styles = cc.get("video_styles")
    if styles:
        lines.append(f"- **视频形式**: {_join(styles)}")
    freq = cc.get("update_frequency")
    if freq:
        lines.append(f"- **更新节奏**: {freq}")
    lines.append(f"- **方向**: {_join(cc.get('directions', []))}")
    lines.append(f"- **平台**: {_join(cc.get('platforms', []))}")
    priority = cc.get("hermes_priority_tasks", [])
    if priority:
        lines.append("- **Hermes 三步落地方案**:")
        for t in priority:
            lines.append(f"  - {t}")
    roles = cc.get("hermes_roles", [])
    if roles:
        lines.append(f"- **Hermes 协作角色**: {_join(roles)}")
    lines.append("")


def _render_work_style(lines: list[str], p: dict[str, Any]) -> None:
    work = p.get("work_style", {})
    lines.append("## 工作风格与偏好")
    lines.append("")
    lines.append(f"- **偏好语言**: {work.get('preferred_language') or '中文'}")
    lines.append(f"- **代码风格**: {_join(work.get('code_style', []))}")
    lines.append(f"- **工作习惯**: {_join(work.get('work_habits', []))}")
    lines.append(f"- **沟通风格**: {_join(work.get('communication_style', []))}")
    lines.append(f"- **偏好工具**: {_join(work.get('tools_preferred', []))}")
    principles = work.get("working_principles", []) or []
    if principles:
        lines.append("- **工作原则/规则**:")
        for principle in principles:
            # Indent embedded newlines so multi-line principle bodies stay
            # nested under the list item instead of breaking list structure.
            indented = str(principle).replace("\n", "\n    ")
            lines.append(f"  - {indented}")
    lines.append("")


def _render_projects(lines: list[str], p: dict[str, Any]) -> None:
    projects = p.get("personal_projects") or p.get("projects", [])
    lines.append("## 参与/关注的项目")
    lines.append("")
    if projects:
        for proj in projects:
            lines.append(f"- {proj}")
    else:
        lines.append("- 未设置")
    lines.append("")


def _render_goals(lines: list[str], p: dict[str, Any]) -> None:
    goals = p.get("goals", {})
    lines.append("## 目标")
    lines.append("")
    lines.append(f"- **短期目标**: {_join(goals.get('short_term', []))}")
    lines.append(f"- **长期目标**: {_join(goals.get('long_term', []))}")
    lines.append(f"- **学习计划**: {_join(goals.get('learning', []))}")
    lines.append("")


def _render_notes(lines: list[str], p: dict[str, Any]) -> None:
    notes = p.get("notes", "")
    if notes:
        lines.append("## 备注")
        lines.append("")
        lines.append(notes)
        lines.append("")


def _default_profile() -> dict[str, Any]:
    return {
        "version": 4,
        "updated_at": None,
        "basic_info": {
            "name": None,
            "nickname": None,
            "gender": None,
            "age_range": None,
            "location": None,
            "city_district": None,
            "timezone": "Asia/Shanghai",
            "occupation": None,
            "industry": None,
            "education": None,
            "phone": None,
            "expected_salary": None,
            "current_base_salary": None,
            "work_experience_years": None,
            "mbti": None,
            "employment_status": None,
        },
        "contact": {
            "email": None,
            "github": "hpj360",
            "wechat": None,
            "blog": None,
            "website": None,
        },
        "social_accounts": {},
        "pets": [],
        "career": {
            "tags": [],
            "summary": None,
            "skills_detail": {
                "sql_and_data": [],
                "big_data_ecosystem": [],
                "platforms_and_tools": [],
            },
            "work_experience": [],
            "projects": [],
            "campus_experience": [],
        },
        "skills": {
            "programming_languages": [],
            "frameworks": [],
            "tools": [],
            "domains": [],
            "languages_spoken": [],
            "skill_level": {},
        },
        "alcohol_preferences": {
            "craft_beer_ranking": [],
            "whiskey_preference": {
                "ranking": [],
                "favorite_distilleries": [],
                "favorite_bottles": [],
            },
            "cocktail": {"style": None, "home_bar": False, "note": None},
            "gin": {"preference": None, "favorite_brands": []},
            "identity": None,
        },
        "interests": {
            "tech_interests": [],
            "hobbies": [],
            "reading": [],
            "music": [],
            "sports": [],
            "film_directors": [],
            "film_genres": [],
            "food": {"preference": None, "signature_dishes": None, "style": None},
            "photography": {"subjects": [], "equipment": []},
            "script_kill": {"preferred_types": []},
            "theater": None,
            "investing": [],
            "ski_resorts": [],
            "fitness": {"goal": None, "frequency": None},
            "other_interests": [],
        },
        "content_creation": {
            "status": None,
            "video_styles": [],
            "update_frequency": None,
            "directions": [],
            "platforms": [],
            "hermes_priority_tasks": [],
            "hermes_roles": [],
        },
        "work_style": {
            "preferred_language": "中文",
            "code_style": [],
            "work_habits": [],
            "communication_style": [],
            "tools_preferred": [],
            "working_principles": [],
        },
        "personal_projects": [],
        "goals": {
            "short_term": [],
            "long_term": [],
            "learning": [],
        },
        "notes": "",
    }
