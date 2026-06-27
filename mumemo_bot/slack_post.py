from dataclasses import dataclass
from typing import Any
import re


URL_PATTERN = re.compile(r"https?://[^\s<>\"'|]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,、。)）]］}>」』"


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

    @property
    def urls(self) -> list[str]:
        return _urls_in_text(f"{self.title}\n{self.body}")

    def with_urls(self, urls: list[str]) -> "MumemoSlackPost":
        original_urls = self.urls
        clean_urls = [_clean_replacement_url(url) for url in urls]
        if len(clean_urls) != len(original_urls):
            raise ValueError(
                f"URLの件数が一致しません: {len(original_urls)}件のURLを入力してください"
            )

        title, used = _replace_urls_in_text(self.title, clean_urls, 0)
        body, used = _replace_urls_in_text(self.body, clean_urls, used)
        if used != len(clean_urls):
            raise ValueError("URLの置換に失敗しました")

        return MumemoSlackPost(
            channel_id=self.channel_id,
            message_ts=self.message_ts,
            user_id=self.user_id,
            title=title,
            body=body,
            images=self.images,
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


def _urls_in_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_PATTERN.finditer(text):
        url = _strip_trailing_punctuation(match.group(0))
        if url:
            urls.append(url)
    return urls


def _replace_urls_in_text(text: str, urls: list[str], start_index: int) -> tuple[str, int]:
    output: list[str] = []
    last_index = 0
    url_index = start_index

    for match in URL_PATTERN.finditer(text):
        raw_url = match.group(0)
        stripped_url = _strip_trailing_punctuation(raw_url)
        if not stripped_url:
            continue
        trim_length = len(raw_url) - len(stripped_url)
        match_end = match.end() - trim_length
        output.append(text[last_index : match.start()])
        output.append(urls[url_index])
        last_index = match_end
        url_index += 1

    output.append(text[last_index:])
    return "".join(output), url_index


def _strip_trailing_punctuation(url: str) -> str:
    return url.rstrip(TRAILING_URL_PUNCTUATION)


def _clean_replacement_url(url: str) -> str:
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("URLは空にできません")
    if any(character.isspace() for character in clean_url):
        raise ValueError("URLに空白を含めることはできません")
    if not clean_url.lower().startswith(("http://", "https://")):
        raise ValueError("URLは http:// または https:// で始めてください")
    return clean_url
