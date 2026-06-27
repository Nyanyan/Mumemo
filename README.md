# Mumemo

Static site files live in `docs/` for GitHub Pages.

## Adding or Updating Memos

Memo content is stored in `docs/data/memos.json`. Each item supports:

- `title`: displayed title and default URL source
- `body`: detail text and search text
- `image`: public thumbnail image path, such as `/assets/example.jpg`
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

New top-level Slack posts are not published immediately. The bot replies in the thread with a review message and buttons. Press `承認して公開` to save it to `docs/data/memos.json`; `再読み込み` rebuilds the review from the original Slack message; `破棄` removes only the Slack draft review.

Attached image files are saved under `docs/assets/slack/`. The first image becomes the tile thumbnail, and every attached image is recorded in `images` so the detail page can show the full set. Detail page images can be clicked to open a larger view. Approved posts are inserted above older non-fixed posts, while fixed entries such as `これは何？` remain first.

To organize existing posts from Slack, type `mumemo`, `mumemo list`, or `mumemo 整理` in the configured channel. The bot posts the current list with `編集` and `削除` buttons. If the slash command is configured, `/mumemo` opens the same organizer as an ephemeral Slack response.

The bot updates local files and runs `node scripts/build-route-pages.mjs`. It does not commit or push changes; review the generated files and commit them when ready.
