from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SlackImageFile:
    file_id: str
    name: str
    mimetype: str
    download_url: str


@dataclass(frozen=True)
class MumemoSlackPost:
    channel_id: str
    message_ts: str
    user_id: str
    title: str
    body: str
    images: list[SlackImageFile]

    @classmethod
    def from_message(cls, channel_id: str, message: dict[str, Any]) -> "MumemoSlackPost":
        text = str(message.get("text") or "")
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            raise ValueError("Slack message first line is empty; cannot create title")

        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        return cls(
            channel_id=channel_id,
            message_ts=str(message.get("ts") or ""),
            user_id=str(message.get("user") or "unknown"),
            title=title,
            body=body,
            images=_image_files(message),
        )


def _image_files(message: dict[str, Any]) -> list[SlackImageFile]:
    images: list[SlackImageFile] = []
    files = message.get("files", [])
    if not isinstance(files, list):
        return images

    for file_data in files:
        if not isinstance(file_data, dict):
            continue
        mimetype = str(file_data.get("mimetype") or "")
        if not mimetype.startswith("image/"):
            continue
        download_url = file_data.get("url_private_download") or file_data.get("url_private")
        if not isinstance(download_url, str) or not download_url:
            continue
        file_id = str(file_data.get("id") or "file")
        name = str(file_data.get("name") or f"{file_id}.image")
        images.append(
            SlackImageFile(
                file_id=file_id,
                name=name,
                mimetype=mimetype,
                download_url=download_url,
            )
        )
    return images