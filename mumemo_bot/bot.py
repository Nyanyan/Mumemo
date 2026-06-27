from threading import Lock
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from mumemo_bot.config import BotConfig, PROJECT_ROOT, mask_secret
from mumemo_bot.site_store import save_post_as_memo
from mumemo_bot.slack_post import MumemoSlackPost


ALLOWED_TOP_LEVEL_SUBTYPES = {None, "file_share"}


def create_app(config: BotConfig) -> App:
    app = App(token=config.slack_bot_token)
    state_lock = Lock()
    seen_event_ids: set[str] = set()

    def claim_event(event_id: str) -> bool:
        if not event_id:
            return True
        with state_lock:
            if event_id in seen_event_ids:
                return False
            seen_event_ids.add(event_id)
            return True

    @app.event("message")
    def handle_message_event(
        event: dict[str, Any],
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        print(_event_summary("received message event", event, body), flush=True)
        event_id = str(body.get("event_id") or "")
        if not claim_event(event_id):
            print(f"[slack:event] skipped duplicate event_id={event_id}", flush=True)
            return

        skip_reason = _message_skip_reason(event, config.slack_channel_id)
        if skip_reason:
            print(f"[slack:event] skipped: {skip_reason}", flush=True)
            return

        try:
            post = MumemoSlackPost.from_message(
                channel_id=config.slack_channel_id,
                message=event,
            )
        except ValueError as error:
            logger.info("Skipped Slack message: %s", error)
            print(f"[slack:event] skipped: {error}", flush=True)
            return

        print(
            "[slack:event] accepted: "
            f"title={post.title!r}, body_chars={len(post.body)}, "
            f"images={len(post.images)}",
            flush=True,
        )

        try:
            result = save_post_as_memo(config, post)
        except Exception as error:
            logger.exception("Failed to save Slack post as Mumemo memo")
            print(f"[mumemo] failed: {error}", flush=True)
            _reply(
                client=client,
                channel_id=config.slack_channel_id,
                thread_ts=post.message_ts,
                text=f"Mumemoへの保存に失敗しました: {_short_status(str(error))}",
            )
            return

        if result.created:
            text = (
                f"Mumemoに保存しました: {result.title}\n"
                f"画像: {result.image_count}件\n"
                "必要なら内容を確認して commit / push してください。"
            )
        else:
            text = f"このSlack投稿はすでにMumemoへ保存済みです: {result.title}"
        _reply(
            client=client,
            channel_id=config.slack_channel_id,
            thread_ts=post.message_ts,
            text=text,
        )

    return app


def main() -> None:
    config = BotConfig.from_env()
    _print_startup_diagnostics(config)
    app = create_app(config)
    print(
        f"Listening for Slack messages in {config.slack_channel_label}",
        flush=True,
    )
    print("[socket-mode] starting SocketModeHandler", flush=True)
    SocketModeHandler(app, config.slack_app_token).start()


def _message_skip_reason(event: dict[str, Any], target_channel_id: str) -> str | None:
    event_channel = event.get("channel")
    if event_channel != target_channel_id:
        return f"channel mismatch: event.channel={event_channel!r}, target={target_channel_id!r}"
    if event.get("bot_id"):
        return f"bot message: bot_id={event.get('bot_id')!r}"

    subtype = event.get("subtype")
    if subtype not in ALLOWED_TOP_LEVEL_SUBTYPES:
        return f"unsupported subtype: {subtype!r}"

    ts = event.get("ts")
    thread_ts = event.get("thread_ts")
    if thread_ts and thread_ts != ts:
        return f"thread reply: ts={ts!r}, thread_ts={thread_ts!r}"

    return None


def _event_summary(label: str, event: dict[str, Any], body: dict[str, Any]) -> str:
    text = str(event.get("text") or "")
    text_preview = text.replace("\n", " ")[:120]
    files = event.get("files")
    file_count = len(files) if isinstance(files, list) else 0
    return (
        f"[slack:event] {label}: "
        f"event_id={body.get('event_id')!r}, "
        f"type={event.get('type')!r}, subtype={event.get('subtype')!r}, "
        f"channel={event.get('channel')!r}, user={event.get('user')!r}, "
        f"bot_id={event.get('bot_id')!r}, ts={event.get('ts')!r}, "
        f"thread_ts={event.get('thread_ts')!r}, files={file_count}, "
        f"text={text_preview!r}"
    )


def _reply(client: Any, channel_id: str, thread_ts: str, text: str) -> None:
    try:
        client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=text)
    except Exception as error:
        print(f"[slack:reply] failed: {error}", flush=True)


def _print_startup_diagnostics(config: BotConfig) -> None:
    print(f"[config] PROJECT_ROOT={PROJECT_ROOT}", flush=True)
    print(f"[config] .env exists={(PROJECT_ROOT / '.env').exists()}", flush=True)
    print(f"[config] SLACK_CHANNEL_ID={config.slack_channel_id}", flush=True)
    print(f"[config] SLACK_CHANNEL_NAME={config.slack_channel_name}", flush=True)
    print(f"[config] SLACK_BOT_TOKEN={mask_secret(config.slack_bot_token)}", flush=True)
    print(f"[config] SLACK_APP_TOKEN={mask_secret(config.slack_app_token)}", flush=True)
    print(f"[config] MUMEMO_DATA_PATH={config.data_path}", flush=True)
    print(f"[config] MUMEMO_SLACK_ASSET_DIR={config.asset_dir}", flush=True)
    print(f"[config] MUMEMO_SLACK_ASSET_URL_PREFIX={config.asset_url_prefix}", flush=True)
    print(f"[config] MUMEMO_ROUTE_BUILD_COMMAND={config.route_build_command}", flush=True)


def _short_status(text: str) -> str:
    if len(text) <= 2500:
        return text
    return text[:2497] + "..."


if __name__ == "__main__":
    main()