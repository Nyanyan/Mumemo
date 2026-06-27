import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const docsDir = path.join(repoRoot, "docs");
const memosPath = path.join(docsDir, "data", "memos.json");
const indexPath = path.join(docsDir, "index.html");
const fallbackPath = path.join(docsDir, "404.html");

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

const rawMemos = JSON.parse(await fs.readFile(memosPath, "utf8"));
if (!Array.isArray(rawMemos)) {
  throw new Error(`${memosPath} must contain an array`);
}

const memos = addSlugs(rawMemos);
await fs.copyFile(indexPath, fallbackPath);

for (const memo of memos) {
  const routeDir = path.join(docsDir, memo.slug);
  await fs.mkdir(routeDir, { recursive: true });
  await fs.copyFile(indexPath, path.join(routeDir, "index.html"));
}

console.log(`Synced ${memos.length} route page(s).`);
