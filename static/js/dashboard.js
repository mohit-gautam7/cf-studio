/* Dashboard: stats, recent, weak topics, bookmarks, rating, import */
if (requireAuth()) {
  document.getElementById("nav").replaceWith(navBar("dash"));
  loadDashboard();
  wireImport(document.getElementById("imp-url"), document.getElementById("imp-btn"));
  loadRating();
}

async function loadDashboard() {
  try {
    const d = await API.get("/api/dashboard");
    const stats = document.getElementById("stats");
    stats.innerHTML = "";
    stats.append(
      el("div", { class: "card" }, el("h3", {}, "Daily streak"), el("div", { class: "stat" }, "🔥 " + d.streak, el("small", {}, d.streak === 1 ? "day" : "days"))),
      el("div", { class: "card" }, el("h3", {}, "Solved"), el("div", { class: "stat" }, "✅ " + d.solved, el("small", {}, "problems"))),
      el("div", { class: "card" }, el("h3", {}, "Attempted"), el("div", { class: "stat" }, "🧩 " + d.attempted, el("small", {}, "problems"))),
    );
    const rec = document.getElementById("recent");
    rec.innerHTML = "";
    if (!d.recent.length) rec.textContent = "Run some code and your recent problems appear here.";
    for (const r of d.recent) {
      rec.append(el("div", { class: "row", style: "padding:5px 0" },
        el("span", { class: "dot " + (r.solved ? "solved" : "tried") }),
        el("a", { href: "/p/" + r.id, style: "flex:1" }, r.title),
        ratingChip(r.rating),
        el("span", { class: "muted small" }, fmtAgo(r.last_at))));
    }
    const top = document.getElementById("topics");
    top.innerHTML = "";
    if (!d.topics.length) top.textContent = "Solve a few problems to see your per-topic accuracy.";
    for (const t of d.topics) {
      top.append(el("div", { style: "margin-bottom:8px" },
        el("div", { class: "row small" }, el("span", { style: "flex:1" }, t.tag),
          el("span", { class: "muted" }, `${t.solved}/${t.attempted} · ${t.rate}%`)),
        el("div", { class: "bar" }, el("div", { style: "width:" + t.rate + "%" }))));
    }
    const bm = document.getElementById("bookmarks");
    bm.innerHTML = "";
    if (!d.bookmarks.length) bm.textContent = "Star problems in the workspace to collect them here.";
    for (const b of d.bookmarks) {
      bm.append(el("div", { class: "row", style: "padding:5px 0" },
        el("span", { class: "star on" }, "★"),
        el("a", { href: "/p/" + b.problem_id, style: "flex:1" }, b.title),
        el("span", { class: "tag" }, b.label), ratingChip(b.rating)));
    }
  } catch (e) { toast(e.message, true); }
}

async function loadRating() {
  const box = document.getElementById("rating");
  const u = API.user();
  box.innerHTML = "";
  const handleInput = el("input", { placeholder: "your CF handle", value: (u && u.handle) || "", style: "width:150px" });
  const saveBtn = el("button", {}, "Save");
  const importBtn = el("button", { class: "accent" }, "Import verdicts");
  const chart = el("div", { style: "margin-top:10px" });
  saveBtn.onclick = async () => {
    busy(saveBtn, true);
    try {
      const r = await API.post("/api/me", { handle: handleInput.value.trim() });
      const user = API.user(); user.handle = r.handle; API.setSession(API.token(), user);
      toast("handle saved"); drawChart();
    } catch (e) { toast(e.message, true); } finally { busy(saveBtn, false); }
  };
  importBtn.onclick = async () => {
    busy(importBtn, true, "Importing…");
    try {
      const r = await API.post("/api/cf/verdicts", { handle: handleInput.value.trim() });
      toast("imported " + r.imported + " verdicts from Codeforces"); loadDashboard();
    } catch (e) { toast(e.message, true); } finally { busy(importBtn, false); }
  };
  box.append(el("div", { class: "row" }, handleInput, saveBtn, importBtn), chart);
  async function drawChart() {
    chart.innerHTML = "";
    const h = handleInput.value.trim();
    if (!h) { chart.append(el("div", { class: "muted small" }, "Set your handle to see your rating graph.")); return; }
    try {
      const { rating } = await API.get("/api/cf/rating?handle=" + encodeURIComponent(h));
      if (!rating.length) { chart.append(el("div", { class: "muted small" }, "No rated contests yet.")); return; }
      const vals = rating.map(r => r.new);
      const min = Math.min(...vals), max = Math.max(...vals), W = 460, H = 90;
      const pts = vals.map((v, i) => {
        const x = vals.length === 1 ? W / 2 : (i / (vals.length - 1)) * (W - 10) + 5;
        const y = H - 8 - (max === min ? 0.5 : (v - min) / (max - min)) * (H - 20);
        return x.toFixed(1) + "," + y.toFixed(1);
      }).join(" ");
      chart.innerHTML =
        `<svg viewBox="0 0 ${W} ${H}" style="width:100%"><polyline fill="none" stroke="#ffa116" stroke-width="2" points="${pts}"/></svg>` +
        `<div class="small muted">current <b style="color:var(--accent)">${vals[vals.length - 1]}</b> · peak ${max} · ${rating.length} contests</div>`;
    } catch (e) { chart.append(el("div", { class: "muted small" }, e.message)); }
  }
  drawChart();
}

function wireImport(input, btn) {
  btn.onclick = async () => {
    if (!input.value.trim()) return toast("paste a Codeforces problem URL", true);
    busy(btn, true, "Fetching…");
    try {
      const r = await API.post("/api/problems/import", { url: input.value.trim() });
      toast(r.created ? "problem imported" : "already imported — opening");
      location.href = "/p/" + r.problem_id;
    } catch (e) { toast(e.message, true); busy(btn, false); }
  };
}
