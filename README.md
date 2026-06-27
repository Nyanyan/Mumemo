# Mumemo

Static site files live in `docs/` for GitHub Pages.

## Adding or Updating Memos

Memo content is stored in `docs/data/memos.json`. Each item supports:

- `title`: displayed title and default URL source
- `body`: detail text and search text
- `image`: public image path, such as `/assets/example.jpg`
- `slug`: optional stable URL slug; when omitted, the title is normalized
- `fixed`: optional; show before other items on the default top page
- `iconImage`: optional; render image with icon-style padding

After changing `docs/data/memos.json`, run:

```sh
node scripts/build-route-pages.mjs
```

This refreshes `docs/404.html` and the static `docs/<slug>/index.html` route entries.

## Future Slack Flow

Keep Slack tokens out of browser code. A Slack bot, webhook worker, or GitHub Action should receive Slack input, save images under `docs/assets/`, update `docs/data/memos.json`, run `node scripts/build-route-pages.mjs`, and push a commit. GitHub Pages can then publish the static result.
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
- Bot token scopes: `channels:history`, `chat:write`, `files:read`
- Event subscription: `message.channels`

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

Attached image files are saved under `docs/assets/slack/`; the first image becomes the memo thumbnail. The bot appends a memo to `docs/data/memos.json`, runs `node scripts/build-route-pages.mjs`, and replies in the Slack thread. It does not commit or push changes; review the generated files and commit them when ready.
