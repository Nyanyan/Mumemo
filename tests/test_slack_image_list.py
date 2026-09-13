from types import SimpleNamespace
import unittest

from mumemo_bot.slack_views import edit_modal_view


class SlackImageListTests(unittest.TestCase):
    def test_all_image_links_are_split_across_slack_safe_blocks(self) -> None:
        images = [
            "/assets/posts/"
            + "%E8%8C%A8%E5%9F%8E%E7%9C%8C%E9%9C%9E%E3%82%B1%E6%B5%A6"
            + "%E7%92%B0%E5%A2%83%E7%A7%91%E5%AD%A6%E3%82%BB%E3%83%B3"
            + f"%E3%82%BF%E3%83%BC/display/image-{index}.jpg"
            for index in range(1, 21)
        ]
        memo = SimpleNamespace(
            id="memo-1",
            title="入力済みタイトル",
            body="入力済み本文",
            location="茨城県",
            image=images[0],
            images=images,
        )

        view = edit_modal_view(
            memo=memo,
            channel_id="C123",
            message_ts="123.456",
            site_base_url="https://mumemo.nyanyan.dev",
        )
        image_sections = [
            block["text"]["text"]
            for block in view["blocks"]
            if block.get("type") == "section"
            and block.get("text", {}).get("text", "").startswith("*画像一覧")
        ]

        self.assertGreater(len(image_sections), 1)
        self.assertTrue(all(len(section) <= 2900 for section in image_sections))
        self.assertEqual(sum(section.count("|画像") for section in image_sections), 20)
        self.assertTrue(any("|画像20>" in section for section in image_sections))


if __name__ == "__main__":
    unittest.main()
