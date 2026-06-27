"""Slack Block Kit views for Mumemo bot."""

from __future__ import annotations

from typing import Any
import json


APPROVE_MEMO_ACTION_ID = "mumemo_approve_post"
RELOAD_REVIEW_ACTION_ID = "mumemo_reload_review"
DISMISS_REVIEW_ACTION_ID = "mumemo_dismiss_review"
EDIT_MEMO_ACTION_ID = "mumemo_edit_memo"
DELETE_MEMO_ACTION_ID = "mumemo_delete_memo"
MEMO_EDIT_CALLBACK_ID = "mumemo_edit_modal"

TITLE_BLOCK_ID = "title"
BODY_BLOCK_ID = "body"
IMAGE_BLOCK_ID = "image"
IMAGES_BLOCK_ID = "images"
VALUE_ACTION_ID = "value"


def review_blocks(
    *,
    channel_id: str,
    message_ts: str,
    title: str,
    body: str,
    image_count: int,
    status_text: str | None,
    buttons_enabled: bool,
) -> list[dict[str, Any]]:
    body_preview = body.strip() or "(本文なし)"
    body_preview = _truncate(body_preview, 1800)

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
                ),
            },
        }
    ]

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
        value = json.dumps(
            {
                "channel_id": channel_id,
                "message_ts": message_ts,
            },
            ensure_ascii=False,
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "承認して公開"},
                        "style": "primary",
                        "action_id": APPROVE_MEMO_ACTION_ID,
                        "value": value,
                    },
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
                ],
            }
        )

    return blocks


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
        blocks.extend(
            [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*{_mrkdwn_text(item.title)}*\n"
                            f"{_mrkdwn_text(body_preview)}\n"
                            f"画像: {item.image_count}件"
                        ),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "編集"},
                            "action_id": EDIT_MEMO_ACTION_ID,
                            "value": value,
                        },
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
                                    "text": f"*{_mrkdwn_text(item.title)}* をMumemoの一覧から削除します。",
                                },
                                "confirm": {"type": "plain_text", "text": "削除"},
                                "deny": {"type": "plain_text", "text": "戻る"},
                            },
                        },
                    ],
                },
            ]
        )

    return blocks[:50]


def edit_modal_view(*, memo: Any, channel_id: str, message_ts: str | None) -> dict[str, Any]:
    metadata = json.dumps(
        {
            "memo_id": memo.id,
            "channel_id": channel_id,
            "message_ts": message_ts,
        },
        ensure_ascii=False,
    )
    images_text = "\n".join(memo.images)

    return {
        "type": "modal",
        "callback_id": MEMO_EDIT_CALLBACK_ID,
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": "Mumemo編集"},
        "submit": {"type": "plain_text", "text": "保存"},
        "close": {"type": "plain_text", "text": "閉じる"},
        "blocks": [
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
            {
                "type": "input",
                "block_id": IMAGE_BLOCK_ID,
                "label": {"type": "plain_text", "text": "サムネイル画像URL"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": VALUE_ACTION_ID,
                    "initial_value": _input_initial(memo.image, 300),
                },
            },
            {
                "type": "input",
                "block_id": IMAGES_BLOCK_ID,
                "optional": True,
                "label": {"type": "plain_text", "text": "詳細画像URL"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": VALUE_ACTION_ID,
                    "multiline": True,
                    "initial_value": _input_initial(images_text, 2900),
                },
            },
        ],
    }


def modal_value(view: dict[str, Any], block_id: str) -> str:
    values = view.get("state", {}).get("values", {})
    block = values.get(block_id, {})
    action = block.get(VALUE_ACTION_ID, {})
    return str(action.get("value") or "")


def decode_action_value(action: dict[str, Any]) -> dict[str, Any]:
    raw_value = str(action.get("value") or "{}")
    value = json.loads(raw_value)
    if not isinstance(value, dict):
        raise ValueError("Slack action value must be an object")
    return value


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
