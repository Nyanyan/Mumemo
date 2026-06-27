const siteTitle = "Mumemo - にゃにゃんの博物館メモ";
const memosUrl = "/data/memos.json";
const shareIconUrl = "/assets/share-icon.svg";

const app = document.querySelector("#app");
const homeTemplate = document.querySelector("#home-template");
const postedAtFormatter = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit"
});
let entries = [];
let lightbox = null;
let tileFitFrame = 0;

const tileFitClasses = [
  "fit-title-more",
  "fit-summary-two",
  "fit-summary-one",
  "fit-summary-none",
  "fit-title-small",
  "fit-title-tiny",
  "fit-title-ellipsis"
];

function slugBase(value) {
  const normalized = value.normalize("NFKC").trim();
  return normalized
    .replace(/[\\/#?%&=+]/g, " ")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "") || "memo";
}

function addSlugs(items) {
  const seen = new Map();

  return items.map((item) => {
    const base = slugBase(item.slug || item.title);
    const count = seen.get(base) || 0;
    seen.set(base, count + 1);

    return {
      ...item,
      slug: count === 0 ? base : `${base}-${count + 1}`
    };
  });
}

function hrefFor(entry) {
  return `/${encodeURIComponent(entry.slug)}`;
}

function absoluteHrefFor(entry) {
  return new URL(hrefFor(entry), window.location.origin).href;
}

function currentSlug() {
  const path = window.location.pathname.replace(/^\/+|\/+$/g, "");
  if (!path) {
    return "";
  }

  try {
    return decodeURIComponent(path.split("/")[0]);
  } catch {
    return path.split("/")[0];
  }
}

function summarize(text) {
  return text.replace(/\s+/g, " ").trim();
}

function imagesFor(entry) {
  const images = Array.isArray(entry.images) ? entry.images : [];
  const candidates = [...images, entry.image].filter((image) => typeof image === "string" && image.trim());
  return [...new Set(candidates)];
}

function thumbnailFor(entry) {
  return entry.thumbnail || entry.image || imagesFor(entry)[0] || "/website_icon_small.png";
}

function postedAtValue(entry) {
  const direct = entry.postedAt || entry.posted_at || entry.createdAt || entry.created_at;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  if (typeof direct === "number" && Number.isFinite(direct)) {
    return new Date(direct).toISOString();
  }

  const source = entry.source;
  if (!source || typeof source !== "object") {
    return "";
  }

  const messageTs = source.message_ts || source.messageTs;
  if (typeof messageTs !== "string" && typeof messageTs !== "number") {
    return "";
  }

  const timestamp = Number.parseFloat(messageTs);
  if (!Number.isFinite(timestamp)) {
    return "";
  }
  return new Date(timestamp * 1000).toISOString();
}

function formatPostedAt(entry) {
  const rawValue = postedAtValue(entry);
  if (!rawValue) {
    return "";
  }

  const date = new Date(rawValue);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return postedAtFormatter.format(date);
}

function appendLinkedText(parent, text) {
  const urlPattern = /<((?:https?:\/\/)[^\s<>|]+)(?:\|([^<>]*))?>|(https?:\/\/[^\s<>]+)/g;
  const trailingPunctuation = /[.,\u3001\u3002)\uFF09\]\uFF3D}>\u300D\u300F]+$/;
  let lastIndex = 0;

  for (const match of text.matchAll(urlPattern)) {
    const slackUrl = match[1];
    const rawUrl = slackUrl || match[3];
    const url = slackUrl ? rawUrl : rawUrl.replace(trailingPunctuation, "");
    const trailing = slackUrl ? "" : rawUrl.slice(url.length);
    const index = match.index || 0;
    if (index > lastIndex) {
      parent.append(document.createTextNode(text.slice(lastIndex, index)));
    }

    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = slackUrl && match[2] ? match[2] : url;
    parent.append(link);
    if (trailing) {
      parent.append(document.createTextNode(trailing));
    }
    lastIndex = index + match[0].length;
  }

  if (lastIndex < text.length) {
    parent.append(document.createTextNode(text.slice(lastIndex)));
  }
}

function createStatusMessage(text) {
  const message = document.createElement("p");
  message.className = "empty-state";
  message.textContent = text;
  return message;
}

function createTile(entry) {
  const tile = document.createElement("a");
  tile.className = `tile${entry.fixed ? " fixed" : ""}`;
  tile.href = hrefFor(entry);
  tile.dataset.nav = "";

  const image = document.createElement("img");
  image.className = "tile-thumb";
  image.src = thumbnailFor(entry);
  image.alt = "";
  image.loading = entry.fixed ? "eager" : "lazy";

  const body = document.createElement("div");
  body.className = "tile-body";

  const title = document.createElement("h2");
  title.className = "tile-title";
  title.textContent = entry.title;

  const summary = document.createElement("p");
  summary.className = "tile-summary";
  summary.textContent = summarize(entry.body);

  body.append(title, summary);
  tile.append(image, body);
  return tile;
}

function scheduleTileTextFit() {
  window.cancelAnimationFrame(tileFitFrame);
  tileFitFrame = window.requestAnimationFrame(fitVisibleTileText);
}

function fitVisibleTileText() {
  document.querySelectorAll(".tile").forEach(fitTileText);
}

function fitTileText(tile) {
  const body = tile.querySelector(".tile-body");
  const title = tile.querySelector(".tile-title");
  if (!(body instanceof HTMLElement) || !(title instanceof HTMLElement)) {
    return;
  }

  const steps = [
    ["fit-title-more", "fit-summary-two"],
    ["fit-title-more", "fit-summary-one"],
    ["fit-title-more", "fit-summary-none"],
    ["fit-title-small", "fit-summary-none"],
    ["fit-title-tiny", "fit-summary-none"],
    ["fit-title-ellipsis", "fit-summary-none"]
  ];

  tile.classList.remove(...tileFitClasses);
  if (!tileTextOverflows(body, title)) {
    return;
  }

  for (const step of steps) {
    tile.classList.remove(...tileFitClasses);
    tile.classList.add(...step);
    if (!tileTextOverflows(body, title)) {
      return;
    }
  }
}

function tileTextOverflows(body, title) {
  const tolerance = 1;
  return body.scrollHeight > body.clientHeight + tolerance || title.scrollHeight > title.clientHeight + tolerance;
}

function renderLoading() {
  app.replaceChildren(createStatusMessage("読み込み中です。"));
}

function renderLoadError() {
  document.title = `読み込めません - ${siteTitle}`;
  app.replaceChildren(createStatusMessage("メモを読み込めませんでした。"));
}

function renderHome() {
  document.body.dataset.view = "home";
  document.title = siteTitle;
  const view = homeTemplate.content.cloneNode(true);
  app.replaceChildren(view);

  const input = document.querySelector("#searchInput");
  const grid = document.querySelector("#tileGrid");
  const resultCount = document.querySelector("#resultCount");

  const draw = () => {
    const query = input.value.trim().toLocaleLowerCase("ja");
    const fixedItems = entries.filter((entry) => entry.fixed);
    const searchableItems = entries.filter((entry) => !entry.fixed);
    const matchesQuery = (entry) => `${entry.title}\n${entry.body}\n${formatPostedAt(entry)}`.toLocaleLowerCase("ja").includes(query);
    const matched = query ? entries.filter(matchesQuery) : searchableItems;
    const shown = query ? matched : [...fixedItems, ...matched];

    grid.replaceChildren(...shown.map(createTile));
    resultCount.textContent = `${matched.length}件`;

    if (matched.length === 0 && query) {
      grid.append(createStatusMessage("該当するメモはありません。"));
    }
    scheduleTileTextFit();
  };

  input.addEventListener("input", draw);
  draw();
}

function createDetailImageButton(entry, imageUrl, index) {
  const button = document.createElement("button");
  button.className = "detail-image-button";
  button.type = "button";
  button.setAttribute("aria-label", `${entry.title}の画像${index + 1}を拡大`);

  const image = document.createElement("img");
  image.className = `detail-image${entry.iconImage ? " icon-image" : ""}`;
  image.src = imageUrl;
  image.alt = "";
  image.loading = index === 0 ? "eager" : "lazy";

  button.append(image);
  button.addEventListener("click", () => openImageLightbox(imageUrl, entry.title));
  return button;
}

function createDetailMedia(entry) {
  const images = imagesFor(entry);
  const media = document.createElement("div");
  media.className = `detail-media${images.length > 1 ? " many" : ""}`;

  for (const [index, imageUrl] of images.entries()) {
    media.append(createDetailImageButton(entry, imageUrl, index));
  }

  if (images.length === 0) {
    media.append(createDetailImageButton({ ...entry, iconImage: true }, "/website_icon_small.png", 0));
  }

  return media;
}

function createPostedAt(entry) {
  const postedAt = formatPostedAt(entry);
  if (!postedAt) {
    return null;
  }

  const meta = document.createElement("p");
  meta.className = "detail-posted-at";
  meta.textContent = `投稿日: ${postedAt}`;
  return meta;
}

function shareTextFor(entry) {
  return `${entry.title} - ${siteTitle}`;
}

function createShareIcon(className) {
  const icon = document.createElement("img");
  icon.className = className;
  icon.src = shareIconUrl;
  icon.alt = "";
  icon.loading = "lazy";
  return icon;
}

function appendShareButtonIcon(button, label) {
  button.append(createShareIcon("share-button-icon"), document.createTextNode(label));
}

function createShareLink(label, href) {
  const link = document.createElement("a");
  link.className = "share-button";
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label;
  return link;
}

function createShareActions(entry) {
  const shareUrl = absoluteHrefFor(entry);
  const shareText = shareTextFor(entry);
  const section = document.createElement("section");
  section.className = "share-actions";
  section.setAttribute("aria-label", "\u3053\u306e\u6295\u7a3f\u3092\u5171\u6709");

  const title = document.createElement("h3");
  title.className = "share-title";
  title.append(createShareIcon("share-title-icon"), document.createTextNode("\u5171\u6709"));

  const row = document.createElement("div");
  row.className = "share-row";

  const copyButton = document.createElement("button");
  copyButton.className = "share-button";
  copyButton.type = "button";
  copyButton.textContent = "\u30ea\u30f3\u30af\u3092\u30b3\u30d4\u30fc";

  const status = document.createElement("span");
  status.className = "share-status";
  status.setAttribute("aria-live", "polite");

  copyButton.addEventListener("click", async () => {
    const copied = await copyText(shareUrl);
    status.textContent = copied ? "\u30b3\u30d4\u30fc\u3057\u307e\u3057\u305f" : "\u30b3\u30d4\u30fc\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f";
    copyButton.textContent = copied ? "\u30b3\u30d4\u30fc\u6e08\u307f" : "\u30ea\u30f3\u30af\u3092\u30b3\u30d4\u30fc";
    window.setTimeout(() => {
      status.textContent = "";
      copyButton.textContent = "\u30ea\u30f3\u30af\u3092\u30b3\u30d4\u30fc";
    }, 1800);
  });
  row.append(copyButton);

  if (navigator.share) {
    const nativeShareButton = document.createElement("button");
    nativeShareButton.className = "share-button";
    nativeShareButton.type = "button";
    appendShareButtonIcon(nativeShareButton, "\u7aef\u672b\u3067\u5171\u6709");
    nativeShareButton.addEventListener("click", async () => {
      try {
        await navigator.share({
          title: entry.title,
          text: shareText,
          url: shareUrl
        });
      } catch (error) {
        if (error.name !== "AbortError") {
          status.textContent = "\u5171\u6709\u3092\u958b\u3051\u307e\u305b\u3093\u3067\u3057\u305f";
        }
      }
    });
    row.append(nativeShareButton);
  }

  row.append(
    createShareLink("X", `https://twitter.com/intent/tweet?${new URLSearchParams({ text: shareText, url: shareUrl })}`),
    createShareLink("Facebook", `https://www.facebook.com/sharer/sharer.php?${new URLSearchParams({ u: shareUrl })}`),
    createShareLink("LINE", `https://social-plugins.line.me/lineit/share?${new URLSearchParams({ url: shareUrl })}`),
    createShareLink("Bluesky", `https://bsky.app/intent/compose?${new URLSearchParams({ text: `${shareText}\n${shareUrl}` })}`)
  );

  section.append(title, row, status);
  return section;
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the legacy copy path.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-999px";
  document.body.append(textarea);
  textarea.select();

  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

function createDetailAuthorLink() {
  const headerAuthorLink = document.querySelector(".site-header .author-link");
  const link = document.createElement("a");
  link.className = "detail-author-link";
  link.href = headerAuthorLink?.href || "https://nyanyan.dev/";
  link.target = "_blank";
  link.rel = headerAuthorLink?.rel || "author noopener noreferrer";
  link.textContent = headerAuthorLink?.textContent || "\u4f5c\u8005Web\u30b5\u30a4\u30c8";
  return link;
}
function renderDetail(entry) {
  document.body.dataset.view = "detail";
  document.title = `${entry.title} - ${siteTitle}`;

  const detail = document.createElement("article");
  detail.className = "detail";

  const back = document.createElement("a");
  back.className = "back-link";
  back.href = "/";
  back.dataset.nav = "";
  back.textContent = "一覧へ戻る";

  const actions = document.createElement("div");
  actions.className = "detail-actions";
  actions.append(back, createDetailAuthorLink());

  const hero = document.createElement("div");
  hero.className = "detail-hero";

  const media = createDetailMedia(entry);

  const copy = document.createElement("div");
  copy.className = "detail-copy";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = entry.title;

  const text = document.createElement("p");
  text.className = "detail-text";
  appendLinkedText(text, entry.body);

  copy.append(title, text);
  const postedAt = createPostedAt(entry);
  if (postedAt) {
    copy.append(postedAt);
  }
  hero.append(media, copy, createShareActions(entry));
  detail.append(actions, hero);
  app.replaceChildren(detail);
}

function renderNotFound(slug) {
  document.body.dataset.view = "not-found";
  document.title = `メモが見つかりません - ${siteTitle}`;

  const section = document.createElement("section");
  section.className = "detail";

  const back = document.createElement("a");
  back.className = "back-link";
  back.href = "/";
  back.dataset.nav = "";
  back.textContent = "一覧へ戻る";

  const message = createStatusMessage(slug ? "そのURLのメモはありません。" : "メモはありません。");

  section.append(back, message);
  app.replaceChildren(section);
}

function route() {
  closeImageLightbox({ restoreFocus: false });
  const slug = currentSlug();

  if (!slug) {
    renderHome();
    return;
  }

  const entry = entries.find((item) => item.slug === slug);
  if (entry) {
    renderDetail(entry);
    return;
  }

  renderNotFound(slug);
}

function openImageLightbox(imageUrl, title) {
  closeImageLightbox({ restoreFocus: false });
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

  const overlay = document.createElement("div");
  overlay.className = "lightbox";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", `${title}の画像`);

  const panel = document.createElement("div");
  panel.className = "lightbox-panel";

  const close = document.createElement("button");
  close.className = "lightbox-close";
  close.type = "button";
  close.setAttribute("aria-label", "閉じる");
  close.textContent = "×";

  const image = document.createElement("img");
  image.className = "lightbox-image";
  image.src = imageUrl;
  image.alt = "";

  close.addEventListener("click", () => closeImageLightbox());
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeImageLightbox();
    }
  });

  panel.append(close, image);
  overlay.append(panel);
  document.body.append(overlay);
  document.body.classList.add("lightbox-open");
  lightbox = { overlay, previousFocus };
  close.focus({ preventScroll: true });
}

function closeImageLightbox(options = {}) {
  if (!lightbox) {
    return;
  }

  const { overlay, previousFocus } = lightbox;
  overlay.remove();
  document.body.classList.remove("lightbox-open");
  lightbox = null;

  if (options.restoreFocus === false || !previousFocus) {
    return;
  }
  previousFocus.focus({ preventScroll: true });
}

async function loadEntries() {
  const response = await fetch(memosUrl, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Failed to load ${memosUrl}: ${response.status}`);
  }

  const items = await response.json();
  if (!Array.isArray(items)) {
    throw new Error(`${memosUrl} must contain an array`);
  }

  return addSlugs(items);
}

async function start() {
  renderLoading();

  try {
    entries = await loadEntries();
    route();
  } catch (error) {
    console.error(error);
    renderLoadError();
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-nav]");
  if (!link || link.origin !== window.location.origin) {
    return;
  }

  event.preventDefault();
  window.history.pushState({}, "", link.href);
  route();
  window.scrollTo({ top: 0, behavior: "auto" });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeImageLightbox();
  }
});

window.addEventListener("resize", scheduleTileTextFit);
window.addEventListener("popstate", route);
if (document.fonts) {
  document.fonts.ready.then(scheduleTileTextFit);
}
start();
