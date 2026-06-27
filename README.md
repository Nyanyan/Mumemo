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
