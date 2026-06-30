from threading import Lock
from typing import Any
import json
import re
import unicodedata

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from mumemo_bot.config import BotConfig, PROJECT_ROOT, mask_secret
from mumemo_bot.git_sync import GitSyncError, GitSyncResult, commit_and_push_site_changes
from mumemo_bot.location import LocationInference, UNKNOWN_LOCATION, infer_location_detail
from mumemo_bot.site_store import (
    MemoNotFoundError,
    ProtectedMemoError,
    StoreResult,
    append_memo_with_post,
    delete_memo,
    download_images,
    find_title_conflict,
    get_memo,
    list_memos,
    overwrite_memo_with_post,
    save_post_as_memo,
    update_memo,
)
from mumemo_bot.slack_post import MumemoSlackPost, SlackImageFile
from mumemo_bot.slack_views import (
    APPROVE_MEMO_ACTION_ID,
    BODY_BLOCK_ID,
    OVERWRITE_EXISTING_MEMO_ACTION_ID,
    OVERWRITE_REVIEW_POST_ACTION_ID,
    PUBLISH_SEPARATE_MEMO_ACTION_ID,
    DELETE_MEMO_ACTION_ID,
    DISMISS_REVIEW_ACTION_ID,
    EDIT_MEMO_ACTION_ID,
    EDIT_REVIEW_URLS_ACTION_ID,
    IMAGE_BLOCK_ID,
    LOCATION_BLOCK_ID,
    IMAGES_BLOCK_ID,
    MEMO_EDIT_CALLBACK_ID,
    MEMO_REVIEW_URLS_CALLBACK_ID,
    RELOAD_REVIEW_ACTION_ID,
    SELECT_REVIEW_THUMBNAIL_ACTION_ID,
    TITLE_BLOCK_ID,
    UPLOAD_IMAGES_BLOCK_ID,
    URLS_BLOCK_ID,
    decode_action_value,
    decode_thumbnail_select_value,
    edit_modal_view,
    manage_blocks,
    modal_file_values,
    modal_value,
    review_blocks,
    review_urls_modal_view,
)


ALLOWED_TOP_LEVEL_SUBTYPES = {None, "file_share"}
MANAGE_COMMAND = "mumemo"
MANAGE_LIST_LIMIT = 15


def create_app(config: BotConfig) -> App:
    app = App(token=config.slack_bot_token)
    state_lock = Lock()
    seen_event_ids: set[str] = set()
    accepted_post_keys: set[tuple[str, str]] = set()
    handled_review_message_keys: set[tuple[str, str]] = set()
    review_posts: dict[tuple[str, str], MumemoSlackPost] = {}
    review_locations: dict[tuple[str, str], LocationInference] = {}

    def claim_event(event_id: str) -> bool:
        if not event_id:
            return True
        with state_lock:
            if event_id in seen_event_ids:
                return False
            seen_event_ids.add(event_id)
            return True

    def claim_post(key: tuple[str, str]) -> bool:
        with state_lock:
            if key in accepted_post_keys:
                return False
            accepted_post_keys.add(key)
            return True

    def release_post(key: tuple[str, str]) -> None:
        with state_lock:
            accepted_post_keys.discard(key)

    def claim_review_message(key: tuple[str, str]) -> bool:
        with state_lock:
            if key in handled_review_message_keys:
                return False
            handled_review_message_keys.add(key)
            return True

    def remember_review_post(
        post: MumemoSlackPost,
        location_detail: LocationInference | None = None,
    ) -> None:
        key = (post.channel_id, post.message_ts)
        with state_lock:
            review_posts[key] = post
            if location_detail is not None:
                review_locations[key] = location_detail

    def get_review_post(channel_id: str, message_ts: str) -> MumemoSlackPost | None:
        with state_lock:
            return review_posts.get((channel_id, message_ts))

    def remember_review_location(
        post: MumemoSlackPost,
        location_detail: LocationInference,
    ) -> None:
        with state_lock:
            review_locations[(post.channel_id, post.message_ts)] = location_detail

    def get_review_location(channel_id: str, message_ts: str) -> LocationInference | None:
        with state_lock:
            return review_locations.get((channel_id, message_ts))

    def forget_review_post(channel_id: str, message_ts: str) -> None:
        with state_lock:
            review_posts.pop((channel_id, message_ts), None)
            review_locations.pop((channel_id, message_ts), None)

    def resolve_review_post(channel_id: str, message_ts: str, client: Any) -> MumemoSlackPost:
        post = get_review_post(channel_id, message_ts)
        if post is not None:
            return post
        message = _fetch_original_message(client, channel_id, message_ts)
        post = MumemoSlackPost.from_message(channel_id=channel_id, message=message)
        remember_review_post(post)
        return post

    def publish_review_post(
        *,
        client: Any,
        logger: Any,
        channel_id: str,
        message_ts: str,
        review_message_ts: str,
        user_id: str,
        mode: str,
        memo_id: str | None = None,
    ) -> None:
        key = (channel_id, message_ts)
        review_key = (channel_id, review_message_ts)
        if not claim_review_message(review_key):
            print(f"[slack:action] duplicate review action ignored: {review_key}", flush=True)
            return

        post: MumemoSlackPost | None = None
        location_detail: LocationInference | None = None
        claimed = False
        try:
            post = resolve_review_post(channel_id, message_ts, client)
            location_detail = get_review_location(channel_id, message_ts)
            if location_detail is None:
                location_detail = _infer_post_location(config, post)
                remember_review_location(post, location_detail)
            print(
                "[slack:publish] resolved review post: "
                f"mode={mode}, title={post.title!r}, images={len(post.images)}, "
                f"urls={len(post.urls)}, {_location_debug_text(location_detail)}",
                flush=True,
            )
            target_memo_id = memo_id
            if mode in {"append_existing", "overwrite_post", "overwrite_existing"} and not target_memo_id:
                conflict = find_title_conflict(config, post)
                if conflict is None:
                    raise ValueError("上書き先の既存投稿が見つかりません")
                target_memo_id = conflict.id

            _update_review_status(
                client=client,
                channel_id=channel_id,
                review_message_ts=review_message_ts,
                post=post,
                status_text="保存中です...",
                location_detail=location_detail,
            )

            if not claim_post(key):
                _update_review_status(
                    client=client,
                    channel_id=channel_id,
                    review_message_ts=review_message_ts,
                    post=post,
                    status_text="この投稿はすでに処理中、または保存済みです。",
                    location_detail=location_detail,
                )
                return
            claimed = True

            if mode == "append_existing":
                result = append_memo_with_post(
                    config,
                    memo_id=str(target_memo_id),
                    post=post,
                    location=location_detail.location,
                )
                status = _publish_status(
                    f"既存投稿に追記しました。追加画像: {result.image_count}件",
                    result,
                    include_image_count=False,
                )
            elif mode in {"overwrite_post", "overwrite_existing"}:
                result = overwrite_memo_with_post(
                    config,
                    memo_id=str(target_memo_id),
                    post=post,
                    preserve_existing_identity=True,
                    location=location_detail.location,
                )
                status = _publish_status("上書き投稿しました。", result)
            else:
                result = save_post_as_memo(config, post, location=location_detail.location)
                status = _publish_status(
                    "別で投稿しました。" if mode == "separate" else "公開しました。" if result.created else "このSlack投稿はすでにMumemoへ保存済みです。",
                    result,
                    include_image_count=result.created,
                )
        except Exception as error:
            if claimed:
                release_post(key)
            logger.exception("Failed to publish Slack post as Mumemo memo")
            print(f"[mumemo] publish failed: {error}", flush=True)
            if post is not None:
                _update_review_status(
                    client=client,
                    channel_id=channel_id,
                    review_message_ts=review_message_ts,
                    post=post,
                    status_text=_short_status(f"保存に失敗しました: {error}"),
                    location_detail=location_detail or _location_error_detail(post, error),
                )
            else:
                _clear_review_buttons(
                    client=client,
                    channel_id=channel_id,
                    review_message_ts=review_message_ts,
                    status_text=_short_status(f"保存に失敗しました: {error}"),
                )
            _reply(
                client=client,
                channel_id=channel_id,
                thread_ts=message_ts,
                text=_short_status(f"Mumemoへの保存に失敗しました: {error}"),
            )
            return

        print(
            "[slack:publish] stored memo: "
            f"mode={mode}, created={result.created}, title={result.title!r}, "
            f"memo_id={result.memo_id!r}, page_url={result.page_url!r}, "
            f"location={result.location!r}, images={result.image_count}",
            flush=True,
        )

        git_status = _sync_git_after_publish(mode=mode, result=result, logger=logger)
        if git_status:
            status = _append_status(status, git_status)

        _update_review_status(
            client=client,
            channel_id=channel_id,
            review_message_ts=review_message_ts,
            post=post,
            status_text=status,
            location_detail=location_detail,
        )
        forget_review_post(channel_id, message_ts)
        reply_text = _publish_reply_text(result)
        if git_status:
            reply_text = _append_status(reply_text, git_status)
        _reply(
            client=client,
            channel_id=channel_id,
            thread_ts=message_ts,
            text=reply_text,
        )

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

        command_text = _manage_command_text(event)
        if command_text is not None:
            print(f"[slack:manage] command received: {command_text!r}", flush=True)
            _post_manage_response(
                client=client,
                config=config,
                channel_id=config.slack_channel_id,
                thread_ts=str(event.get("ts") or ""),
                user_id=str(event.get("user") or ""),
                command_text=command_text,
                ephemeral=False,
            )
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

        try:
            location_detail = _infer_post_location(config, post)
        except Exception as error:
            logger.exception("Failed to infer Mumemo location")
            print(f"[slack:event] location inference failed: {error}", flush=True)
            _reply(
                client=client,
                channel_id=config.slack_channel_id,
                thread_ts=post.message_ts,
                text=_short_status(f"Mumemoの場所推定に失敗しました: {error}"),
            )
            return
        print(
            "[slack:event] accepted for review: "
            f"title={post.title!r}, body_chars={len(post.body)}, "
            f"images={len(post.images)}, urls={len(post.urls)}, "
            f"{_location_debug_text(location_detail)}",
            flush=True,
        )
        remember_review_post(post, location_detail)
        _post_review_for_post(
            client=client,
            config=config,
            channel_id=config.slack_channel_id,
            post=post,
            location_detail=location_detail,
        )

    @app.command("/mumemo")
    def handle_slash_command(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        channel_id = str(body.get("channel_id") or "")
        user_id = str(body.get("user_id") or "")
        command_text = str(body.get("text") or "").strip()
        print(
            f"[slack:manage] slash command channel={channel_id!r}, text={command_text!r}",
            flush=True,
        )
        if channel_id != config.slack_channel_id:
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=f"Mumemoの整理は {config.slack_channel_label} で使ってください。",
            )
            return

        _post_manage_response(
            client=client,
            config=config,
            channel_id=channel_id,
            thread_ts=None,
            user_id=user_id,
            command_text=command_text,
            ephemeral=True,
        )

    @app.action(APPROVE_MEMO_ACTION_ID)
    def handle_approve_memo(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "unknown")
        print(
            "[slack:action] approve clicked: "
            f"user={user_id}, channel={channel_id}, message_ts={message_ts}, "
            f"review_ts={review_message_ts}",
            flush=True,
        )
        publish_review_post(
            client=client,
            logger=logger,
            channel_id=channel_id,
            message_ts=message_ts,
            review_message_ts=review_message_ts,
            user_id=user_id,
            mode="approve",
        )

    @app.action(PUBLISH_SEPARATE_MEMO_ACTION_ID)
    def handle_publish_separate_memo(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "unknown")
        print(
            "[slack:action] publish separate clicked: "
            f"user={user_id}, channel={channel_id}, message_ts={message_ts}, "
            f"review_ts={review_message_ts}",
            flush=True,
        )
        publish_review_post(
            client=client,
            logger=logger,
            channel_id=channel_id,
            message_ts=message_ts,
            review_message_ts=review_message_ts,
            user_id=user_id,
            mode="separate",
        )

    @app.action(OVERWRITE_REVIEW_POST_ACTION_ID)
    def handle_overwrite_review_post(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        memo_id = str(value.get("memo_id") or "")
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "unknown")
        print(
            "[slack:action] overwrite memo clicked: "
            f"user={user_id}, channel={channel_id}, message_ts={message_ts}, "
            f"memo_id={memo_id}, review_ts={review_message_ts}",
            flush=True,
        )
        publish_review_post(
            client=client,
            logger=logger,
            channel_id=channel_id,
            message_ts=message_ts,
            review_message_ts=review_message_ts,
            user_id=user_id,
            mode="overwrite_existing",
            memo_id=memo_id,
        )

    @app.action(OVERWRITE_EXISTING_MEMO_ACTION_ID)
    def handle_overwrite_existing_memo(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        memo_id = str(value.get("memo_id") or "")
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "unknown")
        print(
            "[slack:action] append existing memo clicked: "
            f"user={user_id}, channel={channel_id}, message_ts={message_ts}, "
            f"memo_id={memo_id}, review_ts={review_message_ts}",
            flush=True,
        )
        publish_review_post(
            client=client,
            logger=logger,
            channel_id=channel_id,
            message_ts=message_ts,
            review_message_ts=review_message_ts,
            user_id=user_id,
            mode="append_existing",
            memo_id=memo_id,
        )

    @app.action(EDIT_REVIEW_URLS_ACTION_ID)
    def handle_edit_review_urls(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "")

        try:
            post = resolve_review_post(channel_id, message_ts, client)
            if not post.urls:
                _post_ephemeral(
                    client=client,
                    channel_id=channel_id,
                    user_id=user_id,
                    text="この下書きにはURLがありません。",
                )
                return
            client.views_open(
                trigger_id=body["trigger_id"],
                view=review_urls_modal_view(
                    post=post,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    review_message_ts=review_message_ts,
                ),
            )
        except Exception as error:
            logger.exception("Failed to open Mumemo URL edit modal")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=_short_status(f"URL修正画面を開けませんでした: {error}"),
            )

    @app.view(MEMO_REVIEW_URLS_CALLBACK_ID)
    def handle_review_urls_submission(
        ack: Any,
        body: dict[str, Any],
        view: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        metadata = json.loads(str(view.get("private_metadata") or "{}"))
        channel_id = str(metadata.get("channel_id") or config.slack_channel_id)
        message_ts = str(metadata.get("message_ts") or "")
        review_message_ts = str(metadata.get("review_message_ts") or "")
        urls = [line.strip() for line in modal_value(view, URLS_BLOCK_ID).splitlines() if line.strip()]
        post = get_review_post(channel_id, message_ts)
        if post is None:
            ack(response_action="errors", errors={URLS_BLOCK_ID: "下書きを再読み込みしてください"})
            return

        try:
            updated_post = post.with_urls(urls)
        except ValueError as error:
            ack(response_action="errors", errors={URLS_BLOCK_ID: str(error)})
            return

        ack()
        try:
            location_detail = get_review_location(channel_id, message_ts)
            if location_detail is None:
                location_detail = _infer_post_location(config, updated_post)
            remember_review_post(updated_post, location_detail)
            _update_review_status(
                client=client,
                channel_id=channel_id,
                review_message_ts=review_message_ts,
                post=updated_post,
                status_text="URLを反映しました。承認前に確認してください。",
                buttons_enabled=True,
                title_conflict=find_title_conflict(config, updated_post),
                location_detail=location_detail,
            )
        except Exception as error:
            logger.exception("Failed to update Mumemo URL review")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=str(body.get("user", {}).get("id") or ""),
                text=_short_status(f"URL修正の反映に失敗しました: {error}"),
            )

    @app.action(SELECT_REVIEW_THUMBNAIL_ACTION_ID)
    def handle_select_review_thumbnail(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        selected_option = action.get("selected_option") or {}
        channel_id = str(body.get("channel", {}).get("id") or config.slack_channel_id)
        review_message_ts = str(
            body.get("message", {}).get("ts")
            or body.get("container", {}).get("message_ts")
            or ""
        )
        user_id = str(body.get("user", {}).get("id") or "")

        try:
            message_ts, file_id = decode_thumbnail_select_value(
                str(selected_option.get("value") or "")
            )
            post = resolve_review_post(channel_id, message_ts, client)
            updated_post = post.with_thumbnail_image(file_id)
            location_detail = get_review_location(channel_id, message_ts)
            if location_detail is None:
                location_detail = _infer_post_location(config, updated_post)
            remember_review_post(updated_post, location_detail)
            selected_name = updated_post.images[0].name if updated_post.images else ""
            _update_review_status(
                client=client,
                channel_id=channel_id,
                review_message_ts=review_message_ts,
                post=updated_post,
                status_text=f"サムネイルを変更しました: {selected_name}",
                buttons_enabled=True,
                title_conflict=find_title_conflict(config, updated_post),
                location_detail=location_detail,
            )
        except Exception as error:
            logger.exception("Failed to update Mumemo thumbnail review")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=_short_status(f"サムネイル変更に失敗しました: {error}"),
            )

    @app.action(RELOAD_REVIEW_ACTION_ID)
    def handle_reload_review(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        review_key = (channel_id, review_message_ts)

        print(
            "[slack:action] reload clicked: "
            f"channel={channel_id}, message_ts={message_ts}, review_ts={review_message_ts}",
            flush=True,
        )

        if not claim_review_message(review_key):
            print(f"[slack:action] duplicate review action ignored: {review_key}", flush=True)
            return

        post: MumemoSlackPost | None = None
        location_detail: LocationInference | None = None
        try:
            message = _fetch_original_message(client, channel_id, message_ts)
            post = MumemoSlackPost.from_message(channel_id=channel_id, message=message)
            location_detail = _infer_post_location(config, post)
            remember_review_post(post, location_detail)
            _post_review_for_post(
                client=client,
                config=config,
                channel_id=channel_id,
                post=post,
                location_detail=location_detail,
            )
            _update_review_status(
                client=client,
                channel_id=channel_id,
                review_message_ts=review_message_ts,
                post=post,
                status_text="再読み込みしました。新しい下書きを使ってください。",
                location_detail=location_detail,
            )
        except Exception as error:
            logger.exception("Failed to reload Slack post for Mumemo review")
            print(f"[slack:action] reload failed: {error}", flush=True)
            if post is not None:
                _update_review_status(
                    client=client,
                    channel_id=channel_id,
                    review_message_ts=review_message_ts,
                    post=post,
                    status_text=_short_status(f"再読み込みに失敗しました: {error}"),
                    location_detail=location_detail or _location_error_detail(post, error),
                )
            else:
                _clear_review_buttons(
                    client=client,
                    channel_id=channel_id,
                    review_message_ts=review_message_ts,
                    status_text=_short_status(f"再読み込みに失敗しました: {error}"),
                )

    @app.action(DISMISS_REVIEW_ACTION_ID)
    def handle_dismiss_review(
        ack: Any,
        body: dict[str, Any],
        client: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        channel_id = str(value["channel_id"])
        message_ts = str(value["message_ts"])
        review_message_ts = str(body.get("message", {}).get("ts") or "")
        review_key = (channel_id, review_message_ts)
        if not claim_review_message(review_key):
            return
        forget_review_post(channel_id, message_ts)
        _clear_review_buttons(
            client=client,
            channel_id=channel_id,
            review_message_ts=review_message_ts,
            status_text="Mumemo下書きを破棄しました。",
        )

    @app.action(EDIT_MEMO_ACTION_ID)
    def handle_edit_memo(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        memo_id = str(value["memo_id"])
        channel_id = str(body.get("channel", {}).get("id") or config.slack_channel_id)
        message_ts = str(body.get("message", {}).get("ts") or "") or None

        try:
            memo = get_memo(config, memo_id)
            client.views_open(
                trigger_id=body["trigger_id"],
                view=edit_modal_view(
                    memo=memo,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    site_base_url=config.site_base_url,
                ),
            )
        except Exception as error:
            logger.exception("Failed to open Mumemo edit modal")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=str(body.get("user", {}).get("id") or ""),
                text=_short_status(f"編集画面を開けませんでした: {error}"),
            )

    @app.action(DELETE_MEMO_ACTION_ID)
    def handle_delete_memo(
        ack: Any,
        body: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        ack()
        action = body["actions"][0]
        value = decode_action_value(action)
        memo_id = str(value["memo_id"])
        channel_id = str(body.get("channel", {}).get("id") or config.slack_channel_id)
        message_ts = str(body.get("message", {}).get("ts") or "")
        user_id = str(body.get("user", {}).get("id") or "")

        try:
            result = delete_memo(config, memo_id=memo_id)
            git_status = _sync_git_after_change(
                action="delete",
                title=result.title,
                logger=logger,
            )
            confirmation_text = _append_status(f"削除しました: {result.title}", git_status)
            _refresh_manage_message(
                client=client,
                config=config,
                channel_id=channel_id,
                message_ts=message_ts,
                fallback_user_id=user_id,
                fallback_text=confirmation_text,
            )
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=confirmation_text,
            )
        except (MemoNotFoundError, ProtectedMemoError, ValueError) as error:
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=str(error),
            )
        except Exception as error:
            logger.exception("Failed to delete Mumemo memo")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=_short_status(f"削除に失敗しました: {error}"),
            )

    @app.view(MEMO_EDIT_CALLBACK_ID)
    def handle_edit_modal_submission(
        ack: Any,
        body: dict[str, Any],
        view: dict[str, Any],
        client: Any,
        logger: Any,
    ) -> None:
        title = modal_value(view, TITLE_BLOCK_ID).strip()
        if not title:
            ack(response_action="errors", errors={TITLE_BLOCK_ID: "タイトルを入力してください"})
            return
        ack()

        metadata = json.loads(str(view.get("private_metadata") or "{}"))
        memo_id = str(metadata.get("memo_id") or "")
        channel_id = str(metadata.get("channel_id") or config.slack_channel_id)
        message_ts = metadata.get("message_ts")
        user_id = str(body.get("user", {}).get("id") or "")
        body_text = modal_value(view, BODY_BLOCK_ID)
        location = modal_value(view, LOCATION_BLOCK_ID).strip()
        primary_image_ref = modal_value(view, IMAGE_BLOCK_ID).strip()
        image_order_lines = [line.strip() for line in modal_value(view, IMAGES_BLOCK_ID).splitlines()]

        try:
            current_memo = get_memo(config, memo_id)
            images = _images_from_order_lines(
                image_order_lines,
                current_memo.images,
                config.site_base_url,
            )
            image = (
                _image_ref_from_modal_line(
                    primary_image_ref,
                    current_memo.images,
                    config.site_base_url,
                )
                if primary_image_ref
                else ""
            )
            if image and image not in images:
                image = ""

            uploaded_files = _uploaded_image_files_from_modal(
                client,
                modal_file_values(view, UPLOAD_IMAGES_BLOCK_ID),
            )
            if uploaded_files:
                saved_images = download_images(
                    bot_token=config.slack_bot_token,
                    post=MumemoSlackPost(
                        channel_id=channel_id,
                        message_ts=str(message_ts or "edit"),
                        user_id=user_id or "unknown",
                        title=title,
                        body=body_text,
                        images=uploaded_files,
                    ),
                    asset_dir=config.asset_dir,
                    asset_url_prefix=config.asset_url_prefix,
                    original_asset_dir=config.original_asset_dir,
                    github_repo_url=config.github_repo_url,
                    github_branch=config.github_branch,
                )
                images = _append_unique(images, [saved_image.url for saved_image in saved_images])
                new_original_images_by_image = {
                    saved_image.url: saved_image.original_url
                    for saved_image in saved_images
                    if saved_image.original_url
                }
            else:
                new_original_images_by_image = {}

            result = update_memo(
                config,
                memo_id=memo_id,
                title=title,
                body=body_text,
                image=image,
                images=images,
                new_original_images_by_image=new_original_images_by_image,
                location=location,
            )
            git_status = _sync_git_after_change(
                action="update",
                title=result.title,
                logger=logger,
            )
            confirmation_text = _append_status(f"\u66f4\u65b0\u3057\u307e\u3057\u305f: {result.title}", git_status)
            if isinstance(message_ts, str) and message_ts:
                _refresh_manage_message(
                    client=client,
                    config=config,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    fallback_user_id=user_id,
                    fallback_text=confirmation_text,
                )
            else:
                _post_ephemeral(
                    client=client,
                    channel_id=channel_id,
                    user_id=user_id,
                    text=confirmation_text,
                )
        except Exception as error:
            logger.exception("Failed to update Mumemo memo")
            _post_ephemeral(
                client=client,
                channel_id=channel_id,
                user_id=user_id,
                text=_short_status(f"更新に失敗しました: {error}"),
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


def _post_review_for_post(
    client: Any,
    config: BotConfig,
    channel_id: str,
    post: MumemoSlackPost,
    location_detail: LocationInference | None = None,
) -> None:
    if location_detail is None:
        location_detail = _infer_post_location(config, post)
    title_conflict = find_title_conflict(config, post)
    print(
        "[slack:review] preparing review message: "
        f"thread_ts={post.message_ts}, title={post.title!r}, "
        f"conflict={getattr(title_conflict, 'id', None)!r}, "
        f"{_location_debug_text(location_detail)}",
        flush=True,
    )
    response = client.chat_postMessage(
        channel=channel_id,
        thread_ts=post.message_ts,
        text=f"Mumemo下書き: {post.title}",
        blocks=review_blocks(
            channel_id=channel_id,
            message_ts=post.message_ts,
            title=post.title,
            body=post.body,
            image_count=len(post.images),
            location=location_detail.location,
            urls=post.urls,
            title_conflict=title_conflict,
            status_text=None,
            buttons_enabled=True,
            images=post.images,
        ),
    )
    print(
        "[slack:review] posted review buttons: "
        f"thread_ts={post.message_ts}, review_ts={response.get('ts')}, "
        f"{_location_debug_text(location_detail)}",
        flush=True,
    )


def _update_review_status(
    *,
    client: Any,
    channel_id: str,
    review_message_ts: str,
    post: MumemoSlackPost,
    status_text: str,
    location_detail: LocationInference,
    buttons_enabled: bool = False,
    title_conflict: Any | None = None,
) -> None:
    print(
        "[slack:review] updating review status: "
        f"thread_ts={post.message_ts}, review_ts={review_message_ts}, "
        f"buttons_enabled={buttons_enabled}, {_location_debug_text(location_detail)}, "
        f"status={_short_status(status_text)!r}",
        flush=True,
    )
    client.chat_update(
        channel=channel_id,
        ts=review_message_ts,
        text=f"Mumemo下書き: {post.title} - {status_text}",
        blocks=review_blocks(
            channel_id=channel_id,
            message_ts=post.message_ts,
            title=post.title,
            body=post.body,
            image_count=len(post.images),
            location=location_detail.location,
            urls=post.urls,
            title_conflict=title_conflict,
            status_text=_short_status(status_text),
            buttons_enabled=buttons_enabled,
            images=post.images,
        ),
    )


def _clear_review_buttons(
    *,
    client: Any,
    channel_id: str,
    review_message_ts: str,
    status_text: str,
) -> None:
    client.chat_update(
        channel=channel_id,
        ts=review_message_ts,
        text=_short_status(status_text),
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _short_status(status_text)},
            }
        ],
    )


def _sync_git_after_publish(*, mode: str, result: StoreResult, logger: Any) -> str:
    should_sync = result.created or mode in {
        "append_existing",
        "overwrite_post",
        "overwrite_existing",
        "separate",
    }
    if not should_sync:
        return ""
    return _sync_git_after_change(action="add", title=result.title, logger=logger)


def _sync_git_after_change(*, action: str, title: str, logger: Any) -> str:
    try:
        git_result = commit_and_push_site_changes(action, title)
    except GitSyncError as error:
        logger.exception("Failed to commit and push Mumemo site changes")
        return _short_status(f"Git commit/push に失敗しました: {error}")
    return _git_sync_status(git_result)


def _git_sync_status(result: GitSyncResult) -> str:
    if result.committed:
        commit_hash = result.commit_hash or "unknown"
        return f"Git: `{result.commit_message}` ({commit_hash}) をcommitし、origin/mainへpushしました。"
    return f"Git: `{result.commit_message}` のコミット対象差分はありませんでした。"


def _append_status(text: str, extra: str) -> str:
    if not extra:
        return text
    if not text:
        return extra
    return f"{text}\n{extra}"

def _publish_status(
    message: str,
    result: StoreResult,
    *,
    include_image_count: bool = True,
) -> str:
    lines = [message]
    if include_image_count:
        lines.append(f"画像: {result.image_count}件")
    if result.page_url:
        lines.append(f"URL: {result.page_url}")
    return "\n".join(lines)


def _publish_reply_text(result: StoreResult) -> str:
    lines = [f"Mumemoに反映しました: {result.title}", f"画像: {result.image_count}件"]
    if result.page_url:
        lines.append(f"URL: {result.page_url}")
    return "\n".join(lines)

def _post_manage_response(
    *,
    client: Any,
    config: BotConfig,
    channel_id: str,
    thread_ts: str | None,
    user_id: str,
    command_text: str,
    ephemeral: bool,
) -> None:
    command = command_text.strip()
    normalized_command = _normalized_manage_command(command)

    if _is_manage_help_command(normalized_command):
        text = _manage_help_text()
        if ephemeral:
            _post_ephemeral(client=client, channel_id=channel_id, user_id=user_id, text=text)
        else:
            _reply(client=client, channel_id=channel_id, thread_ts=thread_ts or "", text=text)
        return

    items = list_memos(config, include_fixed=True)
    query = "" if _is_manage_list_command(normalized_command) else _manage_search_query(command)
    if query:
        matched_items = _filter_memos_by_title(items, query)
        shown = matched_items[:MANAGE_LIST_LIMIT]
        blocks = manage_blocks(
            items=shown,
            total_count=len(matched_items),
            shown_count=len(shown),
            title=f"Mumemo 投稿検索: {query}",
            description=f"タイトルに一致する投稿を {len(shown)}/{len(matched_items)} 件表示しています。",
            empty_text=f"タイトルに「{query}」を含む投稿は見つかりませんでした。",
        )
        text = f"Mumemo 投稿検索: {query} ({len(shown)}/{len(matched_items)}件)"
    else:
        shown = items[:MANAGE_LIST_LIMIT]
        blocks = manage_blocks(items=shown, total_count=len(items), shown_count=len(shown))
        text = f"Mumemo 投稿整理: {len(shown)}/{len(items)}件"

    if ephemeral:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=text,
            blocks=blocks,
        )
    else:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
            blocks=blocks,
        )


def _normalized_manage_command(command_text: str) -> str:
    return unicodedata.normalize("NFKC", command_text).strip().casefold()


def _is_manage_help_command(command: str) -> bool:
    return command in {"help", "h", "?", "ヘルプ", "使い方"}


def _is_manage_list_command(command: str) -> bool:
    return command in {"", "list", "ls", "一覧", "整理", "manage"}


def _manage_search_query(command_text: str) -> str:
    query = unicodedata.normalize("NFKC", command_text).strip()
    lowered = query.casefold()
    for prefix in ("edit ", "search ", "find ", "編集 ", "検索 "):
        if lowered.startswith(prefix.casefold()):
            return query[len(prefix) :].strip()
    return query


def _filter_memos_by_title(items: list[Any], query: str) -> list[Any]:
    tokens = [token for token in _normalized_search_text(query).split(" ") if token]
    if not tokens:
        return items
    return [
        item
        for item in items
        if all(token in _normalized_search_text(str(item.title)) for token in tokens)
    ]


def _normalized_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _manage_help_text() -> str:
    return "\n".join(
        [
            "*Mumemo コマンド*",
            "`mumemo` / `mumemo list` / `/mumemo` : 投稿一覧を表示します。",
            "`mumemo <タイトル>` : タイトル名で投稿を検索し、編集・削除ボタンを表示します。",
            "`mumemo edit <タイトル>` / `mumemo 検索 <タイトル>` : 同じくタイトル検索します。",
            "`mumemo help` / `/mumemo help` : このヘルプを表示します。",
            "",
            "編集ボタンから、タイトル・本文・サムネイル・画像順序・画像追加を変更できます。保存後はサイトを生成し、Git commit/push します。",
        ]
    )


def _refresh_manage_message(
    *,
    client: Any,
    config: BotConfig,
    channel_id: str,
    message_ts: str,
    fallback_user_id: str,
    fallback_text: str,
) -> None:
    items = list_memos(config, include_fixed=True)
    shown = items[:MANAGE_LIST_LIMIT]
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=f"Mumemo 投稿整理: {len(shown)}/{len(items)}件",
            blocks=manage_blocks(items=shown, total_count=len(items), shown_count=len(shown)),
        )
    except Exception as error:
        print(f"[slack:manage] failed to refresh list message: {error}", flush=True)
        _post_ephemeral(
            client=client,
            channel_id=channel_id,
            user_id=fallback_user_id,
            text=fallback_text,
        )


def _fetch_original_message(client: Any, channel_id: str, message_ts: str) -> dict[str, Any]:
    response = client.conversations_replies(
        channel=channel_id,
        ts=message_ts,
        limit=1,
        inclusive=True,
    )
    messages = response.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("Slack投稿が見つかりません")
    message = messages[0]
    if not isinstance(message, dict):
        raise RuntimeError("Slack投稿の形式が不正です")
    return message


def _uploaded_image_files_from_modal(
    client: Any,
    file_values: list[Any],
) -> list[SlackImageFile]:
    images: list[SlackImageFile] = []
    for file_value in file_values:
        file_data = _resolve_modal_file(client, file_value)
        if file_data is None:
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


def _resolve_modal_file(client: Any, file_value: Any) -> dict[str, Any] | None:
    if isinstance(file_value, str):
        return _fetch_slack_file(client, file_value)
    if not isinstance(file_value, dict):
        return None
    if file_value.get("url_private_download") or file_value.get("url_private"):
        return file_value
    file_id = str(file_value.get("id") or "")
    return _fetch_slack_file(client, file_id) if file_id else None


def _fetch_slack_file(client: Any, file_id: str) -> dict[str, Any] | None:
    response = client.files_info(file=file_id)
    file_data = response.get("file")
    return file_data if isinstance(file_data, dict) else None


_FULL_WIDTH_DIGITS = str.maketrans("\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19", "0123456789")


def _images_from_order_lines(
    lines: list[str],
    current_images: list[str],
    site_base_url: str,
) -> list[str]:
    ordered_images: list[str] = []
    for line in lines:
        image_ref = _image_ref_from_modal_line(line, current_images, site_base_url)
        if image_ref:
            ordered_images.append(image_ref)
    return _append_unique([], ordered_images)


def _image_ref_from_modal_line(
    line: str,
    current_images: list[str],
    site_base_url: str,
) -> str:
    clean_line = _clean_modal_image_reference(line)
    if not clean_line:
        return ""

    normalized_line = clean_line.translate(_FULL_WIDTH_DIGITS)
    if not any(marker in normalized_line for marker in ("/", ".", ":")):
        match = re.fullmatch(r"\D*([0-9]+)\D*", normalized_line)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(current_images):
                return current_images[index]
            raise ValueError(f"Image number out of range: {clean_line}")

    return _local_image_ref_from_public_url(clean_line, site_base_url)


def _clean_modal_image_reference(value: str) -> str:
    clean_value = value.strip()
    slack_link_match = re.fullmatch(r"<([^>|]+)(?:\|[^>]*)?>", clean_value)
    if slack_link_match:
        return slack_link_match.group(1).strip()
    return clean_value


def _local_image_ref_from_public_url(value: str, site_base_url: str) -> str:
    clean_value = value.strip()
    base_url = str(site_base_url or "").strip().rstrip("/")
    if base_url and clean_value.startswith(f"{base_url}/"):
        clean_value = clean_value[len(base_url) :]
    return clean_value



def _append_unique(values: list[str], additions: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in [*values, *additions]:
        clean_value = value.strip()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        output.append(clean_value)
    return output


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


def _manage_command_text(event: dict[str, Any]) -> str | None:
    text = str(event.get("text") or "").strip()
    if not text:
        return None
    lowered = text.casefold()
    if lowered == MANAGE_COMMAND:
        return ""
    prefix = f"{MANAGE_COMMAND} "
    if lowered.startswith(prefix):
        return text[len(prefix) :].strip()
    return None


def _infer_post_location(config: BotConfig, post: MumemoSlackPost) -> LocationInference:
    return infer_location_detail(
        post.title,
        post.body,
        nominatim_user_agent=config.nominatim_user_agent,
        nominatim_email=config.nominatim_email,
        nominatim_endpoint=config.nominatim_endpoint,
        timeout_seconds=config.nominatim_timeout_seconds,
    )


def _location_error_detail(post: MumemoSlackPost, error: Exception) -> LocationInference:
    return LocationInference(
        location=UNKNOWN_LOCATION,
        source="nominatim_error",
        matched=f"{type(error).__name__}: {error}",
        query=post.title,
    )


def _location_debug_text(location_detail: LocationInference) -> str:
    return (
        f"location={location_detail.location!r}, "
        f"location_source={location_detail.source!r}, "
        f"location_matched={location_detail.matched!r}, "
        f"location_query={location_detail.query!r}"
    )


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


def _post_ephemeral(client: Any, channel_id: str, user_id: str, text: str) -> None:
    if not user_id:
        print(f"[slack:ephemeral] skipped without user: {text}", flush=True)
        return
    try:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
    except Exception as error:
        print(f"[slack:ephemeral] failed: {error}", flush=True)


def _print_startup_diagnostics(config: BotConfig) -> None:
    print(f"[config] PROJECT_ROOT={PROJECT_ROOT}", flush=True)
    print(f"[config] .env exists={(PROJECT_ROOT / '.env').exists()}", flush=True)
    print(f"[config] SLACK_CHANNEL_ID={config.slack_channel_id}", flush=True)
    print(f"[config] SLACK_CHANNEL_NAME={config.slack_channel_name}", flush=True)
    print(f"[config] SLACK_BOT_TOKEN={mask_secret(config.slack_bot_token)}", flush=True)
    print(f"[config] SLACK_APP_TOKEN={mask_secret(config.slack_app_token)}", flush=True)
    print(f"[config] MUMEMO_DATA_PATH={config.data_path}", flush=True)
    print(f"[config] MUMEMO_POST_ASSET_DIR={config.asset_dir}", flush=True)
    print(f"[config] MUMEMO_POST_ASSET_URL_PREFIX={config.asset_url_prefix}", flush=True)
    print(f"[config] MUMEMO_ORIGINAL_ASSET_DIR={config.original_asset_dir}", flush=True)
    print(f"[config] MUMEMO_ROUTE_BUILD_COMMAND={config.route_build_command}", flush=True)
    print(f"[config] MUMEMO_NOMINATIM_ENDPOINT={config.nominatim_endpoint}", flush=True)
    print(f"[config] MUMEMO_NOMINATIM_USER_AGENT={config.nominatim_user_agent}", flush=True)
    print(f"[config] MUMEMO_NOMINATIM_EMAIL={config.nominatim_email}", flush=True)
    print(f"[config] MUMEMO_NOMINATIM_TIMEOUT_SECONDS={config.nominatim_timeout_seconds}", flush=True)


def _short_status(text: str) -> str:
    if len(text) <= 2500:
        return text
    return text[:2497] + "..."


if __name__ == "__main__":
    main()
