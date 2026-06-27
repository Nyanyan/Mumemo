const siteTitle = "Mumemo - にゃにゃんの博物館メモ";
const memosUrl = "/data/memos.json";

const app = document.querySelector("#app");
const homeTemplate = document.querySelector("#home-template");
let entries = [];

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
  image.src = entry.image;
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

function renderLoading() {
  app.replaceChildren(createStatusMessage("読み込み中です。"));
}

function renderLoadError() {
  document.title = `読み込めません - ${siteTitle}`;
  app.replaceChildren(createStatusMessage("メモを読み込めませんでした。"));
}

function renderHome() {
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
    const matchesQuery = (entry) => `${entry.title}\n${entry.body}`.toLocaleLowerCase("ja").includes(query);
    const matched = query ? entries.filter(matchesQuery) : searchableItems;
    const shown = query ? matched : [...fixedItems, ...matched];

    grid.replaceChildren(...shown.map(createTile));
    resultCount.textContent = `${matched.length}件`;

    if (matched.length === 0 && query) {
      grid.append(createStatusMessage("該当するメモはありません。"));
    }
  };

  input.addEventListener("input", draw);
  draw();
}

function renderDetail(entry) {
  document.title = `${entry.title} - ${siteTitle}`;

  const detail = document.createElement("article");
  detail.className = "detail";

  const back = document.createElement("a");
  back.className = "back-link";
  back.href = "/";
  back.dataset.nav = "";
  back.textContent = "一覧へ戻る";

  const hero = document.createElement("div");
  hero.className = "detail-hero";

  const image = document.createElement("img");
  image.className = `detail-image${entry.iconImage ? " icon-image" : ""}`;
  image.src = entry.image;
  image.alt = "";

  const copy = document.createElement("div");
  copy.className = "detail-copy";

  const title = document.createElement("h2");
  title.className = "detail-title";
  title.textContent = entry.title;

  const text = document.createElement("p");
  text.className = "detail-text";
  text.textContent = entry.body;

  copy.append(title, text);
  hero.append(image, copy);
  detail.append(back, hero);
  app.replaceChildren(detail);
}

function renderNotFound(slug) {
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

window.addEventListener("popstate", route);
start();
