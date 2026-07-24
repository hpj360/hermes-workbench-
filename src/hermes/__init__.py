"""Hermes - Independent agent layer with inherited environment configuration."""

__version__ = "0.2.0"

from hermes.config import Settings, get_settings
from hermes.skills import SkillInfo, discover_skills, get_skill_path, list_knowledge_docs

__all__ = [
    "Settings",
    "SkillInfo",
    "__version__",
    "discover_skills",
    "get_settings",
    "get_skill_path",
    "list_knowledge_docs",
]
