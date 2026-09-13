from types import SimpleNamespace
import unittest

from mumemo_bot.bot import _image_order_lines_from_modal, _images_from_order_lines
from mumemo_bot.slack_views import (
    BODY_BLOCK_ID,
    IMAGES_BLOCK_ID,
    TITLE_BLOCK_ID,
    VALUE_ACTION_ID,
    edit_modal_view,
    modal_value,
)


class SlackEditModalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memo = SimpleNamespace(
            id="memo-1",
            title="入力済みタイトル",
            body="入力済み本文",
            location="茨城県",
            image="/assets/one.jpg",
            images=["/assets/one.jpg", "/assets/two.jpg"],
        )

    def test_title_and_body_are_validated_by_the_app(self) -> None:
        view = edit_modal_view(
            memo=self.memo,
            channel_id="C123",
            message_ts="123.456",
        )
        blocks = {block.get("block_id"): block for block in view["blocks"]}

        self.assertTrue(blocks[TITLE_BLOCK_ID]["optional"])
        self.assertTrue(blocks[BODY_BLOCK_ID]["optional"])

    def test_missing_modal_state_uses_current_value(self) -> None:
        view = {"state": {"values": {}}}

        self.assertEqual(
            modal_value(view, TITLE_BLOCK_ID, default=self.memo.title),
            self.memo.title,
        )

    def test_null_modal_state_uses_current_value(self) -> None:
        view = {
            "state": {
                "values": {
                    TITLE_BLOCK_ID: {VALUE_ACTION_ID: {"value": None}},
                }
            }
        }

        self.assertEqual(
            modal_value(view, TITLE_BLOCK_ID, default=self.memo.title),
            self.memo.title,
        )

    def test_explicit_empty_string_does_not_use_default(self) -> None:
        view = {
            "state": {
                "values": {
                    TITLE_BLOCK_ID: {VALUE_ACTION_ID: {"value": ""}},
                }
            }
        }

        self.assertEqual(
            modal_value(view, TITLE_BLOCK_ID, default=self.memo.title),
            "",
        )

    def test_missing_image_order_preserves_existing_images(self) -> None:
        view = {"state": {"values": {}}}
        order_lines = _image_order_lines_from_modal(
            view,
            self.memo.images,
            preserve_when_empty=True,
        )

        self.assertEqual(
            _images_from_order_lines(order_lines, self.memo.images, ""),
            self.memo.images,
        )

    def test_empty_image_order_with_uploads_preserves_existing_images(self) -> None:
        view = {
            "state": {
                "values": {
                    IMAGES_BLOCK_ID: {VALUE_ACTION_ID: {"value": ""}},
                }
            }
        }

        order_lines = _image_order_lines_from_modal(
            view,
            self.memo.images,
            preserve_when_empty=True,
        )

        self.assertEqual(
            _images_from_order_lines(order_lines, self.memo.images, ""),
            self.memo.images,
        )


if __name__ == "__main__":
    unittest.main()
