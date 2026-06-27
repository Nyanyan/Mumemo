"""Slack Block Kit views for Mumemo bot."""

from __future__ import annotations

from typing import Any
import json


APPROVE_MEMO_ACTION_ID = "mumemo_approve_post"
OVERWRITE_REVIEW_POST_ACTION_ID = "mumemo_overwrite_review_post"
OVERWRITE_EXISTING_MEMO_ACTION_ID = "mumemo_overwrite_existing_memo"
PUBLISH_SEPARATE_MEMO_ACTION_ID = "mumemo_publish_separate_memo"
RELOAD_REVIEW_ACTION_ID = "mumemo_reload_review"
DISMISS_REVIEW_ACTION_ID = "mumemo_dismiss_review"
EDIT_REVIEW_URLS_ACTION_ID = "mumemo_edit_review_urls"
SELECT_REVIEW_THUMBNAIL_ACTION_ID = "mumemo_select_review_thumbnail"
EDIT_MEMO_ACTION_ID = "mumemo_edit_memo"
DELETE_MEMO_ACTION_ID = "mumemo_delete_memo"
MEMO_EDIT_CALLBACK_ID = "mumemo_edit_modal"
MEMO_REVIEW_URLS_CALLBACK_ID = "mumemo_review_urls_modal"

TITLE_BLOCK_ID = "title"
BODY_BLOCK_ID = "body"
IMAGE_BLOCK_ID = "image"
IMAGES_BLOCK_ID = "images"
UPLOAD_IMAGES_BLOCK_ID = "upload_images"
UPLOAD_IMAGES_ACTION_ID = "upload_images"
URLS_BLOCK_ID = "urls"
VALUE_ACTION_ID = "value"
THUMBNAIL_SELECT_SEPARATOR = "|"


def review_blocks(
    *,
    channel_id: str,
    message_ts: str,
    title: str,
    body: str,
    image_count: int,
    urls: list[str],
    title_conflict: Any | None,
    status_text: str | None,
    buttons_enabled: bool,
    images: list[Any] | None = None,
) -> list[dict[str, Any]]:
    images = images or []
    body_preview = body.strip() or "(本文なし)"
    body_preview = _truncate(body_preview, 1800)
    thumbnail_label = _thumbnail_label(images[0], 0) if images else ""
    thumbnail_line = (
        f"\n*サムネイル:* {_mrkdwn_text(thumbnail_label)}"
        if thumbnail_label
        else ""
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Mumemo 下書き*\n"
                    f"*タイトル:* {_mrkdwn_text(title)}\n"
                    f"*本文:*\n```{_code_text(body_preview)}```\n"
                    f"*添付画像:* {image_count}件"
                    f"{thumbnail_line}"
                ),
            },
        }
    ]

    if urls:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*検出URL*\n" + _url_list_text(urls),
                },
            }
        )

    if title_conflict is not None:
        existing_body = _truncate(str(title_conflict.body).strip() or "(本文なし)", 1000)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*同じタイトルの既存投稿があります*\n"
                        f"*既存投稿:* {_mrkdwn_text(title_conflict.title)}\n"
                        f"*本文*\n```{_code_text(existing_body)}```\n"
                        f"*画像:* {title_conflict.image_count}件"
                    ),
                },
            }
        )

    if status_text:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*状態:* {_mrkdwn_text(status_text)}",
                    }
                ],
            }
        )

    if buttons_enabled:
        value_data = {
            "channel_id": channel_id,
            "message_ts": message_ts,
        }
        if title_conflict is not None:
            value_data["memo_id"] = title_conflict.id
        value = json.dumps(value_data, ensure_ascii=False)

        elements: list[dict[str, Any]] = []
        if title_conflict is None:
            elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "承認して公開"},
                    "style": "primary",
                    "action_id": APPROVE_MEMO_ACTION_ID,
                    "value": value,
                }
            )
        else:
            elements.extend(
                [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "既存投稿に追記"},
                        "style": "primary",
                        "action_id": OVERWRITE_EXISTING_MEMO_ACTION_ID,
                        "value": value,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "既存投稿に追記しますか?"},
                            "text": {
                                "type": "mrkdwn",
                                "text": "既存投稿の末尾に、このSlack投稿の本文と画像を追加します。",
                            },
                            "confirm": {"type": "plain_text", "text": "追記"},
                            "deny": {"type": "plain_text", "text": "戻る"},
                        },
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "別で投稿"},
                        "action_id": PUBLISH_SEPARATE_MEMO_ACTION_ID,
                        "value": value,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "上書き投稿"},
                        "style": "danger",
                        "action_id": OVERWRITE_REVIEW_POST_ACTION_ID,
                        "value": value,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "上書き投稿しますか?"},
                            "text": {
                                "type": "mrkdwn",
                                "text": "既存投稿のURLを保ったまま、本文と画像をこのSlack投稿で置き換えます。",
                            },
                            "confirm": {"type": "plain_text", "text": "上書き"},
                            "deny": {"type": "plain_text", "text": "戻る"},
                        },
                    },
                ]
            )
        thumbnail_options = _thumbnail_select_options(message_ts, images)
        if len(thumbnail_options) > 1:
            elements.append(
                {
                    "type": "static_select",
                    "placeholder": {"type": "plain_text", "text": "サムネを選択"},
                    "action_id": SELECT_REVIEW_THUMBNAIL_ACTION_ID,
                    "options": thumbnail_options,
                    "initial_option": thumbnail_options[0],
                }
            )
        if urls:
            elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "URL修正"},
                    "action_id": EDIT_REVIEW_URLS_ACTION_ID,
                    "value": value,
                }
            )
        elements.extend(
            [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "再読み込み"},
                    "action_id": RELOAD_REVIEW_ACTION_ID,
                    "value": value,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "破棄"},
                    "style": "danger",
                    "action_id": DISMISS_REVIEW_ACTION_ID,
                    "value": value,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "下書きを破棄しますか?"},
                        "text": {
                            "type": "mrkdwn",
                            "text": "このSlack上の下書きだけを破棄します。元投稿とWebサイトは変更しません。",
                        },
                        "confirm": {"type": "plain_text", "text": "破棄"},
                        "deny": {"type": "plain_text", "text": "戻る"},
                    },
                },
            ]
        )
        for chunk in _chunks(elements, 5):
            blocks.append({"type": "actions", "elements": chunk})
    return blocks


def review_urls_modal_view(
    *,
    post: Any,
    channel_id: str,
    message_ts: str,
    review_message_ts: str,
) -> dict[str, Any]:
    metadata = json.dumps(
        {
            "channel_id": channel_id,
            "message_ts": message_ts,
            "review_message_ts": review_message_ts,
        },
        ensure_ascii=False,
    )
    return {
        "type": "modal",
        "callback_id": MEMO_REVIEW_URLS_CALLBACK_ID,
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": "URL修正"},
        "submit": {"type": "plain_text", "text": "反映"},
        "close": {"type": "plain_text", "text": "閉じる"},
        "blocks": [
            {
                "type": "input",
                "block_id": URLS_BLOCK_ID,
                "label": {"type": "plain_text", "text": "URL"},
                "hint": {"type": "plain_text", "text": "1行につき1つ、表示順のまま修正してください。"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": VALUE_ACTION_ID,
                    "multiline": True,
                    "initial_value": _input_initial("\n".join(post.urls), 2900),
                },
            }
        ],
    }


def manage_blocks(
    *,
    items: list[Any],
    total_count: int,
    shown_count: int,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Mumemo 投稿整理*\n新しい順に {shown_count}/{total_count} 件を表示しています。",
            },
        }
    ]

    if not items:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "整理できる投稿はまだありません。"},
            }
        )
        return blocks

    for item in items:
        body_preview = _truncate(item.body.replace("\n", " ").strip(), 140)
        if not body_preview:
            body_preview = "本文なし"
        value = json.dumps({"memo_id": item.id}, ensure_ascii=False)
        title_label = f"{item.title} (固定)" if item.fixed else item.title
        elements: list[dict[str, Any]] = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "編集"},
                "action_id": EDIT_MEMO_ACTION_ID,
                "value": value,
            }
        ]
        if not item.fixed:
            elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "削除"},
                    "style": "danger",
                    "action_id": DELETE_MEMO_ACTION_ID,
                    "value": value,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "削除しますか?"},
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{_mrkdwn_text(item.title)}* をMumemoの一覧から削除します。関連するローカル画像とページフォルダも削除します。",
                        },
                        "confirm": {"type": "plain_text", "text": "削除"},
                        "deny": {"type": "plain_text", "text": "戻る"},
                    },
                }
            )
        blocks.extend(
            [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*{_mrkdwn_text(title_label)}*\n"
                            f"{_mrkdwn_text(body_preview)}\n"
                            f"画像: {item.image_count}件"
                        ),
                    },
                },
                {"type": "actions", "elements": elements},
            ]
        )
    return blocks[:50]


def edit_modal_view(
    *,
    memo: Any,
    channel_id: str,
    message_ts: str | None,
    site_base_url: str = "",
) -> dict[str, Any]:
    metadata = json.dumps(
        {
            "memo_id": memo.id,
            "channel_id": channel_id,
            "message_ts": message_ts,
        },
        ensure_ascii=False,
    )
    image_reference = _image_reference_text(memo.images, site_base_url)
    order_initial = _image_order_initial(memo.images)
    primary_initial = _primary_image_initial(memo.image, memo.images)

    blocks: list[dict[str, Any]] = [
        {
            "type": "input",
            "block_id": TITLE_BLOCK_ID,
            "label": {"type": "plain_text", "text": "タイトル"},
            "element": {
                "type": "plain_text_input",
                "action_id": VALUE_ACTION_ID,
                "initial_value": _input_initial(memo.title, 150),
            },
        },
        {
            "type": "input",
            "block_id": BODY_BLOCK_ID,
            "label": {"type": "plain_text", "text": "本文"},
            "element": {
                "type": "plain_text_input",
                "action_id": VALUE_ACTION_ID,
                "multiline": True,
                "initial_value": _input_initial(memo.body, 2900),
            },
        },
    ]

    if image_reference:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": image_reference},
            }
        )

    blocks.extend(
        [
            {
                "type": "input",
                "block_id": IMAGE_BLOCK_ID,
                "optional": True,
                "label": {"type": "plain_text", "text": "サムネイル画像番号"},
                "hint": {"type": "plain_text", "text": "画像1、画像2の番号で指定します。空欄なら画像順の先頭を使います。"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": VALUE_ACTION_ID,
                    "initial_value": _input_initial(primary_initial, 30),
                },
            },
            {
                "type": "input",
                "block_id": IMAGES_BLOCK_ID,
                "optional": True,
                "label": {"type": "plain_text", "text": "画像の順序"},
                "hint": {"type": "plain_text", "text": "1行に1つずつ画像番号を並べます。行を入れ替えると表示順が変わり、行を消すと画像を外します。"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": VALUE_ACTION_ID,
                    "multiline": True,
                    "initial_value": _input_initial(order_initial, 2900),
                },
            },
            {
                "type": "input",
                "block_id": UPLOAD_IMAGES_BLOCK_ID,
                "optional": True,
                "label": {"type": "plain_text", "text": "画像を追加"},
                "hint": {"type": "plain_text", "text": "ここで選んだ画像は、画像の順序の末尾に追加されます。"},
                "element": {
                    "type": "file_input",
                    "action_id": UPLOAD_IMAGES_ACTION_ID,
                    "filetypes": ["jpg", "jpeg", "png", "gif", "webp"],
                    "max_files": 10,
                },
            },
        ]
    )

    return {
        "type": "modal",
        "callback_id": MEMO_EDIT_CALLBACK_ID,
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": "Mumemo編集"},
        "submit": {"type": "plain_text", "text": "保存"},
        "close": {"type": "plain_text", "text": "閉じる"},
        "blocks": blocks,
    }


def modal_value(view: dict[str, Any], block_id: str) -> str:
    values = view.get("state", {}).get("values", {})
    block = values.get(block_id, {})
    action = block.get(VALUE_ACTION_ID, {})
    return str(action.get("value") or "")


def modal_file_values(view: dict[str, Any], block_id: str) -> list[Any]:
    values = view.get("state", {}).get("values", {})
    block = values.get(block_id, {})
    action = block.get(UPLOAD_IMAGES_ACTION_ID, {})
    files = action.get("files") or action.get("selected_files") or []
    return files if isinstance(files, list) else []


def decode_thumbnail_select_value(value: str) -> tuple[str, str]:
    message_ts, separator, file_id = str(value).partition(THUMBNAIL_SELECT_SEPARATOR)
    if not separator or not message_ts or not file_id:
        raise ValueError("Slack thumbnail selection value must contain message_ts and file_id")
    return message_ts, file_id

def decode_action_value(action: dict[str, Any]) -> dict[str, Any]:
    raw_value = str(action.get("value") or "{}")
    value = json.loads(raw_value)
    if not isinstance(value, dict):
        raise ValueError("Slack action value must be an object")
    return value


def _thumbnail_select_options(message_ts: str, images: list[Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for index, image in enumerate(images[:100]):
        file_id = _image_file_id(image)
        if not file_id:
            continue
        options.append(
            {
                "text": {
                    "type": "plain_text",
                    "text": _truncate(_thumbnail_label(image, index), 75),
                },
                "value": _thumbnail_select_value(message_ts, file_id),
            }
        )
    return options


def _thumbnail_select_value(message_ts: str, file_id: str) -> str:
    return f"{message_ts}{THUMBNAIL_SELECT_SEPARATOR}{file_id}"


def _thumbnail_label(image: Any, index: int) -> str:
    name = str(getattr(image, "name", "") or "").strip()
    file_id = _image_file_id(image)
    label = name or file_id or "image"
    return f"{index + 1}. {label}"


def _image_file_id(image: Any) -> str:
    return str(getattr(image, "file_id", "") or "").strip()


def _image_reference_text(images: list[str], site_base_url: str) -> str:
    if not images:
        return ""
    lines = ["*\u753b\u50cf\u4e00\u89a7*"]
    for index, image_url in enumerate(images, start=1):
        public_url = _public_site_url(site_base_url, image_url)
        lines.append(f"<{_mrkdwn_url(public_url)}|\u753b\u50cf{index}>")
    return _truncate("\n".join(lines), 2900)


def _image_order_initial(images: list[str]) -> str:
    return "\n".join(str(index) for index in range(1, len(images) + 1))


def _primary_image_initial(image: str, images: list[str]) -> str:
    try:
        return str(images.index(image) + 1)
    except ValueError:
        return "1" if images else ""


def _public_site_url(site_base_url: str, image_url: str) -> str:
    clean_url = str(image_url or "").strip()
    if not clean_url:
        return ""
    if clean_url.startswith(("http://", "https://")):
        return clean_url
    if not clean_url.startswith("/"):
        clean_url = f"/{clean_url}"
    base_url = str(site_base_url or "").strip().rstrip("/")
    return f"{base_url}{clean_url}" if base_url else clean_url


def _mrkdwn_url(url: str) -> str:
    return (
        str(url)
        .replace("\\", "%5C")
        .replace(" ", "%20")
        .replace("<", "%3C")
        .replace(">", "%3E")
    )

def _url_list_text(urls: list[str]) -> str:
    lines = [f"{index + 1}. <{_mrkdwn_text(url)}>" for index, url in enumerate(urls)]
    return _truncate("\n".join(lines), 1800)


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _input_initial(text: str, limit: int) -> str:
    return _truncate(text or " ", limit)


def _mrkdwn_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _code_text(text: str) -> str:
    return _mrkdwn_text(text).replace("```", "'''")
