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
    default_image: str
    route_build_command: list[str]

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
            default_image=os.getenv("MUMEMO_DEFAULT_IMAGE", "/website_icon.png"),
            route_build_command=route_build_command,
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


def mask_secret(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:8]}...{value[-4:]}"