const rawEntries = [
      {
        title: "これは何？",
        body: "にゃにゃんが訪れた博物館のメモを並べた小さな棚です。\n\nタイトルと本文を検索できます。",
        image: "/website_icon.png",
        fixed: true,
        iconImage: true
      },
      {
        title: "架空のラーメン博物館",
        body: "20XX/YY/ZZ訪問\n\nラーメンは美味しい。",
        image: "/assets/ramen.jpg"
      },
      {
        title: "架空のパスタ博物館",
        body: "20XX/YY/ZZ訪問\n\nパスタも美味しい。",
        image: "/assets/pasta.jpg"
      }
    ];

    const app = document.querySelector("#app");
    const homeTemplate = document.querySelector("#home-template");
    const entries = addSlugs(rawEntries);

    function slugBase(title) {
      const normalized = title.normalize("NFKC").trim();
      return normalized
        .replace(/[\\/#?%&=+]/g, " ")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "") || "memo";
    }

    function addSlugs(items) {
      const seen = new Map();

      return items.map((item) => {
        const base = slugBase(item.title);
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

    function renderHome() {
      document.title = "にゃにゃんの博物館メモ";
      const view = homeTemplate.content.cloneNode(true);
      app.replaceChildren(view);

      const input = document.querySelector("#searchInput");
      const grid = document.querySelector("#tileGrid");
      const resultCount = document.querySelector("#resultCount");

      const draw = () => {
        const query = input.value.trim().toLocaleLowerCase("ja");
        const fixedItems = entries.filter((entry) => entry.fixed);
        const searchableItems = entries.filter((entry) => !entry.fixed);
        const matched = query
          ? searchableItems.filter((entry) => `${entry.title}\n${entry.body}`.toLocaleLowerCase("ja").includes(query))
          : searchableItems;
        const shown = [...fixedItems, ...matched];

        grid.replaceChildren(...shown.map(createTile));
        resultCount.textContent = `${matched.length}件`;

        if (matched.length === 0 && query) {
          const empty = document.createElement("p");
          empty.className = "empty-state";
          empty.textContent = "該当するメモはありません。";
          grid.append(empty);
        }
      };

      input.addEventListener("input", draw);
      draw();
    }

    function renderDetail(entry) {
      document.title = `${entry.title} - にゃにゃんの博物館メモ`;

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
      document.title = "メモが見つかりません - にゃにゃんの博物館メモ";

      const section = document.createElement("section");
      section.className = "detail";

      const back = document.createElement("a");
      back.className = "back-link";
      back.href = "/";
      back.dataset.nav = "";
      back.textContent = "一覧へ戻る";

      const message = document.createElement("p");
      message.className = "empty-state";
      message.textContent = slug ? "そのURLのメモはありません。" : "メモはありません。";

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
    route();
