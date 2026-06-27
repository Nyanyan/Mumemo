# Mumemo

Static site files live in `docs/` for GitHub Pages.

## Adding or Updating Memos

Memo content is stored in `docs/data/memos.json`. Each item supports:

- `title`: displayed title and default URL source
- `body`: detail text and search text
- `image`: primary detail image path, such as `/assets/example.jpg`
- `thumbnail`: optional small tile image path; Slack images get generated JPEG thumbnails under `thumbs/`
- `images`: optional detail image paths; all are shown on the detail page
- `postedAt`: optional post date, such as `2026-06-27`; shown at the end of the detail page
- `slug`: optional stable URL slug; when omitted, the title is normalized
- `fixed`: optional; show before other items on the default top page
- `iconImage`: optional; render image with icon-style padding

After changing `docs/data/memos.json`, run:

```sh
node scripts/build-route-pages.mjs
```

This refreshes `docs/404.html` and the static `docs/<slug>/index.html` route entries.

## Slack Bot

The Slack receiver lives outside `docs/` in `mumemo_bot/`. It uses Slack Socket Mode, so it does not need a public HTTP endpoint while running locally.

Install dependencies:

```sh
python -m pip install -r requirements.txt
```

Copy `.env.example` values into `.env` and set real tokens there. `.env` is intentionally ignored by git.

Required Slack settings:

- `SLACK_BOT_TOKEN`: bot token, usually `xoxb-...`
- `SLACK_APP_TOKEN`: Socket Mode app token, usually `xapp-...`
- `SLACK_CHANNEL_ID`: channel to accept top-level posts from
- `SLACK_CHANNEL_NAME`: optional display name for startup logs
- `MUMEMO_SITE_BASE_URL`: optional public site URL used in publish-complete Slack messages; defaults to `docs/CNAME` when present

Useful Slack app permissions/events:

- App-level token scope: `connections:write`
- Bot token scopes: `channels:history`, `chat:write`, `files:read`, `commands`
- Event subscription: `message.channels`
- Interactivity enabled for buttons and modals
- Optional slash command: `/mumemo`

Run the receiver:

```sh
python run_slack_bot.py
```

Slack post format:

```text
Title line
Body text line 1
Body text line 2
```

New top-level Slack posts are not published immediately. The bot replies in the thread with a review message and buttons. Detected URLs are shown in the review. Press `URL修正` to edit only those URLs before publishing, `承認して公開` to save it to `docs/data/memos.json`, `再読み込み` to rebuild the review from the original Slack message, or `破棄` to remove only the Slack draft review. After publishing, Slack shows the public Mumemo page URL.

When a new Slack post has the same title as an existing memo, the review shows both versions. Use `既存投稿に追記` to append the new body/images to the existing memo, `別で投稿` to publish a separate memo while assigning the new memo a suffixed slug, or `上書き投稿` to replace the existing memo body/images while keeping its URL.

Attached image files are saved under `docs/assets/slack/<title>/`. Small JPEG tile thumbnails are generated under `docs/assets/slack/<title>/thumbs/`, while every attached original image is recorded in `images` so the detail page can show the full set. Detail page images can be clicked to open a larger view. Approved posts are inserted above older non-fixed posts, while fixed entries such as `これは何？` remain first.

To organize existing posts from Slack, type `mumemo`, `mumemo list`, or `mumemo 整理` in the configured channel. The bot posts the current list with `編集` and `削除` buttons. Fixed memos such as `これは何？` are shown and can be edited, but cannot be deleted. Deleting a memo also removes its local Slack image files, empty image title folders, and stale generated route folders when safe. If the slash command is configured, `/mumemo` opens the same organizer as an ephemeral Slack response.

In the edit modal, remove image URL lines to delete images, add URL lines to reference existing images, or use `画像を追加` to upload new image files from Slack. Uploaded files are copied into `docs/assets/slack/<title>/` and appended to the memo image list.

The bot updates local files, runs `node scripts/build-route-pages.mjs`, stages `docs/`, commits approved Slack publishes as `add <title>`, commits Slack deletes as `delete <title>`, and runs `git push origin main`. Run the bot from a clean `main` checkout with push access to the repository.
