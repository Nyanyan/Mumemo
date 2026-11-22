from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mumemo_bot import bot
from mumemo_bot.location import LocationInference
from mumemo_bot.site_store import StoreResult
from mumemo_bot.slack_views import (
    ADD_REVIEW_IMAGES_ACTION_ID,
    APPROVE_MEMO_ACTION_ID,
    DISMISS_REVIEW_ACTION_ID,
    MEMO_REVIEW_IMAGES_CALLBACK_ID,
    RELOAD_REVIEW_ACTION_ID,
    SELECT_REVIEW_THUMBNAIL_ACTION_ID,
    UPLOAD_IMAGES_ACTION_ID,
    UPLOAD_IMAGES_BLOCK_ID,
)


class ReviewApp:
    def __init__(self, *, token: str) -> None:
        self.handlers = {}

    def register(self, callback_id):
        def register_handler(handler):
            self.handlers[callback_id] = handler
            return handler

        return register_handler

    action = command = event = view = register


class SlackReviewImagesTests(unittest.TestCase):
    def setUp(self) -> None:
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        directory = Path(contexts.enter_context(TemporaryDirectory()))
        contexts.enter_context(redirect_stdout(StringIO()))
        self.config = SimpleNamespace(
            slack_bot_token="unused",
            slack_channel_id="C123",
            review_image_draft_dir=directory / "drafts",
        )
        self.save = Mock(return_value=StoreResult(True, "施設", 14, directory / "memos.json"))
        contexts.enter_context(patch.multiple(
            bot,
            App=ReviewApp,
            _infer_post_location=Mock(return_value=LocationInference("東京都", "test", "", "")),
            find_title_conflict=Mock(return_value=None),
            save_post_as_memo=self.save,
            _sync_git_after_publish=Mock(return_value=""),
        ))
        self.app = bot.create_app(self.config)
        self.client = Mock()
        self.logger = Mock()
        self.original = {
            "channel": "C123",
            "ts": "123.000",
            "text": "施設\n本文",
            "files": [self.file("F-original")],
        }
        self.client.conversations_replies.return_value = {"messages": [self.original]}
        self.client.chat_postMessage.return_value = {"ts": "123.001"}
        self.app.handlers["message"](self.original, {}, self.client, self.logger)
        self.review_ts = "123.001"
        self.blocks = self.client.chat_postMessage.call_args.kwargs["blocks"]

    @staticmethod
    def file(file_id: str) -> dict:
        return {
            "id": file_id,
            "name": f"{file_id}.jpg",
            "mimetype": "image/jpeg",
            "url_private_download": f"https://files.slack.com/{file_id}",
        }

    def click(self, action_id, *, selected_option=None, ack=None):
        action = next(
            element
            for block in self.blocks
            for element in block.get("elements", [])
            if element.get("action_id") == action_id
        )
        if selected_option:
            action = {**action, "selected_option": selected_option}
        self.app.handlers[action_id](
            ack=ack or Mock(),
            body={
                "actions": [action],
                "trigger_id": "trigger",
                "channel": {"id": "C123"},
                "message": {"ts": self.review_ts},
                "user": {"id": "U123"},
            },
            client=self.client,
            logger=self.logger,
        )

    def open_upload(self):
        self.click(ADD_REVIEW_IMAGES_ACTION_ID)
        return self.client.views_open.call_args.kwargs["view"]

    def submit(self, view, files, ack=None):
        callback_id = view["callback_id"]
        self.assertEqual(callback_id, MEMO_REVIEW_IMAGES_CALLBACK_ID)
        self.app.handlers[callback_id](
            ack=ack or Mock(),
            body={"user": {"id": "U123"}},
            view={
                **view,
                "state": {"values": {UPLOAD_IMAGES_BLOCK_ID: {
                    UPLOAD_IMAGES_ACTION_ID: {"files": files},
                }}},
            },
            client=self.client,
            logger=self.logger,
        )

    def read_updated_blocks(self):
        self.assertIsNotNone(self.client.chat_update.call_args, self.client.chat_postEphemeral.call_args)
        self.blocks = self.client.chat_update.call_args.kwargs["blocks"]
        return self.blocks[0]["text"]["text"]

    def test_repeated_batches_accumulate_in_order_and_are_published(self):
        first_batch = [self.file(f"F-{index}") for index in range(10)]
        view = self.open_upload()
        self.assertEqual(view["blocks"][0]["element"]["max_files"], 10)
        self.submit(view, first_batch)
        self.assertIn("添付画像:* 11件", self.read_updated_blocks())

        self.client.files_info.side_effect = lambda *, file: {"file": self.file(file)}
        self.submit(self.open_upload(), ["F-10", {"id": "F-11"}])
        self.assertIn("添付画像:* 13件", self.read_updated_blocks())
        self.submit(self.open_upload(), [self.file("F-12"), first_batch[0]])
        self.assertIn("添付画像:* 14件", self.read_updated_blocks())

        self.click(SELECT_REVIEW_THUMBNAIL_ACTION_ID, selected_option={"value": "123.000|F-12"})
        self.assertIn("サムネイル:* 1. F-12.jpg", self.read_updated_blocks())
        self.click(APPROVE_MEMO_ACTION_ID)
        post = self.save.call_args.args[1]
        self.assertEqual(
            [image.file_id for image in post.images],
            ["F-12", "F-original", *[f"F-{index}" for index in range(12)]],
        )
        self.assertEqual(list(self.config.review_image_draft_dir.iterdir()), [])

    def test_reload_after_restart_keeps_added_images(self):
        self.submit(self.open_upload(), [self.file("F-added")])
        self.read_updated_blocks()
        self.app = bot.create_app(self.config)
        self.client.chat_postMessage.return_value = {"ts": "123.002"}
        self.click(RELOAD_REVIEW_ACTION_ID)
        self.review_ts = "123.002"
        self.blocks = self.client.chat_postMessage.call_args.kwargs["blocks"]
        self.assertIn("添付画像:* 2件", self.blocks[0]["text"]["text"])
        self.submit(self.open_upload(), [self.file("F-after-reload")])
        self.assertIn("添付画像:* 3件", self.read_updated_blocks())
        self.click(DISMISS_REVIEW_ACTION_ID)
        self.assertEqual(list(self.config.review_image_draft_dir.iterdir()), [])
        self.save.assert_not_called()

    def test_failed_batch_does_not_discard_previously_added_images(self):
        self.submit(self.open_upload(), [self.file("F-added")])
        self.read_updated_blocks()
        view = self.open_upload()
        ack = Mock()
        self.submit(view, [], ack)
        self.assertIn(UPLOAD_IMAGES_BLOCK_ID, ack.call_args.kwargs["errors"])

        bad_file = {**self.file("F-invalid"), "mimetype": "application/pdf"}
        self.submit(view, [self.file("F-valid"), bad_file])
        self.client.chat_postEphemeral.assert_called_once()
        self.click(APPROVE_MEMO_ACTION_ID)
        post = self.save.call_args.args[1]
        self.assertEqual([image.file_id for image in post.images], ["F-original", "F-added"])

    def test_approval_waits_for_a_submitted_batch(self):
        allow_file_lookup = Event()
        lookup_started = Event()
        approval_acked = Event()

        def lookup(*, file):
            lookup_started.set()
            if not allow_file_lookup.wait(5):
                raise TimeoutError("File lookup was not released")
            return {"file": self.file(file)}

        self.client.files_info.side_effect = lookup
        view = self.open_upload()
        with ThreadPoolExecutor(max_workers=2) as workers:
            upload = workers.submit(self.submit, view, ["F-pending"])
            try:
                self.assertTrue(lookup_started.wait(5))
                approval = workers.submit(self.click, APPROVE_MEMO_ACTION_ID, ack=approval_acked.set)
                self.assertTrue(approval_acked.wait(5))
                self.save.assert_not_called()
            finally:
                allow_file_lookup.set()
            upload.result(timeout=5)
            approval.result(timeout=5)
        post = self.save.call_args.args[1]
        self.assertEqual([image.file_id for image in post.images], ["F-original", "F-pending"])


if __name__ == "__main__":
    unittest.main()
