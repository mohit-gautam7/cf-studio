/* Problem list: filter, search, bookmark, import */
let ALL = [];

if (requireAuth()) {
  document.getElementById("nav").replaceWith(navBar("problems"));
  init();
}

async function init() {
  for (const r of [800, 1000, 1200, 1400, 1600, 1900, 2100, 2400]) {
    document.getElementById("min-r").append(el("option", { value: r }, "≥ " + r));
    document.getElementById("max-r").append(el("option", { value: r }, "≤ " + r));
  }
  document.getElementById("q").addEventListener("input", draw);
  document.getElementById("min-r").addEventListener("change", draw);
  document.getElementById("max-r").addEventListener("change", draw);
  const btn = document.getElementById("imp-btn"), url = document.getElementById("imp-url");
  btn.onclick = async () => {
    if (!url.value.trim()) return toast("paste a Codeforces problem URL", true);
    busy(btn, true, "Fetching…");
    try {
      const r = await API.post("/api/problems/import", { url: url.value.trim() });
      location.href = "/p/" + r.problem_id;
    } catch (e) { toast(e.message, true); busy(btn, false); }
  };
  await load();
}

async function load() {
  try { ALL = (await API.get("/api/problems")).problems; draw(); }
  catch (e) { toast(e.message, true); }
}

function draw() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const minR = +document.getElementById("min-r").value || 0;
  const maxR = +document.getElementById("max-r").value || 9999;
  const tb = document.querySelector("#tbl tbody");
  tb.innerHTML = "";
  for (const p of ALL) {
    const tags = (p.tags || []).join(" ");
    if (q && !(p.title.toLowerCase().includes(q) || tags.toLowerCase().includes(q))) continue;
    const r = p.rating || 0;
    if ((minR && r < minR) || (maxR !== 9999 && r > maxR)) continue;
    const star = el("button", { class: "star" + (p.bookmark ? " on" : ""), title: "bookmark" }, "★");
    star.onclick = async () => {
      try {
        const res = await API.post("/api/bookmarks/toggle", { problem_id: p.id });
        p.bookmark = res.bookmark; star.className = "star" + (p.bookmark ? " on" : "");
      } catch (e) { toast(e.message, true); }
    };
    tb.append(el("tr", {},
      el("td", {}, el("span", { class: "dot " + (p.status.solved ? "solved" : p.status.attempts ? "tried" : "") })),
      el("td", {}, el("a", { href: "/p/" + p.id }, p.title),
        p.source === "cf" ? el("span", { class: "muted small" }, "  " + p.cf_contest_id + p.cf_index) : ""),
      el("td", {}, ratingChip(p.rating)),
      el("td", {}, ...(p.tags || []).slice(0, 4).map(t => el("span", { class: "tag" }, t))),
      el("td", { class: "muted small" }, p.status.attempts ? p.status.attempts + "×" : "—"),
      el("td", {}, star),
    ));
  }
  if (!tb.children.length) tb.append(el("tr", {}, el("td", { colspan: "6", class: "muted", style: "text-align:center;padding:24px" }, "Nothing matches — adjust filters or import a problem.")));
}
