import { spawnSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const docsDir = path.join(repoRoot, "docs");
const memosPath = path.join(docsDir, "data", "memos.json");
const indexPath = path.join(docsDir, "index.html");
const fallbackPath = path.join(docsDir, "404.html");
const ogpManifestPath = path.join(docsDir, "assets", "ogp", "manifest.json");
const ogpGeneratorPath = path.join(repoRoot, "scripts", "generate-ogp-images.py");
const defaultImage = "/website_icon_small.png";
const homeOgpSourcePath = path.join(repoRoot, "OGP.jpg");
const homeOgpDocsPath = path.join(docsDir, "OGP.jpg");
const homeOgpImage = "/OGP.jpg";

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

function runOgpGenerator() {
  const pythonCommand = process.env.PYTHON || "python";
  const result = spawnSync(pythonCommand, [ogpGeneratorPath], {
    cwd: repoRoot,
    stdio: "inherit"
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`OGP image generation failed with exit code ${result.status}`);
  }
}

async function syncHomeOgpImage() {
  try {
    await fs.copyFile(homeOgpSourcePath, homeOgpDocsPath);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

async function readJson(pathname, fallback) {
  try {
    return JSON.parse(await fs.readFile(pathname, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") {
      return fallback;
    }
    throw error;
  }
}

async function siteBaseUrl() {
  const envValue = (process.env.MUMEMO_SITE_BASE_URL || "").trim();
  if (envValue) {
    return normalizeBaseUrl(envValue);
  }

  try {
    const cname = (await fs.readFile(path.join(docsDir, "CNAME"), "utf8"))
      .split(/\r?\n/)[0]
      .trim();
    return cname ? normalizeBaseUrl(cname) : "";
  } catch (error) {
    if (error.code === "ENOENT") {
      return "";
    }
    throw error;
  }
}

function normalizeBaseUrl(value) {
  const withProtocol = /^https?:\/\//i.test(value) ? value : `https://${value}`;
  return withProtocol.replace(/\/+$/g, "");
}

function absoluteUrl(baseUrl, urlPath) {
  if (!urlPath) {
    return "";
  }
  if (/^https?:\/\//i.test(urlPath)) {
    return urlPath;
  }
  const cleanPath = urlPath.startsWith("/") ? urlPath : `/${urlPath}`;
  return baseUrl ? `${baseUrl}${cleanPath}` : cleanPath;
}

function routePath(slug) {
  return `/${encodeURIComponent(slug)}`;
}

function summarize(text, fallback) {
  const cleanText = String(text || "").replace(/\s+/g, " ").trim();
  if (!cleanText) {
    return fallback;
  }
  return cleanText.length <= 130 ? cleanText : `${cleanText.slice(0, 127)}...`;
}

function extractTitle(html) {
  return html.match(/<title>([\s\S]*?)<\/title>/i)?.[1] || "Mumemo";
}

function extractDescription(html) {
  return html.match(/<meta\s+name="description"\s+content="([^"]*)"\s*>/i)?.[1] || "";
}

function renderHtml(templateHtml, meta) {
  let html = templateHtml.replace(
    /<title>[\s\S]*?<\/title>/i,
    `<title>${escapeHtml(meta.title)}</title>`
  );

  const descriptionTag = `<meta name="description" content="${escapeAttribute(meta.description)}">`;
  if (/<meta\s+name="description"\s+content="[^"]*"\s*>/i.test(html)) {
    html = html.replace(/<meta\s+name="description"\s+content="[^"]*"\s*>/i, descriptionTag);
  } else {
    html = html.replace(/<meta\s+name="viewport"[^>]*>/i, (match) => `${match}\n  ${descriptionTag}`);
  }

  html = html.replace(/\n?\s*<!-- mumemo:ogp:start -->[\s\S]*?<!-- mumemo:ogp:end -->\s*/g, "\n");
  const ogpBlock = ogpMetaBlock(meta);
  return html.replace(descriptionTag, `${descriptionTag}\n${ogpBlock}`);
}

function ogpMetaBlock(meta) {
  const tags = [
    "  <!-- mumemo:ogp:start -->",
    metaTag("property", "og:site_name", meta.siteName),
    metaTag("property", "og:title", meta.title),
    metaTag("property", "og:description", meta.description),
    metaTag("property", "og:type", meta.type),
    metaTag("property", "og:url", meta.url),
    metaTag("property", "og:image", meta.image),
    metaTag("property", "og:image:alt", meta.title)
  ];

  if (meta.imageWidth && meta.imageHeight) {
    tags.push(
      metaTag("property", "og:image:width", String(meta.imageWidth)),
      metaTag("property", "og:image:height", String(meta.imageHeight))
    );
  }

  tags.push(
    metaTag("name", "twitter:card", meta.twitterCard),
    metaTag("name", "twitter:title", meta.title),
    metaTag("name", "twitter:description", meta.description),
    metaTag("name", "twitter:image", meta.image),
    "  <!-- mumemo:ogp:end -->"
  );
  return tags.join("\n");
}

function metaTag(attributeName, name, content) {
  return `  <meta ${attributeName}="${escapeAttribute(name)}" content="${escapeAttribute(content)}">`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

function homeMeta({ siteTitle, siteDescription, baseUrl, hasHomeOgpImage }) {
  const image = absoluteUrl(baseUrl, hasHomeOgpImage ? homeOgpImage : defaultImage);
  return {
    siteName: siteTitle,
    title: siteTitle,
    description: siteDescription,
    type: "website",
    url: absoluteUrl(baseUrl, "/"),
    image,
    imageWidth: hasHomeOgpImage ? 1200 : null,
    imageHeight: hasHomeOgpImage ? 630 : null,
    twitterCard: hasHomeOgpImage ? "summary_large_image" : "summary"
  };
}

function memoMeta({ memo, siteTitle, siteDescription, baseUrl, ogpManifest }) {
  const ogpImage = ogpManifest[memo.slug] || {};
  const width = Number(ogpImage.width) || null;
  const height = Number(ogpImage.height) || null;
  return {
    siteName: siteTitle,
    title: `${memo.title} - ${siteTitle}`,
    description: summarize(memo.body, siteDescription),
    type: "article",
    url: absoluteUrl(baseUrl, routePath(memo.slug)),
    image: absoluteUrl(baseUrl, ogpImage.url || defaultImage),
    imageWidth: width,
    imageHeight: height,
    twitterCard: width && height && width === height ? "summary" : "summary_large_image"
  };
}

const rawMemos = JSON.parse(await fs.readFile(memosPath, "utf8"));
if (!Array.isArray(rawMemos)) {
  throw new Error(`${memosPath} must contain an array`);
}

runOgpGenerator();
const hasHomeOgpImage = await syncHomeOgpImage();

const memos = addSlugs(rawMemos);
const baseUrl = await siteBaseUrl();
const ogpManifest = await readJson(ogpManifestPath, {});
const indexHtml = await fs.readFile(indexPath, "utf8");
const siteTitle = extractTitle(indexHtml);
const siteDescription = extractDescription(indexHtml);
const defaultHtml = renderHtml(indexHtml, homeMeta({ siteTitle, siteDescription, baseUrl, hasHomeOgpImage }));

await fs.writeFile(indexPath, defaultHtml, "utf8");
await fs.writeFile(fallbackPath, defaultHtml, "utf8");

for (const memo of memos) {
  const routeDir = path.join(docsDir, memo.slug);
  await fs.mkdir(routeDir, { recursive: true });
  await fs.writeFile(
    path.join(routeDir, "index.html"),
    renderHtml(defaultHtml, memoMeta({ memo, siteTitle, siteDescription, baseUrl, ogpManifest })),
    "utf8"
  );
}

console.log(`Synced ${memos.length} route page(s).`);
