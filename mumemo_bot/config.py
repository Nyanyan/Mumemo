from dataclasses import dataclass
from pathlib import Path
import os
import shlex

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTE_BUILD_COMMAND = ["node", "scripts/build-route-pages.mjs"]


@dataclass(frozen=True)
class BotConfig:
    slack_bot_token: str
    slack_app_token: str
    slack_channel_id: str
    slack_channel_name: str
    data_path: Path
    asset_dir: Path
    asset_url_prefix: str
    original_asset_dir: Path
    default_image: str
    route_build_command: list[str]
    github_repo_url: str
    github_branch: str = "main"
    site_base_url: str = ""
    nominatim_endpoint: str = "https://nominatim.openstreetmap.org/search"
    nominatim_user_agent: str = ""
    nominatim_email: str = ""
    nominatim_timeout_seconds: float = 10.0

    @property
    def slack_channel_label(self) -> str:
        if self.slack_channel_name:
            return f"#{self.slack_channel_name} ({self.slack_channel_id})"
        return self.slack_channel_id

    @classmethod
    def from_env(cls) -> "BotConfig":
        load_environment()
        data_path = _path_env("MUMEMO_DATA_PATH", "docs/data/memos.json")
        asset_dir = _path_env("MUMEMO_SLACK_ASSET_DIR", "docs/assets/slack")
        original_asset_dir = _path_env("MUMEMO_SLACK_ORIGINAL_ASSET_DIR", "originals/slack")
        route_build_command = _command_env(
            "MUMEMO_ROUTE_BUILD_COMMAND",
            DEFAULT_ROUTE_BUILD_COMMAND,
        )

        return cls(
            slack_bot_token=_required_env("SLACK_BOT_TOKEN"),
            slack_app_token=_required_env("SLACK_APP_TOKEN"),
            slack_channel_id=_required_env("SLACK_CHANNEL_ID"),
            slack_channel_name=os.getenv("SLACK_CHANNEL_NAME", ""),
            data_path=data_path,
            asset_dir=asset_dir,
            asset_url_prefix=os.getenv(
                "MUMEMO_SLACK_ASSET_URL_PREFIX",
                "/assets/slack",
            ).rstrip("/"),
            original_asset_dir=original_asset_dir,
            default_image=_default_image_env(),
            route_build_command=route_build_command,
            github_repo_url=os.getenv(
                "MUMEMO_GITHUB_REPO_URL",
                "https://github.com/Nyanyan/Mumemo",
            ).strip().rstrip("/"),
            github_branch=os.getenv("MUMEMO_GITHUB_BRANCH", "main").strip() or "main",
            site_base_url=_site_base_url_env(),
            nominatim_endpoint=os.getenv(
                "MUMEMO_NOMINATIM_ENDPOINT",
                "https://nominatim.openstreetmap.org/search",
            ).strip(),
            nominatim_user_agent=_required_env("MUMEMO_NOMINATIM_USER_AGENT"),
            nominatim_email=os.getenv("MUMEMO_NOMINATIM_EMAIL", "").strip(),
            nominatim_timeout_seconds=_float_env("MUMEMO_NOMINATIM_TIMEOUT_SECONDS", 10.0),
        )


def load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _path_env(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default))
    if value.is_absolute():
        return value
    return PROJECT_ROOT / value


def _command_env(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)
    if not raw_value:
        return list(default)
    command = shlex.split(raw_value, posix=os.name != "nt")
    if not command:
        raise RuntimeError(f"{name} must not be empty")
    return command


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number") from error


def _default_image_env() -> str:
    value = os.getenv("MUMEMO_DEFAULT_IMAGE", "/website_icon_small.png").strip()
    if value == "/website_icon.png":
        return "/website_icon_small.png"
    return value or "/website_icon_small.png"

def _site_base_url_env() -> str:
    raw_value = os.getenv("MUMEMO_SITE_BASE_URL", "").strip()
    if not raw_value:
        cname_path = PROJECT_ROOT / "docs" / "CNAME"
        if cname_path.exists():
            lines = cname_path.read_text(encoding="utf-8").splitlines()
            raw_value = lines[0].strip() if lines else ""
    if not raw_value:
        return ""
    if not raw_value.startswith(("http://", "https://")):
        raw_value = f"https://{raw_value}"
    return raw_value.rstrip("/")


def mask_secret(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:8]}...{value[-4:]}"
