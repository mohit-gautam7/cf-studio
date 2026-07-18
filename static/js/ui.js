/* Shared UI helpers: DOM, toasts, chips, math/markdown rendering */
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of children) if (c !== null && c !== undefined) n.append(c);
  return n;
}

let _toastTimer;
function toast(msg, isErr = false) {
  let t = document.querySelector(".toast");
  if (!t) { t = el("div", { class: "toast" }); document.body.append(t); }
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

function ratingChip(r) {
  if (!r) return el("span", { class: "rt r0" }, "—");
  const cls = r >= 2400 ? "r2400" : r >= 2100 ? "r2100" : r >= 1900 ? "r1900" : r >= 1600 ? "r1600" : r >= 1400 ? "r1400" : r >= 1200 ? "r1200" : "r0";
  return el("span", { class: "rt " + cls }, "" + r);
}

function verdictChip(v) { return el("span", { class: "v " + v }, v); }

function fmtAgo(ts) {
  if (!ts) return "";
  const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

/* KaTeX auto-render over an element ($$$..$$$ CF delimiters + standard) */
function renderMath(node) {
  if (window.renderMathInElement) {
    try {
      renderMathInElement(node, {
        delimiters: [
          { left: "$$$$$$", right: "$$$$$$", display: true },
          { left: "$$$", right: "$$$", display: false },
          { left: "$$", right: "$$", display: true },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    } catch (e) { /* keep raw tex */ }
  }
}

/* markdown (notes, AI replies) — marked + math */
function renderMarkdown(target, text) {
  if (window.marked) {
    target.innerHTML = marked.parse(text || "", { breaks: true });
  } else {
    target.textContent = text || "";
  }
  renderMath(target);
}

function navBar(active) {
  const u = API.user();
  return el("div", { class: "nav" },
    el("a", { class: "logo", href: "/" }, "⚡ CF ", el("span", {}, "Studio")),
    el("a", { class: "navlink" + (active === "dash" ? " active" : ""), href: "/" }, "Dashboard"),
    el("a", { class: "navlink" + (active === "problems" ? " active" : ""), href: "/problems" }, "Problems"),
    el("div", { class: "spacer" }),
    el("span", { class: "who" }, u ? u.email : ""),
    el("button", { onclick: () => API.logout() }, "Log out"),
  );
}

function copyText(text, msg = "Copied to clipboard") {
  navigator.clipboard.writeText(text).then(() => toast(msg), () => toast("copy failed", true));
}

function busy(btn, on, labelBusy) {
  if (on) { btn.dataset.label = btn.textContent; btn.disabled = true; btn.textContent = labelBusy || "Working…"; }
  else { btn.disabled = false; btn.textContent = btn.dataset.label || btn.textContent; }
}
