"""Environment configuration loader for Hermes.

Hermes inherits common account/API environment variables from the main project
repositories. The loading precedence (highest to lowest) is:

1. Process environment variables already set
2. Hermes own `.env` file
3. Main project `.env` files (root and OpenClaw)
4. Default values defined in `Settings`

All user-writable state (config, cache, logs) stays inside the project root
to stay within sandbox allow-listed directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings inherited from the main project environments."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # OpenClaw gateway
    # -------------------------------------------------------------------------
    openclaw_llm_api_key: str | None = Field(default=None, alias="OPENCLAW_LLM_API_KEY")
    openclaw_gateway_port: int = Field(default=18789, alias="OPENCLAW_GATEWAY_PORT")
    openclaw_gateway_token: str | None = Field(default=None, alias="OPENCLAW_GATEWAY_TOKEN")
    openclaw_gateway_password: str | None = Field(default=None, alias="OPENCLAW_GATEWAY_PASSWORD")
    openclaw_state_dir: Path | None = Field(default=None, alias="OPENCLAW_STATE_DIR")
    openclaw_config_path: Path | None = Field(default=None, alias="OPENCLAW_CONFIG_PATH")

    # -------------------------------------------------------------------------
    # Major model providers (OpenAI-compatible or native)
    # -------------------------------------------------------------------------
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_base_url: str | None = Field(default=None, alias="ANTHROPIC_BASE_URL")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )

    # -------------------------------------------------------------------------
    # Regional / alternative providers
    # -------------------------------------------------------------------------
    # Moonshot AI (Kimi)
    moonshot_api_key: str | None = Field(default=None, alias="MOONSHOT_API_KEY")
    moonshot_base_url: str = Field(
        default="https://api.moonshot.cn/v1", alias="MOONSHOT_BASE_URL"
    )
    # Zhipu AI (GLM / z.ai)
    zai_api_key: str | None = Field(default=None, alias="ZAI_API_KEY")
    zai_base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4", alias="ZAI_BASE_URL")
    # Baidu Qianfan
    qianfan_access_key: str | None = Field(default=None, alias="QIANFAN_ACCESS_KEY")
    qianfan_secret_key: str | None = Field(default=None, alias="QIANFAN_SECRET_KEY")
    # Alibaba Qwen / DashScope
    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")
    # Xiaomi MiMo
    xiaomi_api_key: str | None = Field(default=None, alias="XIAOMI_API_KEY")
    # MiniMax
    minimax_api_key: str | None = Field(default=None, alias="MINIMAX_API_KEY")
    minimax_group_id: str | None = Field(default=None, alias="MINIMAX_GROUP_ID")
    # Mistral AI
    mistral_api_key: str | None = Field(default=None, alias="MISTRAL_API_KEY")
    # Novita AI
    novita_api_key: str | None = Field(default=None, alias="NOVITA_API_KEY")
    novita_base_url: str = Field(
        default="https://api.novita.ai/v3/openai", alias="NOVITA_BASE_URL"
    )
    # Ollama (local)
    ollama_base_url: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL")
    # ModelScope (OpenAI-compatible gateway)
    modelscope_api_key: str | None = Field(default=None, alias="MODELSCOPE_API_KEY")
    modelscope_base_url: str = Field(
        default="https://api-inference.modelscope.cn/v1", alias="MODELSCOPE_BASE_URL"
    )
    # OpenAI Live / gateway proxies
    openclaw_live_openai_key: str | None = Field(
        default=None, alias="OPENCLAW_LIVE_OPENAI_KEY"
    )
    openclaw_live_anthropic_key: str | None = Field(
        default=None, alias="OPENCLAW_LIVE_ANTHROPIC_KEY"
    )
    openclaw_live_gemini_key: str | None = Field(
        default=None, alias="OPENCLAW_LIVE_GEMINI_KEY"
    )
    ai_gateway_api_key: str | None = Field(default=None, alias="AI_GATEWAY_API_KEY")
    synthetic_api_key: str | None = Field(default=None, alias="SYNTHETIC_API_KEY")

    openclaw_model_primary: str = Field(
        default="anthropic/claude-sonnet-4-5", alias="OPENCLAW_MODEL_PRIMARY"
    )
    openclaw_model_fallback: str = Field(
        default="openai/gpt-4o", alias="OPENCLAW_MODEL_FALLBACK"
    )

    # -------------------------------------------------------------------------
    # Channels
    # -------------------------------------------------------------------------
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_app_token: str | None = Field(default=None, alias="SLACK_APP_TOKEN")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    discord_bot_token: str | None = Field(default=None, alias="DISCORD_BOT_TOKEN")
    mattermost_bot_token: str | None = Field(default=None, alias="MATTERMOST_BOT_TOKEN")
    mattermost_url: str | None = Field(default=None, alias="MATTERMOST_URL")
    zalo_bot_token: str | None = Field(default=None, alias="ZALO_BOT_TOKEN")
    openclaw_twitch_access_token: str | None = Field(
        default=None, alias="OPENCLAW_TWITCH_ACCESS_TOKEN"
    )
    feishu_app_id: str | None = Field(default=None, alias="FEISHU_APP_ID")
    feishu_app_secret: str | None = Field(default=None, alias="FEISHU_APP_SECRET")
    feishu_verification_token: str | None = Field(
        default=None, alias="FEISHU_VERIFICATION_TOKEN"
    )

    # -------------------------------------------------------------------------
    # Tools / search / media
    # -------------------------------------------------------------------------
    brave_api_key: str | None = Field(default=None, alias="BRAVE_API_KEY")
    perplexity_api_key: str | None = Field(default=None, alias="PERPLEXITY_API_KEY")
    firecrawl_api_key: str | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    xi_api_key: str | None = Field(default=None, alias="XI_API_KEY")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")

    # -------------------------------------------------------------------------
    # Integrations
    # -------------------------------------------------------------------------
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")
    trello_api_key: str | None = Field(default=None, alias="TRELLO_API_KEY")
    trello_api_token: str | None = Field(default=None, alias="TRELLO_API_TOKEN")
    tailscale_auth_key: str | None = Field(default=None, alias="TAILSCALE_AUTH_KEY")

    # -------------------------------------------------------------------------
    # Skillhub
    # -------------------------------------------------------------------------
    skillhub_api_base: str = Field(default="https://lightmake.site", alias="SKILLHUB_API_BASE")
    skillhub_cos_bucket: str = Field(
        default="skills-store-1259584892", alias="SKILLHUB_COS_BUCKET"
    )
    skillhub_cos_region: str = Field(default="ap-guangzhou", alias="SKILLHUB_COS_REGION")

    # -------------------------------------------------------------------------
    # Hermes specific
    # -------------------------------------------------------------------------
    hermes_api_token: str | None = Field(default=None, alias="HERMES_API_TOKEN")
    hermes_log_level: str = Field(default="INFO", alias="HERMES_LOG_LEVEL")
    hermes_skill_default_timeout: float = Field(
        default=300.0, alias="HERMES_SKILL_DEFAULT_TIMEOUT"
    )
    hermes_main_repo_path: Path = Field(
        default=Path("/workspace/OpenClaw/openclaw-main"),
        alias="HERMES_MAIN_REPO_PATH",
    )
    hermes_project_root: Path = Field(
        default=Path(__file__).resolve().parents[2],
        alias="HERMES_PROJECT_ROOT",
    )
    hermes_state_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / ".state",
        alias="HERMES_STATE_DIR",
    )
    hermes_cache_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / ".cache",
        alias="HERMES_CACHE_DIR",
    )
    hermes_profile_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "profile.json",
        alias="HERMES_PROFILE_PATH",
    )

    # Search paths that are consulted for inherited .env files.
    inherit_env_paths: ClassVar[list[Path]] = [
        Path("/workspace/.env"),
        Path("/workspace/OpenClaw/openclaw-main/.env"),
    ]

    def configured_providers(self) -> list[str]:
        """Return names of LLM providers that have API keys configured."""
        provider_keys = [
            ("openai", self.openai_api_key),
            ("anthropic", self.anthropic_api_key),
            ("gemini", self.gemini_api_key or self.google_api_key),
            ("openrouter", self.openrouter_api_key),
            ("moonshot", self.moonshot_api_key),
            ("zai/glm", self.zai_api_key),
            ("qianfan", self.qianfan_access_key and self.qianfan_secret_key),
            ("dashscope/qwen", self.dashscope_api_key),
            ("xiaomi", self.xiaomi_api_key),
            ("minimax", self.minimax_api_key),
            ("mistral", self.mistral_api_key),
            ("novita", self.novita_api_key),
            ("ollama", True),  # local, no key needed by default
            ("modelscope", self.modelscope_api_key),
        ]
        return [name for name, key in provider_keys if key]

    def missing_required(self) -> list[str]:
        """Return a list of environment variables that should be checked.

        Hermes itself does not strictly require any key to be present;
        this returns an empty list by default and is intended as a hook
        for subcommands to surface missing credentials when needed.
        """
        return []


def load_inherited_env() -> None:
    """Load environment variables from main project .env files.

    Existing non-empty environment variables are never overwritten.
    """
    for path in Settings.inherit_env_paths:
        if path.exists():
            load_dotenv(path, override=False, verbose=False)


def load_hermes_env() -> None:
    """Load Hermes own .env file if present.

    Existing non-empty environment variables are never overwritten so that
    explicit exports always win.
    """
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False, verbose=False)


def bootstrap_env() -> None:
    """Bootstrap environment loading with correct precedence.

    Order (highest wins):
    1. Process environment (already present when the process started).
    2. Hermes local .env.
    3. Inherited main-repo .env files.
    4. Default values in Settings.
    """
    load_hermes_env()
    load_inherited_env()


bootstrap_env()

_hermes_settings: Settings | None = None


def get_settings(force_reload: bool = False) -> Settings:
    """Return cached application settings."""
    global _hermes_settings
    if _hermes_settings is None or force_reload:
        _hermes_settings = Settings()
        # Ensure state/cache dirs exist.
        _hermes_settings.hermes_state_dir.mkdir(parents=True, exist_ok=True)
        _hermes_settings.hermes_cache_dir.mkdir(parents=True, exist_ok=True)
    return _hermes_settings
