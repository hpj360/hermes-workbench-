"""Hermes CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from hermes.config import Settings, get_settings
from hermes.logging import setup_logging
from hermes.profile import get_profile_markdown, load_profile
from hermes.skills import discover_skills, knowledge_dir, list_knowledge_docs, skills_dir
from hermes.workbench.cli import add_workbench_subparser


def cmd_start(args: argparse.Namespace) -> int:
    logger = logging.getLogger("hermes")
    settings = get_settings()
    logger.info("Hermes started")
    logger.info("Project root: %s", settings.hermes_project_root)
    logger.info("Main repo path: %s", settings.hermes_main_repo_path)
    logger.info("Primary model: %s", settings.openclaw_model_primary)
    logger.info("Configured providers: %s", ", ".join(settings.configured_providers()) or "(none)")
    logger.info("State dir: %s", settings.hermes_state_dir)
    logger.info("Cache dir: %s", settings.hermes_cache_dir)
    return 0


def cmd_skills_list(args: argparse.Namespace) -> int:
    skills = discover_skills()
    if not skills:
        print(f"No skills found in {skills_dir()}")
        return 0
    print(f"Installed skills ({len(skills)}):")
    for s in skills:
        meta_desc = ""
        if s.meta and isinstance(s.meta, dict):
            meta_desc = s.meta.get("description", "") or ""
        flags = []
        flags.append("md" if s.has_skill_md else "  ")
        flags.append("meta" if s.has_meta else "    ")
        line = f"  [{ '|'.join(flags) }] {s.name}"
        if meta_desc:
            line += f"  - {meta_desc}"
        print(line)
    return 0


def cmd_knowledge_list(args: argparse.Namespace) -> int:
    docs = list_knowledge_docs()
    if not docs:
        print(f"No knowledge docs found in {knowledge_dir()}")
        return 0
    print(f"Knowledge documents ({len(docs)}):")
    for d in docs:
        print(f"  - {d.name}")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    settings = get_settings()
    print("[paths]")
    print(f"  project_root      = {settings.hermes_project_root}")
    print(f"  main_repo_path    = {settings.hermes_main_repo_path}")
    print(f"  state_dir         = {settings.hermes_state_dir}")
    print(f"  cache_dir         = {settings.hermes_cache_dir}")
    print(f"  skills_dir        = {skills_dir()}")
    print(f"  knowledge_dir     = {knowledge_dir()}")
    print()
    print("[models]")
    print(f"  primary           = {settings.openclaw_model_primary}")
    print(f"  fallback          = {settings.openclaw_model_fallback}")
    print(f"  providers_ready   = {', '.join(settings.configured_providers()) or '(none)'}")
    print()
    print("[gateway]")
    print(f"  gateway_port      = {settings.openclaw_gateway_port}")
    print(f"  gateway_token     = {'set' if settings.openclaw_gateway_token else 'unset'}")
    print()
    print("[channels]")
    print(f"  slack_bot_token   = {'set' if settings.slack_bot_token else 'unset'}")
    print(f"  slack_app_token   = {'set' if settings.slack_app_token else 'unset'}")
    print(f"  telegram_token    = {'set' if settings.telegram_bot_token else 'unset'}")
    print(f"  discord_token     = {'set' if settings.discord_bot_token else 'unset'}")
    print(f"  feishu_app_id     = {'set' if settings.feishu_app_id else 'unset'}")
    print()
    print("[tools]")
    print(f"  brave_api_key     = {'set' if settings.brave_api_key else 'unset'}")
    print(f"  tavily_api_key    = {'set' if settings.tavily_api_key else 'unset'}")
    print(f"  perplexity_key    = {'set' if settings.perplexity_api_key else 'unset'}")
    print(f"  firecrawl_key     = {'set' if settings.firecrawl_api_key else 'unset'}")
    print(f"  github_token      = {'set' if settings.github_token else 'unset'}")
    print(f"  notion_api_key    = {'set' if settings.notion_api_key else 'unset'}")
    print(f"  trello_key/token  = {settings.trello_api_key and settings.trello_api_token and 'set' or 'unset'}")
    print()
    print("[skillhub]")
    print(f"  api_base          = {settings.skillhub_api_base}")
    print(f"  cos_bucket        = {settings.skillhub_cos_bucket}")
    print(f"  cos_region        = {settings.skillhub_cos_region}")
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = load_profile()
    if args.json:
        import json
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    else:
        print(get_profile_markdown())
    return 0


def cmd_profile_init(args: argparse.Namespace) -> int:
    """Initialize profile.json from example or defaults."""
    import json as _json

    settings = get_settings()
    profile_path = settings.hermes_profile_path

    if profile_path.exists() and not args.force:
        print(f"Profile already exists at {profile_path}. Use --force to overwrite.")
        return 1

    example_path = profile_path.parent / "profile.example.json"
    if example_path.exists():
        profile = _json.loads(example_path.read_text(encoding="utf-8"))
        print(f"Initialized profile from {example_path}")
    else:
        from hermes.profile import _default_profile
        profile = _default_profile()
        print("Initialized profile from defaults")

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(_json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written to {profile_path}")
    return 0


def _check_skill_dependencies(settings: Settings) -> list[str]:
    """Check all skills' required bins/env and return warning strings."""
    import shutil as _shutil

    warnings: list[str] = []
    try:
        from hermes.workbench.skill_runner import SkillRunner

        runner = SkillRunner(base_dir=settings.hermes_project_root / "skills")
        for spec in runner.discover():
            missing_bins = [
                b for b in spec.requires_bins if _shutil.which(b) is None
            ]
            if missing_bins:
                warnings.append(
                    f"Skill '{spec.name}' missing binaries: {', '.join(missing_bins)}"
                )
            missing_env = [
                e for e in spec.requires_env if not os.environ.get(e)
            ]
            if missing_env:
                warnings.append(
                    f"Skill '{spec.name}' missing env vars: {', '.join(missing_env)}"
                )
    except Exception:  # noqa: BLE001, S110
        pass  # Soft degradation: skills dir may not exist
    return warnings


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run health checks on the Hermes environment (degraded-friendly)."""
    settings = get_settings()
    issues: list[str] = []
    warnings: list[str] = []

    if not settings.hermes_project_root.exists():
        issues.append(f"Project root missing: {settings.hermes_project_root}")
    if not settings.hermes_main_repo_path.exists():
        warnings.append(f"Main repo path not found: {settings.hermes_main_repo_path}")

    providers = settings.configured_providers()
    if not providers:
        warnings.append("No LLM provider API keys configured; set at least one in .env")

    if not settings.openclaw_gateway_token:
        warnings.append("OPENCLAW_GATEWAY_TOKEN is unset (recommended for production)")

    skills_count = len(discover_skills())
    docs_count = len(list_knowledge_docs())

    # Check skill dependencies
    warnings.extend(_check_skill_dependencies(settings))

    print("=== Hermes Doctor ===")
    print(f"Python:          {sys.version.split()[0]}")
    print(f"Project root:    {settings.hermes_project_root}")
    print(f"Main repo path:  {settings.hermes_main_repo_path}")
    print(f"Skills installed: {skills_count}")
    print(f"Knowledge docs:  {docs_count}")
    print(f"Providers ready: {', '.join(providers) or '(none)'}")
    print()

    if warnings:
        print("[warnings]")
        for w in warnings:
            print(f"  ! {w}")
    if issues:
        print("[errors]")
        for e in issues:
            print(f"  X {e}")
        return 1

    if not warnings:
        print("All checks passed.")
    else:
        print("Doctor completed with warnings.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes",
        description="Hermes Agent - independent agent layer with inherited config",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level (default: from HERMES_LOG_LEVEL or INFO)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional file path to write logs to",
    )

    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("start", help="Start Hermes (default)").set_defaults(func=cmd_start)

    p_skills = sub.add_parser("skills", help="Manage installed skills")
    p_skills_sub = p_skills.add_subparsers(dest="skills_cmd", required=True)
    p_skills_sub.add_parser("list", help="List installed skills").set_defaults(func=cmd_skills_list)

    p_know = sub.add_parser("knowledge", help="List knowledge documents")
    p_know_sub = p_know.add_subparsers(dest="know_cmd", required=True)
    p_know_sub.add_parser("list", help="List knowledge docs").set_defaults(func=cmd_knowledge_list)

    p_cfg = sub.add_parser("config", help="Show effective configuration")
    p_cfg_sub = p_cfg.add_subparsers(dest="cfg_cmd", required=True)
    p_cfg_sub.add_parser("show", help="Print current configuration").set_defaults(func=cmd_config_show)

    sub.add_parser("doctor", help="Run environment health checks").set_defaults(func=cmd_doctor)

    p_profile = sub.add_parser("profile", help="Manage user profile")
    p_profile_sub = p_profile.add_subparsers(dest="profile_cmd", required=True)
    p_profile_show = p_profile_sub.add_parser("show", help="Show user profile")
    p_profile_show.add_argument("--json", action="store_true", help="Output raw JSON")
    p_profile_show.set_defaults(func=cmd_profile_show)
    p_profile_init = p_profile_sub.add_parser("init", help="Initialize profile.json from example or defaults")
    p_profile_init.add_argument("--force", action="store_true", help="Overwrite existing profile")
    p_profile_init.set_defaults(func=cmd_profile_init)

    add_workbench_subparser(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    log_level = args.log_level or settings.hermes_log_level
    setup_logging(level=log_level, log_file=args.log_file)

    func = getattr(args, "func", cmd_start)
    try:
        return func(args)
    except Exception:  # degraded-friendly: never crash silently
        logging.getLogger("hermes").exception("Command failed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
