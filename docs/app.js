(() => {
  const els = {
    updated: document.getElementById("updated"),
    tabs: document.getElementById("tabs"),
    search: document.getElementById("search"),
    stories: document.getElementById("stories"),
    empty: document.getElementById("empty"),
    notice: document.getElementById("notice"),
  };

  let data = null;
  let current = null;

  const storedTab = () => { try { return localStorage.getItem("tab"); } catch { return null; } };
  const saveTab = (id) => { try { localStorage.setItem("tab", id); } catch { /* ignore */ } };

  function timeAgo(iso) {
    if (!iso) return "";
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours} hr ago`;
    const days = Math.round(hours / 24);
    return `${days} day${days > 1 ? "s" : ""} ago`;
  }

  function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    for (const child of children) if (child) node.append(child);
    return node;
  }

  function renderTabs() {
    els.tabs.replaceChildren(...data.categories.map((c) => {
      const btn = el("button", { className: "tab", type: "button" }, [
        c.label, el("span", { className: "count", textContent: c.stories.length }),
      ]);
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(c.id === current));
      btn.addEventListener("click", () => { current = c.id; saveTab(c.id); renderTabs(); renderStories(); });
      return btn;
    }));
  }

  function renderStories() {
    const category = data.categories.find((c) => c.id === current);
    const q = els.search.value.trim().toLowerCase();
    const list = category.stories.filter((s) =>
      !q || `${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(q));

    els.stories.replaceChildren(...list.map((s) => {
      const when = timeAgo(s.published);
      return el("li", { className: "story" }, [
        el("a", { className: "title", href: s.link, target: "_blank", rel: "noopener noreferrer", textContent: s.title }),
        el("div", { className: "byline" }, [
          el("span", { className: "source", textContent: s.source }),
          when ? ` · ${when}` : "",
        ]),
        s.summary ? el("p", { textContent: s.summary }) : null,
      ]);
    }));
    els.empty.hidden = list.length > 0;
    els.empty.textContent = q ? "No stories match your filter." : "No stories in this category today.";
  }

  async function load() {
    try {
      const res = await fetch(`news.json?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
    } catch (err) {
      els.updated.textContent = "Couldn't load headlines. Try refreshing in a minute.";
      return;
    }

    const generated = new Date(data.generated_at);
    els.updated.textContent = `${generated.toLocaleDateString(undefined, {
      weekday: "long", month: "long", day: "numeric",
    })} · updated ${timeAgo(data.generated_at)}`;
    els.updated.title = generated.toLocaleString();

    if (data.failed_feeds && data.failed_feeds.length) {
      els.notice.textContent = `Couldn't reach today: ${data.failed_feeds.join(", ")}.`;
      els.notice.hidden = false;
    }

    const saved = storedTab();
    current = data.categories.some((c) => c.id === saved) ? saved : data.categories[0].id;
    renderTabs();
    renderStories();
  }

  els.search.addEventListener("input", () => data && renderStories());
  load();
})();
