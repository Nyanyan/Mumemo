const siteTitle = "Mumemo - にゃにゃんの博物館メモ";
const memosUrl = "/data/memos.json";
const shareIconUrl = "/assets/share-icon.svg";
const defaultImageUrl = "/website_icon_dummy.jpg";
const locationsSlug = "locations";
const unknownLocationLabel = "不明";
const prefectures = [
  "北海道",
  "青森県",
  "岩手県",
  "宮城県",
  "秋田県",
  "山形県",
  "福島県",
  "茨城県",
  "栃木県",
  "群馬県",
  "埼玉県",
  "千葉県",
  "東京都",
  "神奈川県",
  "新潟県",
  "富山県",
  "石川県",
  "福井県",
  "山梨県",
  "長野県",
  "岐阜県",
  "静岡県",
  "愛知県",
  "三重県",
  "滋賀県",
  "京都府",
  "大阪府",
  "兵庫県",
  "奈良県",
  "和歌山県",
  "鳥取県",
  "島根県",
  "岡山県",
  "広島県",
  "山口県",
  "徳島県",
  "香川県",
  "愛媛県",
  "高知県",
  "福岡県",
  "佐賀県",
  "長崎県",
  "熊本県",
  "大分県",
  "宮崎県",
  "鹿児島県",
  "沖縄県"
];
const prefectureSet = new Set(prefectures);
const prefectureMapPositions = [
  { prefecture: "北海道", column: 12, row: 1, spanColumns: 2, spanRows: 2 },
  { prefecture: "青森県", column: 12, row: 4, spanColumns: 2 },
  { prefecture: "秋田県", column: 12, row: 5 },
  { prefecture: "岩手県", column: 13, row: 5 },
  { prefecture: "山形県", column: 12, row: 6 },
  { prefecture: "宮城県", column: 13, row: 6 },
  { prefecture: "新潟県", column: 11, row: 7, spanRows: 2 },
  { prefecture: "福島県", column: 12, row: 7, spanColumns: 2 },
  { prefecture: "石川県", column: 9, row: 8 },
  { prefecture: "富山県", column: 10, row: 8 },
  { prefecture: "栃木県", column: 12, row: 8 },
  { prefecture: "茨城県", column: 13, row: 8 },
  { prefecture: "山口県", column: 3, row: 9 },
  { prefecture: "島根県", column: 4, row: 9 },
  { prefecture: "鳥取県", column: 5, row: 9 },
  { prefecture: "兵庫県", column: 6, row: 9, spanRows: 2 },
  { prefecture: "京都府", column: 7, row: 9, spanRows: 2 },
  { prefecture: "福井県", column: 8, row: 9 },
  { prefecture: "岐阜県", column: 9, row: 9, spanRows: 2 },
  { prefecture: "長野県", column: 10, row: 9, spanRows: 2 },
  { prefecture: "群馬県", column: 11, row: 9 },
  { prefecture: "埼玉県", column: 12, row: 9 },
  { prefecture: "千葉県", column: 13, row: 9, spanRows: 2 },
  { prefecture: "広島県", column: 4, row: 10 },
  { prefecture: "岡山県", column: 5, row: 10 },
  { prefecture: "滋賀県", column: 8, row: 10 },
  { prefecture: "山梨県", column: 11, row: 10 },
  { prefecture: "東京都", column: 12, row: 10 },
  { prefecture: "佐賀県", column: 1, row: 11 },
  { prefecture: "福岡県", column: 2, row: 11 },
  { prefecture: "大分県", column: 3, row: 11 },
  { prefecture: "大阪府", column: 7, row: 11 },
  { prefecture: "奈良県", column: 8, row: 11 },
  { prefecture: "愛知県", column: 9, row: 11 },
  { prefecture: "静岡県", column: 10, row: 11, spanColumns: 2 },
  { prefecture: "神奈川県", column: 12, row: 11 },
  { prefecture: "長崎県", column: 1, row: 12 },
  { prefecture: "熊本県", column: 2, row: 12 },
  { prefecture: "宮崎県", column: 3, row: 12 },
  { prefecture: "愛媛県", column: 5, row: 12 },
  { prefecture: "香川県", column: 6, row: 12 },
  { prefecture: "和歌山県", column: 8, row: 12, spanRows: 2 },
  { prefecture: "三重県", column: 9, row: 12 },
  { prefecture: "高知県", column: 5, row: 13 },
  { prefecture: "徳島県", column: 6, row: 13 },
  { prefecture: "鹿児島県", column: 2, row: 13, spanColumns: 2 },
  { prefecture: "沖縄県", column: 1, row: 14 }
];


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
let brandTitleFrame = 0;
let scrollTopFrame = 0;
let scrollTopButton = null;
let homeRandomOrder = null;

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
  return `/${encodeURIComponent(entry.slug)}/`;
}

function locationsHref() {
  return `/${locationsSlug}/`;
}

function locationHref(location) {
  const url = new URL(locationsHref(), window.location.origin);
  url.searchParams.set("location", location);
  return `${url.pathname}${url.search}`;
}

function navigateToEntry(entry) {
  window.history.pushState({}, "", hrefFor(entry));
  route();
  window.scrollTo({ top: 0, behavior: "auto" });
}

function shuffledItems(items) {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

function randomPostCandidates(currentEntry = null) {
  const currentSlugValue = currentEntry?.slug || "";
  const candidates = entries.filter((entry) => !entry.fixed && entry.slug !== currentSlugValue);
  if (candidates.length > 0) {
    return candidates;
  }
  return entries.filter((entry) => entry.slug !== currentSlugValue);
}

function randomPostExcept(currentEntry = null) {
  const candidates = randomPostCandidates(currentEntry);
  if (candidates.length === 0) {
    return null;
  }
  return candidates[Math.floor(Math.random() * candidates.length)];
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

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => (
    {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;"
    }[character]
  ));
}

function imagesFor(entry) {
  const images = Array.isArray(entry.images) ? entry.images : [];
  const candidates = [...images, entry.image].filter((image) => typeof image === "string" && image.trim());
  return [...new Set(candidates)];
}

function originalImagesFor(entry) {
  const images = Array.isArray(entry.originalImages) ? entry.originalImages : [];
  const candidates = [...images, entry.originalImage].filter((image) => typeof image === "string" && image.trim());
  return candidates;
}

function fullSizeImageFor(entry, imageUrl, index) {
  const images = imagesFor(entry);
  const originals = originalImagesFor(entry);
  const imageIndex = images.indexOf(imageUrl);
  return originals[imageIndex >= 0 ? imageIndex : index] || "";
}

function openFullSizeImage(imageUrl, title) {
  if (!imageUrl) {
    return;
  }

  const escapedUrl = escapeHtml(imageUrl);
  const escapedTitle = escapeHtml(title || "Full size image");
  const viewer = `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapedTitle}</title>
<style>
html,body{margin:0;min-height:100%;background:#111;color:#fff}
body{display:grid;place-items:center}
img{display:block;max-width:100vw;max-height:100vh;width:auto;height:auto;object-fit:contain}
</style>
</head>
<body>
<img src="${escapedUrl}" alt="">
</body>
</html>`;
  const viewerUrl = URL.createObjectURL(new Blob([viewer], { type: "text/html" }));
  const opened = window.open(viewerUrl, "_blank");
  if (!opened) {
    window.location.href = imageUrl;
  } else {
    opened.opener = null;
  }
  window.setTimeout(() => URL.revokeObjectURL(viewerUrl), 60000);
}

function lightboxItemsFor(entry) {
  const images = imagesFor(entry);
  const sourceImages = images.length > 0 ? images : [defaultImageUrl];
  return sourceImages.map((imageUrl, index) => ({
    previewUrl: detailPreviewFor(imageUrl),
    fullSizeUrl: fullSizeImageFor(entry, imageUrl, index),
    fallbackUrl: imageUrl
  }));
}

function thumbnailFor(entry) {
  return entry.thumbnail || entry.image || imagesFor(entry)[0] || defaultImageUrl;
}

function detailPreviewFor(imageUrl) {
  const cleanImageUrl = typeof imageUrl === "string" ? imageUrl.trim() : "";
  if (!cleanImageUrl || cleanImageUrl === defaultImageUrl || cleanImageUrl === "/website_icon_small.png") {
    return cleanImageUrl || defaultImageUrl;
  }

  let url;
  try {
    url = new URL(cleanImageUrl, window.location.origin);
  } catch {
    return cleanImageUrl;
  }

  if (url.origin !== window.location.origin || !url.pathname.startsWith("/assets/posts/")) {
    return cleanImageUrl;
  }

  const parts = url.pathname.split("/");
  const filename = parts.pop() || "";
  if (!filename || parts.includes("thumbs") || parts.includes("display")) {
    return cleanImageUrl;
  }

  const dotIndex = filename.lastIndexOf(".");
  const stem = dotIndex > 0 ? filename.slice(0, dotIndex) : filename;
  if (!stem) {
    return cleanImageUrl;
  }

  parts.push("display", `${stem}-display.jpg`);
  return parts.join("/");
}

function useOriginalWhenPreviewMissing(image, previewUrl, originalUrl) {
  if (previewUrl === originalUrl) {
    return;
  }

  image.addEventListener(
    "error",
    () => {
      image.src = originalUrl;
    },
    { once: true }
  );
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

function updatedAtValue(entry) {
  const direct = entry.updatedAt || entry.updated_at || entry.modifiedAt || entry.modified_at;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  if (typeof direct === "number" && Number.isFinite(direct)) {
    return new Date(direct).toISOString();
  }
  return "";
}

function formatUpdatedAt(entry) {
  const rawValue = updatedAtValue(entry);
  if (!rawValue) {
    return "";
  }

  const date = new Date(rawValue);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return postedAtFormatter.format(date);
}

function dateSortTime(rawValue) {
  if (!rawValue) {
    return Number.NEGATIVE_INFINITY;
  }

  const date = new Date(rawValue);
  return Number.isNaN(date.getTime()) ? Number.NEGATIVE_INFINITY : date.getTime();
}

function latestActivityTime(entry) {
  return dateSortTime(updatedAtValue(entry) || postedAtValue(entry));
}

function sortByLatestActivity(items) {
  return items
    .map((item, index) => ({
      item,
      index,
      activityTime: latestActivityTime(item),
      postedTime: dateSortTime(postedAtValue(item))
    }))
    .sort((a, b) => (
      b.activityTime - a.activityTime
      || b.postedTime - a.postedTime
      || a.index - b.index
    ))
    .map(({ item }) => item);
}

function locationFor(entry) {
  const location = typeof entry.location === "string" ? entry.location.trim() : "";
  return location || unknownLocationLabel;
}

function displayLocationFor(entry) {
  const location = locationFor(entry);
  return entry.fixed && location === unknownLocationLabel ? "" : location;
}

function tileMetaFor(entry) {
  return displayLocationFor(entry);
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

  body.append(title);
  const metaText = tileMetaFor(entry);
  if (metaText) {
    const meta = document.createElement("p");
    meta.className = "tile-meta";
    meta.textContent = metaText;
    body.append(meta);
  }
  body.append(summary);
  tile.append(image, body);
  return tile;
}

function scheduleTileTextFit() {
  window.cancelAnimationFrame(tileFitFrame);
  tileFitFrame = window.requestAnimationFrame(fitVisibleTileText);
}

function scheduleBrandTitleWrap() {
  window.cancelAnimationFrame(brandTitleFrame);
  brandTitleFrame = window.requestAnimationFrame(updateBrandTitleWrap);
}

function updateBrandTitleWrap() {
  const title = document.querySelector(".brand-title");
  if (!(title instanceof HTMLElement)) {
    return;
  }

  title.classList.remove("is-stacked");
  const lineHeight = Number.parseFloat(window.getComputedStyle(title).lineHeight);
  if (!Number.isFinite(lineHeight) || lineHeight <= 0) {
    return;
  }
  if (title.scrollHeight > lineHeight * 1.35) {
    title.classList.add("is-stacked");
  }
}
function fitVisibleTileText() {
  document.querySelectorAll(".tile-grid").forEach(updateTileGridColumnState);
  document.querySelectorAll(".tile").forEach(fitTileText);
}

function updateTileGridColumnState(grid) {
  if (!(grid instanceof HTMLElement)) {
    return;
  }

  const columns = window.getComputedStyle(grid).gridTemplateColumns
    .split(/\s+/)
    .filter((column) => column && column !== "none");
  grid.classList.toggle("single-column", columns.length <= 1);
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

function ensureScrollTopButton() {
  if (scrollTopButton) {
    return scrollTopButton;
  }

  const button = document.createElement("button");
  button.className = "scroll-top-button";
  button.type = "button";
  button.hidden = true;
  button.tabIndex = -1;
  button.setAttribute("aria-label", "Back to top");
  button.addEventListener("click", () => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  });
  document.body.append(button);
  scrollTopButton = button;
  return button;
}

function setScrollTopButtonEnabled(enabled) {
  if (!enabled && !scrollTopButton) {
    return;
  }

  const button = ensureScrollTopButton();
  button.hidden = !enabled;
  if (!enabled) {
    button.classList.remove("is-visible");
    button.tabIndex = -1;
  }
}

function scheduleScrollTopButtonState() {
  if (scrollTopFrame) {
    return;
  }

  scrollTopFrame = window.requestAnimationFrame(updateScrollTopButtonState);
}

function updateScrollTopButtonState() {
  scrollTopFrame = 0;
  if (!scrollTopButton) {
    return;
  }

  const enabled = document.body.dataset.view === "home";
  const visible = enabled && window.scrollY > Math.max(360, window.innerHeight * 0.55);
  scrollTopButton.hidden = !enabled;
  scrollTopButton.classList.toggle("is-visible", visible);
  scrollTopButton.tabIndex = visible ? 0 : -1;
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
  setDetailHeaderShare(null);
  document.title = siteTitle;
  const view = homeTemplate.content.cloneNode(true);
  app.replaceChildren(view);
  ensureScrollTopButton();
  scheduleScrollTopButtonState();

  const input = document.querySelector("#searchInput");
  const grid = document.querySelector("#tileGrid");
  const resultCount = document.querySelector("#resultCount");
  const randomButtons = document.querySelectorAll("[data-random-home]");

  const draw = () => {
    const query = input.value.trim().toLocaleLowerCase("ja");
    const fixedItems = entries.filter((entry) => entry.fixed);
    const searchableItems = sortByLatestActivity(entries.filter((entry) => !entry.fixed));
    const orderedItems = homeRandomOrder || searchableItems;
    const searchBase = [...fixedItems, ...orderedItems];
    const matchesQuery = (entry) => `${entry.title}\n${entry.body}\n${formatPostedAt(entry)}\n${formatUpdatedAt(entry)}\n${locationFor(entry)}`.toLocaleLowerCase("ja").includes(query);
    const matched = query ? searchBase.filter(matchesQuery) : orderedItems;
    const shown = query ? matched : [...fixedItems, ...matched];

    grid.replaceChildren(...shown.map(createTile));
    resultCount.textContent = `${matched.length}件`;

    if (matched.length === 0 && query) {
      grid.append(createStatusMessage("該当するメモはありません。"));
    }
    scheduleTileTextFit();
  };

  const shuffleHome = () => {
    homeRandomOrder = shuffledItems(entries.filter((entry) => !entry.fixed));
    input.value = "";
    draw();
  };

  randomButtons.forEach((button) => {
    if (button instanceof HTMLButtonElement) {
      button.onclick = shuffleHome;
    }
  });
  input.addEventListener("input", draw);
  draw();
}

function selectedLocationFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return (params.get("location") || "").trim();
}

function locationSearchEntries() {
  return entries.filter((entry) => !entry.fixed);
}

function createLocationCountData() {
  const prefectureCounts = new Map(prefectures.map((prefecture) => [prefecture, 0]));
  const countryCounts = new Map();
  let unknownCount = 0;

  for (const entry of locationSearchEntries()) {
    const location = locationFor(entry);
    if (prefectureSet.has(location)) {
      prefectureCounts.set(location, (prefectureCounts.get(location) || 0) + 1);
    } else if (location === unknownLocationLabel) {
      unknownCount += 1;
    } else {
      countryCounts.set(location, (countryCounts.get(location) || 0) + 1);
    }
  }

  return {
    prefectures: prefectureCounts,
    countries: [...countryCounts.entries()].sort((a, b) => a[0].localeCompare(b[0], "ja")),
    unknown: unknownCount
  };
}

function createLocationItem(location, count, selectedLocation, hrefFactory = locationHref) {
  const link = document.createElement("a");
  link.className = [
    "location-item",
    count === 0 ? "is-empty" : "",
    location === selectedLocation ? "current" : ""
  ].filter(Boolean).join(" ");
  link.href = hrefFactory(location);
  link.dataset.nav = "";
  if (location === selectedLocation) {
    link.setAttribute("aria-current", "page");
  }

  const name = document.createElement("span");
  name.className = "location-name";
  name.textContent = location;

  const countText = document.createElement("span");
  countText.className = "location-count";
  countText.textContent = `(${count}\u4ef6)`;

  link.append(name, countText);
  return link;
}

function createLocationGroup(title, items, selectedLocation, hrefFactory = locationHref) {
  if (items.length === 0) {
    return null;
  }

  const section = document.createElement("section");
  section.className = "location-section";

  const heading = document.createElement("h3");
  heading.className = "location-section-title";
  heading.textContent = title;

  const list = document.createElement("div");
  list.className = "location-list";
  list.append(...items.map(([location, count]) => createLocationItem(location, count, selectedLocation, hrefFactory)));

  section.append(heading, list);
  return section;
}

function shortPrefectureName(prefecture) {
  if (prefecture === "北海道") {
    return prefecture;
  }
  return prefecture.replace(/[都府県]$/, "");
}

function createLocationMapPrefectureButton(mapItem, countData, selectedLocation) {
  const { prefecture, column, row, spanColumns = 1, spanRows = 1 } = mapItem;
  const count = countData.prefectures.get(prefecture) || 0;
  const link = document.createElement("a");
  link.className = [
    "location-map-prefecture",
    spanColumns > 1 || spanRows > 1 ? "is-large" : "",
    count === 0 ? "is-empty" : "",
    prefecture === selectedLocation ? "current" : ""
  ].filter(Boolean).join(" ");
  link.href = locationHref(prefecture);
  link.dataset.nav = "";
  link.style.gridColumn = `${column} / span ${spanColumns}`;
  link.style.gridRow = `${row} / span ${spanRows}`;
  link.title = `${prefecture} (${count}件)`;
  link.setAttribute("aria-label", `${prefecture}の投稿 ${count}件`);
  if (prefecture === selectedLocation) {
    link.setAttribute("aria-current", "page");
  }

  const name = document.createElement("span");
  name.className = "location-map-name";
  name.textContent = shortPrefectureName(prefecture);

  const countText = document.createElement("span");
  countText.className = "location-map-count";
  countText.textContent = count;

  link.append(name, countText);
  return link;
}

function createLocationMap(countData, selectedLocation) {
  const section = document.createElement("section");
  section.className = "location-map-section";

  const heading = document.createElement("h3");
  heading.className = "location-section-title";
  heading.textContent = "地図で検索";

  const mapScroll = document.createElement("div");
  mapScroll.className = "location-map-scroll";

  const map = document.createElement("div");
  map.className = "japan-map";
  map.setAttribute("role", "group");
  map.setAttribute("aria-label", "都道府県で検索");
  map.append(...prefectureMapPositions.map((mapItem) => (
    createLocationMapPrefectureButton(mapItem, countData, selectedLocation)
  )));

  mapScroll.append(map);
  section.append(heading, mapScroll);
  return section;
}

function renderLocationSearch() {
  document.body.dataset.view = "locations";
  setDetailHeaderShare(null);
  const selectedLocation = selectedLocationFromUrl();
  const selectedLabel = selectedLocation;
  document.title = selectedLabel ? `${selectedLabel} - \u5834\u6240\u3067\u691c\u7d22 - ${siteTitle}` : `\u5834\u6240\u3067\u691c\u7d22 - ${siteTitle}`;

  const countData = createLocationCountData();
  const section = document.createElement("section");
  section.className = "location-view";

  const header = document.createElement("div");
  header.className = "location-header";

  const title = document.createElement("h2");
  title.className = "location-title";
  title.textContent = "\u5834\u6240\u3067\u691c\u7d22";

  const filterToggle = document.createElement("button");
  filterToggle.className = "location-filter-toggle";
  filterToggle.type = "button";
  filterToggle.setAttribute("aria-controls", "locationFilters");

  const back = document.createElement("a");
  back.className = "back-link";
  back.href = "/";
  back.dataset.nav = "";
  back.textContent = "\u4e00\u89a7\u3078\u623b\u308b";

  const headerActions = document.createElement("div");
  headerActions.className = "location-header-actions";
  headerActions.append(filterToggle, back);
  header.append(title, headerActions);

  const groups = document.createElement("div");
  groups.id = "locationFilters";
  groups.className = "location-sections";
  let filtersHidden = Boolean(selectedLabel);
  const updateFilterVisibility = () => {
    groups.hidden = filtersHidden;
    groups.setAttribute("aria-hidden", String(filtersHidden));
    filterToggle.textContent = filtersHidden ? "\u7d5e\u308a\u8fbc\u307f\u3092\u8868\u793a" : "\u7d5e\u308a\u8fbc\u307f\u3092\u975e\u8868\u793a";
    filterToggle.setAttribute("aria-expanded", String(!filtersHidden));
  };
  filterToggle.addEventListener("click", () => {
    filtersHidden = !filtersHidden;
    updateFilterVisibility();
  });
  const otherItems = [...countData.countries, [unknownLocationLabel, countData.unknown]];
  [
    createLocationMap(countData, selectedLocation),
    createLocationGroup("\u6d77\u5916\u30fb\u4e0d\u660e", otherItems, selectedLocation)
  ].forEach((group) => {
    if (group) {
      groups.append(group);
    }
  });

  updateFilterVisibility();
  section.append(header, groups);

  if (selectedLabel) {
    const results = document.createElement("section");
    results.className = "location-results";

    const resultsTitle = document.createElement("h3");
    resultsTitle.className = "location-results-title";
    resultsTitle.textContent = `${selectedLabel}\u306e\u6295\u7a3f`;

    const matched = locationSearchEntries().filter((entry) => locationFor(entry) === selectedLocation);
    const grid = document.createElement("div");
    grid.className = "tile-grid";
    if (matched.length > 0) {
      grid.append(...matched.map(createTile));
    } else {
      grid.append(createStatusMessage("\u8a72\u5f53\u3059\u308b\u30e1\u30e2\u306f\u3042\u308a\u307e\u305b\u3093\u3002"));
    }

    results.append(resultsTitle, grid);
    section.append(results);
  }

  app.replaceChildren(section);
  scheduleTileTextFit();
}

function createDetailImageButton(entry, imageUrl, index, lightboxItems = null) {
  const button = document.createElement("button");
  button.className = "detail-image-button";
  button.type = "button";
  button.setAttribute("aria-label", `${entry.title}の画像${index + 1}を拡大`);

  const image = document.createElement("img");
  image.className = `detail-image${entry.iconImage ? " icon-image" : ""}`;
  const previewUrl = detailPreviewFor(imageUrl);
  image.src = previewUrl;
  image.alt = "";
  image.loading = index === 0 ? "eager" : "lazy";
  useOriginalWhenPreviewMissing(image, previewUrl, imageUrl);

  button.append(image);
  button.addEventListener("click", () => {
    openImageLightbox(lightboxItems || [{ previewUrl, fullSizeUrl: fullSizeImageFor(entry, imageUrl, index) }], entry.title, index);
  });
  return button;
}

function createDetailMedia(entry) {
  const images = imagesFor(entry);
  const lightboxItems = lightboxItemsFor(entry);
  const media = document.createElement("div");
  media.className = `detail-media${images.length > 1 ? " many" : ""}`;

  for (const [index, imageUrl] of images.entries()) {
    media.append(createDetailImageButton(entry, imageUrl, index, lightboxItems));
  }

  if (images.length === 0) {
    media.append(createDetailImageButton({ ...entry, iconImage: true }, defaultImageUrl, 0, lightboxItems));
  }

  return media;
}

function createPostedAt(entry) {
  const postedAt = formatPostedAt(entry);
  if (!postedAt) {
    return null;
  }

  const updatedAt = formatUpdatedAt(entry);
  const meta = document.createElement("p");
  meta.className = "detail-posted-at";

  const posted = document.createElement("span");
  posted.textContent = `投稿日: ${postedAt}`;
  meta.append(posted);

  if (updatedAt) {
    const updated = document.createElement("span");
    updated.textContent = `最終更新日: ${updatedAt}`;
    meta.append(updated);
  }

  return meta;
}

function createLocationMeta(entry) {
  const location = displayLocationFor(entry);
  if (!location) {
    return null;
  }
  const meta = document.createElement("p");
  meta.className = "detail-location";
  meta.textContent = `場所: ${location}`;
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


function createShareActions(entry, modifier = "") {
  const shareUrl = absoluteHrefFor(entry);
  const shareText = shareTextFor(entry);
  const section = document.createElement("section");
  section.className = modifier ? `share-actions ${modifier}` : "share-actions";
  section.setAttribute("aria-label", "\u3053\u306e\u6295\u7a3f\u3092\u5171\u6709");

  const details = document.createElement("details");
  details.className = "share-menu";

  const summary = document.createElement("summary");
  summary.className = "share-menu-button";
  summary.append(createShareIcon("share-button-icon"), document.createTextNode("\u5171\u6709"));

  const menu = document.createElement("div");
  menu.className = "share-menu-panel";

  const copyButton = document.createElement("button");
  copyButton.className = "share-menu-item";
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
  menu.append(copyButton);

  if (navigator.share) {
    const nativeShareButton = document.createElement("button");
    nativeShareButton.className = "share-menu-item";
    nativeShareButton.type = "button";
    nativeShareButton.textContent = "\u7aef\u672b\u3067\u5171\u6709";
    nativeShareButton.addEventListener("click", async () => {
      try {
        await navigator.share({
          title: entry.title,
          text: shareText,
          url: shareUrl
        });
        details.open = false;
      } catch (error) {
        if (error.name !== "AbortError") {
          status.textContent = "\u5171\u6709\u3092\u958b\u3051\u307e\u305b\u3093\u3067\u3057\u305f";
        }
      }
    });
    menu.append(nativeShareButton);
  }

  [
    ["X", `https://twitter.com/intent/tweet?${new URLSearchParams({ text: shareText, url: shareUrl })}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?${new URLSearchParams({ u: shareUrl })}`],
    ["LINE", `https://social-plugins.line.me/lineit/share?${new URLSearchParams({ url: shareUrl })}`],
    ["Bluesky", `https://bsky.app/intent/compose?${new URLSearchParams({ text: `${shareText}\n${shareUrl}` })}`]
  ].forEach(([label, href]) => {
    const link = document.createElement("a");
    link.className = "share-menu-item";
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    menu.append(link);
  });

  menu.append(status);
  details.append(summary, menu);
  section.append(details);
  return section;
}

function setDetailHeaderShare(entry = null) {
  const headerActions = document.querySelector(".site-header .header-actions");
  if (!(headerActions instanceof HTMLElement)) {
    return;
  }

  const homeShareMenu = headerActions.querySelector("#homeShareMenu");
  if (homeShareMenu instanceof HTMLElement) {
    homeShareMenu.hidden = true;
  }
  const homeShareButton = headerActions.querySelector(".home-share-button");
  if (homeShareButton instanceof HTMLElement) {
    homeShareButton.setAttribute("aria-expanded", "false");
  }

  headerActions.querySelectorAll(".header-detail-share-actions").forEach((share) => {
    share.remove();
  });

  if (entry) {
    headerActions.append(createShareActions(entry, "header-detail-share-actions"));
  }
}

function shareHrefForTarget(target, shareUrl, shareText) {
  const params = {
    x: () => `https://twitter.com/intent/tweet?${new URLSearchParams({ text: shareText, url: shareUrl })}`,
    facebook: () => `https://www.facebook.com/sharer/sharer.php?${new URLSearchParams({ u: shareUrl })}`,
    line: () => `https://social-plugins.line.me/lineit/share?${new URLSearchParams({ url: shareUrl })}`,
    bluesky: () => `https://bsky.app/intent/compose?${new URLSearchParams({ text: `${shareText}\n${shareUrl}` })}`
  };
  return params[target]?.() || shareUrl;
}

function closeShareMenus(event = null) {
  document.querySelectorAll(".share-menu[open]").forEach((menu) => {
    if (!(menu instanceof HTMLDetailsElement)) {
      return;
    }
    if (!event || !menu.contains(event.target)) {
      menu.open = false;
    }
  });
}

function setupHomeShareButton() {
  const share = document.querySelector(".home-share");
  const button = document.querySelector(".home-share-button");
  const menu = document.querySelector("#homeShareMenu");
  if (!(share instanceof HTMLElement) || !(button instanceof HTMLButtonElement) || !(menu instanceof HTMLElement)) {
    return;
  }

  const shareUrl = new URL("/", window.location.origin).href;
  const copyButton = menu.querySelector("[data-home-share-copy]");
  const nativeButton = menu.querySelector("[data-home-share-native]");
  const status = menu.querySelector(".home-share-status");
  let resetTimer = 0;

  menu.querySelectorAll("[data-home-share-target]").forEach((link) => {
    const target = link.getAttribute("data-home-share-target") || "";
    link.href = shareHrefForTarget(target, shareUrl, siteTitle);
  });

  if (nativeButton instanceof HTMLButtonElement && !navigator.share) {
    nativeButton.hidden = true;
  }

  const setOpen = (open) => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  };

  button.addEventListener("click", () => {
    setOpen(menu.hidden);
  });

  copyButton?.addEventListener("click", async () => {
    const copied = await copyText(shareUrl);
    if (status) {
      status.textContent = copied ? "コピーしました" : "コピーできませんでした";
      window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => {
        status.textContent = "";
      }, 1800);
    }
  });

  nativeButton?.addEventListener("click", async () => {
    if (!navigator.share) {
      return;
    }
    try {
      await navigator.share({ title: siteTitle, text: siteTitle, url: shareUrl });
      setOpen(false);
    } catch (error) {
      if (error.name !== "AbortError" && status) {
        status.textContent = "共有を開けませんでした";
      }
    }
  });

  document.addEventListener("click", (event) => {
    if (!share.contains(event.target)) {
      setOpen(false);
    }
  });


  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
    }
  });
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

function createRandomPostButton(currentEntry) {
  const button = document.createElement("button");
  button.className = "detail-random-button";
  button.type = "button";
  button.textContent = "ランダム投稿";
  button.disabled = randomPostCandidates(currentEntry).length === 0;
  button.addEventListener("click", () => {
    const entry = randomPostExcept(currentEntry);
    if (entry) {
      navigateToEntry(entry);
    }
  });
  return button;
}
function renderDetail(entry) {
  document.body.dataset.view = "detail";
  setDetailHeaderShare(entry);
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
  actions.append(back, createRandomPostButton(entry));

  const header = document.createElement("header");
  header.className = "detail-header";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = entry.title;

  const meta = document.createElement("div");
  meta.className = "detail-meta";
  const locationMeta = createLocationMeta(entry);
  if (locationMeta) {
    meta.append(locationMeta);
  }
  const postedAt = createPostedAt(entry);
  if (postedAt) {
    meta.append(postedAt);
  }

  header.append(title, meta);

  const media = createDetailMedia(entry);

  const copy = document.createElement("div");
  copy.className = "detail-copy";

  const text = document.createElement("p");
  text.className = "detail-text";
  appendLinkedText(text, entry.body);
  copy.append(text);

  const body = document.createElement("div");
  body.className = "detail-body";
  body.append(copy, media);

  detail.append(actions, header, body);
  app.replaceChildren(detail);
}

function renderNotFound(slug) {
  document.body.dataset.view = "not-found";
  setDetailHeaderShare(null);
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
  setScrollTopButtonEnabled(false);

  if (slug === locationsSlug) {
    renderLocationSearch();
    return;
  }

  const entry = entries.find((item) => item.slug === slug);
  if (entry) {
    renderDetail(entry);
    return;
  }

  renderNotFound(slug);
}

function openImageLightbox(lightboxItems, title, initialIndex = 0) {
  closeImageLightbox({ restoreFocus: false });
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const items = (Array.isArray(lightboxItems) ? lightboxItems : [])
    .map((item) => ({
      previewUrl: typeof item.previewUrl === "string" ? item.previewUrl : "",
      fullSizeUrl: typeof item.fullSizeUrl === "string" ? item.fullSizeUrl : "",
      fallbackUrl: typeof item.fallbackUrl === "string" ? item.fallbackUrl : ""
    }))
    .filter((item) => item.previewUrl);
  if (items.length === 0) {
    return;
  }
  let currentIndex = Math.min(Math.max(initialIndex, 0), items.length - 1);

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
  image.alt = "";

  const actions = document.createElement("div");
  actions.className = "lightbox-actions";

  const fullSizeLink = document.createElement("a");
  fullSizeLink.className = "lightbox-fullsize";
  fullSizeLink.target = "_blank";
  fullSizeLink.rel = "noopener noreferrer";
  fullSizeLink.textContent = "フルサイズ画像";
  fullSizeLink.addEventListener("click", (event) => {
    event.preventDefault();
    openFullSizeImage(fullSizeLink.href, title);
  });
  actions.append(fullSizeLink);

  const previous = document.createElement("button");
  previous.className = "lightbox-nav previous";
  previous.type = "button";
  previous.setAttribute("aria-label", "前の画像");
  previous.textContent = "‹";

  const next = document.createElement("button");
  next.className = "lightbox-nav next";
  next.type = "button";
  next.setAttribute("aria-label", "次の画像");
  next.textContent = "›";

  const showImage = (nextIndex) => {
    currentIndex = (nextIndex + items.length) % items.length;
    const item = items[currentIndex];
    let fallbackHref = "";
    if (item.fallbackUrl) {
      try {
        fallbackHref = new URL(item.fallbackUrl, window.location.href).href;
      } catch {
        fallbackHref = "";
      }
    }
    image.onerror = fallbackHref ? () => {
      if (image.src !== fallbackHref) {
        image.src = item.fallbackUrl;
      }
    } : null;
    image.src = item.previewUrl;
    if (item.fullSizeUrl) {
      fullSizeLink.href = item.fullSizeUrl;
      actions.hidden = false;
    } else {
      fullSizeLink.removeAttribute("href");
      actions.hidden = true;
    }
  };

  const showPrevious = () => showImage(currentIndex - 1);
  const showNext = () => showImage(currentIndex + 1);

  close.addEventListener("click", () => closeImageLightbox());
  previous.addEventListener("click", showPrevious);
  next.addEventListener("click", showNext);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeImageLightbox();
    }
  });

  panel.append(close, image);
  if (items.length > 1) {
    panel.append(previous, next);
  }
  panel.append(actions);
  overlay.append(panel);
  document.body.append(overlay);
  document.body.classList.add("lightbox-open");
  const handleKeydown = (event) => {
    if (event.key === "ArrowLeft" && items.length > 1) {
      event.preventDefault();
      showPrevious();
    } else if (event.key === "ArrowRight" && items.length > 1) {
      event.preventDefault();
      showNext();
    } else if (event.key === "Escape") {
      closeImageLightbox();
    }
  };
  document.addEventListener("keydown", handleKeydown);
  lightbox = { overlay, previousFocus, handleKeydown };
  showImage(currentIndex);
  close.focus({ preventScroll: true });
}

function closeImageLightbox(options = {}) {
  if (!lightbox) {
    return;
  }

  const { overlay, previousFocus, handleKeydown } = lightbox;
  if (handleKeydown) {
    document.removeEventListener("keydown", handleKeydown);
  }
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

document.addEventListener("click", (event) => {
  closeShareMenus(event);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeImageLightbox();
    closeShareMenus();
  }
});

window.addEventListener("resize", () => {
  scheduleTileTextFit();
  scheduleBrandTitleWrap();
  scheduleScrollTopButtonState();
});
window.addEventListener("scroll", scheduleScrollTopButtonState, { passive: true });
window.addEventListener("popstate", route);
if (document.fonts) {
  document.fonts.ready.then(() => {
    scheduleTileTextFit();
    scheduleBrandTitleWrap();
  });
}
setupHomeShareButton();
scheduleBrandTitleWrap();
start();
