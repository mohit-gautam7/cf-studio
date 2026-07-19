/* Problem workspace: statement, Monaco editor, tests, AI panel, stress, notes */
const PID = +location.pathname.split("/")[2];
let P = null, editor = null, aiTests = [], customTests = [], lastResult = null, noteTimer = null;
let lastStress = null;
const busyFlags = { gen: false, validate: false, stress: false };

const LANGS = [
  ["cpp", "C++17"], ["python", "Python 3"], ["java", "Java"], ["javascript", "JavaScript"],
  ["rust", "Rust"], ["go", "Go"], ["kotlin", "Kotlin"], ["csharp", "C#"],
];
const MONACO_LANG = { cpp: "cpp", python: "python", java: "java", javascript: "javascript", rust: "rust", go: "go", kotlin: "kotlin", csharp: "csharp" };
const TEMPLATES = {
  cpp: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios_base::sync_with_stdio(false);\n    cin.tie(NULL);\n\n    \n    return 0;\n}\n',
  python: 'import sys\ninput = sys.stdin.readline\n\n\n',
  java: 'import java.util.*;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n\n    }\n}\n',
  javascript: 'const data = require("fs").readFileSync(0, "utf8").split(/\\s+/);\n\n',
  rust: 'use std::io::{self, Read};\n\nfn main() {\n    let mut input = String::new();\n    io::stdin().read_to_string(&mut input).unwrap();\n\n}\n',
  go: 'package main\n\nimport (\n    "bufio"\n    "fmt"\n    "os"\n)\n\nfunc main() {\n    reader := bufio.NewReader(os.Stdin)\n    _ = reader\n    _ = fmt.Sprint\n}\n',
  kotlin: 'import java.util.Scanner\n\nfun main() {\n    val sc = Scanner(System.`in`)\n\n}\n',
  csharp: 'using System;\n\nclass Program {\n    static void Main() {\n\n    }\n}\n',
};

function lang() { return document.getElementById("lang-sel").value; }
function codeKey() { return `cfs_code_${PID}_${lang()}`; }
function getCode() { return editor ? editor.getValue() : ""; }

/* ---------------- boot ---------------- */
if (requireAuth()) boot();

async function boot() {
  const sel = document.getElementById("lang-sel");
  for (const [k, label] of LANGS) sel.append(el("option", { value: k }, label));
  sel.value = localStorage.getItem("cfs_lang") || "cpp";
  try {
    const [pr, tr] = await Promise.all([API.get("/api/problems/" + PID), API.get("/api/tests?problem_id=" + PID)]);
    P = pr.problem; aiTests = tr.tests;
  } catch (e) { document.getElementById("p-title").textContent = e.message; return; }
  customTests = JSON.parse(localStorage.getItem("cfs_custom_" + PID) || "[]");
  if (!customTests.length) customTests = [{ input: "", expected: "" }];

  document.title = P.title + " — CF Studio";
  document.getElementById("p-title").textContent = P.title;
  document.getElementById("p-rating").replaceWith(ratingChip(P.rating));
  document.getElementById("p-limits").textContent = ` ${P.time_limit_ms / 1000}s · ${P.memory_limit_mb}MB `;
  if (P.url) document.getElementById("p-cf-link").append(el("a", { href: P.url, target: "_blank", class: "small" }, "open on CF ↗"));
  const bm = document.getElementById("bm-btn");
  bm.classList.toggle("on", !!P.bookmark);
  bm.onclick = async () => {
    const r = await API.post("/api/bookmarks/toggle", { problem_id: PID });
    bm.classList.toggle("on", !!r.bookmark);
    toast(r.bookmark ? "bookmarked" : "bookmark removed");
  };

  initLeftTabs(); initBottomTabs(); initAI(); initEditor(); initSplitter(); initResizers();

  document.getElementById("copy-btn").onclick = () =>
    copyText(getCode(), "Code copied — paste it into the Codeforces submit page");
  document.getElementById("run-btn").onclick = () => runTests("samples");
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runTests("samples"); }
  });
}

/* ---------------- editor ---------------- */
function initEditor() {
  require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
  require(["vs/editor/editor.main"], () => {
    monaco.editor.defineTheme("cf-dark", {
      base: "vs-dark", inherit: true,
      rules: [], colors: { "editor.background": "#0d1117", "editorGutter.background": "#0d1117" },
    });
    editor = monaco.editor.create(document.getElementById("editor"), {
      value: localStorage.getItem(codeKey()) || TEMPLATES[lang()] || "",
      language: MONACO_LANG[lang()], theme: "cf-dark",
      fontSize: 14, minimap: { enabled: false }, automaticLayout: true,
      scrollBeyondLastLine: false, padding: { top: 10 },
    });
    editor.onDidChangeModelContent(() => localStorage.setItem(codeKey(), getCode()));
    const langSel = document.getElementById("lang-sel");
    langSel.addEventListener("change", () => {
      localStorage.setItem("cfs_lang", lang());
      monaco.editor.setModelLanguage(editor.getModel(), MONACO_LANG[lang()]);
      editor.setValue(localStorage.getItem(codeKey()) || TEMPLATES[lang()] || "");
    });
    document.getElementById("theme-sel").addEventListener("change", (e) => monaco.editor.setTheme(e.target.value));
  });
}

function initSplitter() {
  const div = document.getElementById("divider"), left = document.getElementById("left-pane");
  let drag = false;
  div.addEventListener("mousedown", () => { drag = true; document.body.style.userSelect = "none"; });
  window.addEventListener("mouseup", () => { drag = false; document.body.style.userSelect = ""; });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const pct = Math.min(70, Math.max(20, (e.clientX / window.innerWidth) * 100));
    left.style.width = pct + "%";
  });
}

function initResizers() {
  // bottom panel height
  const bottom = document.getElementById("bottom");
  const hDiv = document.getElementById("bottom-divider");
  const savedH = +localStorage.getItem("cfs_bottom_h");
  if (savedH >= 120) bottom.style.height = savedH + "px";
  let dragH = false;
  if (hDiv) {
    hDiv.addEventListener("mousedown", () => { dragH = true; document.body.style.userSelect = "none"; });
    window.addEventListener("mousemove", (e) => {
      if (!dragH) return;
      const h = Math.min(window.innerHeight * 0.65, Math.max(120, window.innerHeight - e.clientY));
      bottom.classList.remove("collapsed");
      bottom.style.height = h + "px";
      localStorage.setItem("cfs_bottom_h", Math.round(h));
    });
  }
  // AI drawer width
  const ai = document.getElementById("ai-pane");
  const aiHandle = document.getElementById("ai-handle");
  const savedW = +localStorage.getItem("cfs_ai_w");
  if (savedW >= 280) ai.style.width = savedW + "px";
  let dragW = false;
  if (aiHandle) {
    aiHandle.addEventListener("mousedown", () => { dragW = true; document.body.style.userSelect = "none"; });
    window.addEventListener("mousemove", (e) => {
      if (!dragW) return;
      const w = Math.min(680, Math.max(280, window.innerWidth - e.clientX));
      ai.style.width = w + "px";
      localStorage.setItem("cfs_ai_w", Math.round(w));
    });
  }
  window.addEventListener("mouseup", () => { dragH = dragW = false; document.body.style.userSelect = ""; });
}

/* ---------------- left: statement / notes / submissions ---------------- */
let leftTab = "problem";
function initLeftTabs() {
  const tabs = document.getElementById("left-tabs");
  tabs.innerHTML = "";
  for (const [id, label] of [["problem", "Problem"], ["notes", "Notes"], ["subs", "Submissions"]]) {
    tabs.append(el("button", { class: "tab" + (leftTab === id ? " active" : ""), onclick: () => { leftTab = id; initLeftTabs(); } }, label));
  }
  const body = document.getElementById("left-body");
  body.innerHTML = "";
  if (leftTab === "problem") drawStatement(body);
  else if (leftTab === "notes") drawNotes(body);
  else drawSubmissions(body);
}

function drawStatement(body) {
  const s = el("div", { class: "statement" });
  s.append(el("div", { html: P.statement_html }));
  if (P.input_spec_html) s.append(el("div", { class: "sec-title" }, "Input"), el("div", { class: "io", html: P.input_spec_html }));
  if (P.output_spec_html) s.append(el("div", { class: "sec-title" }, "Output"), el("div", { class: "io", html: P.output_spec_html }));
  if ((P.samples || []).length) {
    s.append(el("div", { class: "sec-title" }, "Examples"));
    P.samples.forEach((smp, i) => {
      s.append(el("div", { class: "sample" },
        el("div", { class: "cap" }, el("span", {}, "Input " + (i + 1)),
          el("button", { class: "copy-mini", onclick: () => copyText(smp.input) }, "copy")),
        el("pre", {}, smp.input),
        el("div", { class: "cap" }, el("span", {}, "Output " + (i + 1))),
        el("pre", {}, smp.output)));
    });
  }
  if (P.note_html) s.append(el("div", { class: "sec-title" }, "Note"), el("div", { html: P.note_html }));
  if ((P.tags || []).length) {
    s.append(el("div", { style: "margin-top:14px" }, ...P.tags.map(t => el("span", { class: "tag" }, t))));
  }
  body.append(s);
  renderMath(s);
}

async function drawNotes(body) {
  const ta = el("textarea", { style: "width:100%;min-height:220px", placeholder: "Personal notes — markdown and $$$\\LaTeX$$$ supported. Autosaves." });
  const preview = el("div", { class: "statement", style: "margin-top:10px" });
  const status = el("span", { class: "muted small" }, "");
  try { ta.value = (await API.get("/api/notes?problem_id=" + PID)).content; } catch (e) { /* new note */ }
  const save = async () => {
    try { await API.post("/api/notes", { problem_id: PID, content: ta.value }); status.textContent = "saved"; }
    catch (e) { status.textContent = "save failed"; }
  };
  ta.addEventListener("input", () => {
    status.textContent = "…";
    clearTimeout(noteTimer); noteTimer = setTimeout(save, 1200);
    renderMarkdown(preview, ta.value);
  });
  body.append(el("div", { class: "row" }, el("b", {}, "Notes"), status), ta,
    el("div", { class: "kv" }, "preview"), preview);
  renderMarkdown(preview, ta.value);
}

async function drawSubmissions(body) {
  let data;
  try { data = await API.get("/api/submissions?problem_id=" + PID); } catch (e) { body.textContent = e.message; return; }
  body.append(el("b", {}, "Local runs"));
  const t = el("table", { class: "list" },
    el("thead", {}, el("tr", {}, el("th", {}, "when"), el("th", {}, "kind"), el("th", {}, "lang"), el("th", {}, "verdict"), el("th", {}, "tests"))));
  const tb = el("tbody");
  for (const r of data.runs) {
    tb.append(el("tr", {},
      el("td", { class: "muted small" }, fmtAgo(r.created_at)), el("td", {}, r.kind), el("td", {}, r.language),
      el("td", {}, verdictChip(r.verdict)), el("td", { class: "muted small" }, `${r.passed}/${r.total}`)));
  }
  if (!data.runs.length) tb.append(el("tr", {}, el("td", { colspan: 5, class: "muted" }, "no runs yet")));
  t.append(tb); body.append(t);

  body.append(el("div", { style: "margin-top:14px" }, el("b", {}, "Codeforces verdicts ")));
  const impBtn = el("button", { class: "small" }, "Import from CF (by handle)");
  impBtn.onclick = async () => {
    busy(impBtn, true, "Importing…");
    try { const r = await API.post("/api/cf/verdicts", {}); toast("imported " + r.imported); leftTab = "subs"; initLeftTabs(); }
    catch (e) { toast(e.message, true); busy(impBtn, false); }
  };
  body.append(impBtn);
  const t2 = el("table", { class: "list" }); const tb2 = el("tbody");
  for (const v of data.codeforces) {
    tb2.append(el("tr", {}, el("td", { class: "muted small" }, fmtAgo(v.submitted_at)),
      el("td", {}, v.language), el("td", {}, verdictChip(v.verdict === "OK" ? "OK" : v.verdict))));
  }
  if (!data.codeforces.length) tb2.append(el("tr", {}, el("td", { colspan: 3, class: "muted" }, "none imported for this problem")));
  t2.append(tb2); body.append(t2);
}

/* ---------------- bottom: tests ---------------- */
let bottomTab = "samples";
function initBottomTabs() {
  const tabs = document.getElementById("bottom-tabs");
  tabs.innerHTML = "";
  const defs = [["samples", "Samples"], ["custom", "Custom"],
    ["ai", `AI Tests (${aiTests.length})` + (busyFlags.gen || busyFlags.validate ? " ⏳" : "")],
    ["results", "Results"], ["stress", "Stress" + (busyFlags.stress ? " ⏳" : "")]];
  for (const [id, label] of defs) {
    tabs.append(el("button", { class: "tab" + (bottomTab === id ? " active" : ""), onclick: () => { bottomTab = id; initBottomTabs(); } }, label));
  }
  const collapse = el("button", { class: "tab", style: "margin-left:auto", onclick: () => document.getElementById("bottom").classList.toggle("collapsed") }, "▁▔");
  tabs.append(collapse);
  const body = document.getElementById("bottom-body");
  body.innerHTML = "";
  ({ samples: drawSamples, custom: drawCustom, ai: drawAITests, results: drawResults, stress: drawStress })[bottomTab](body);
}

function drawSamples(body) {
  const btn = el("button", { class: "primary", onclick: () => runTests("samples") }, "▶ Run samples");
  body.append(el("div", { class: "row", style: "margin-bottom:10px" }, btn,
    el("span", { class: "muted small" }, "verdicts computed against expected output")));
  (P.samples || []).forEach((s, i) => {
    body.append(el("div", { class: "tcase" },
      el("div", { class: "thead" }, "sample " + (i + 1)),
      el("div", { class: "io-grid" },
        el("div", {}, el("div", { class: "lab" }, "input"), el("pre", { style: "margin:4px 8px" }, s.input)),
        el("div", {}, el("div", { class: "lab" }, "expected"), el("pre", { style: "margin:4px 8px" }, s.output)))));
  });
}

function saveCustom() { localStorage.setItem("cfs_custom_" + PID, JSON.stringify(customTests)); }

function drawCustom(body) {
  const run = el("button", { class: "primary", onclick: () => runTests("custom") }, "▶ Run custom");
  const add = el("button", { onclick: () => { customTests.push({ input: "", expected: "" }); saveCustom(); initBottomTabs(); } }, "+ Add case");
  body.append(el("div", { class: "row", style: "margin-bottom:10px" }, run, add,
    el("span", { class: "muted small" }, "expected output is optional — leave blank to just see your output")));
  customTests.forEach((t, i) => {
    const inTa = el("textarea", { placeholder: "input" }, t.input || "");
    const exTa = el("textarea", { placeholder: "expected output (optional)" }, t.expected || "");
    inTa.addEventListener("input", () => { t.input = inTa.value; saveCustom(); });
    exTa.addEventListener("input", () => { t.expected = exTa.value; saveCustom(); });
    body.append(el("div", { class: "tcase" },
      el("div", { class: "thead" }, "case " + (i + 1), el("span", { style: "flex:1" }),
        el("button", { class: "copy-mini", onclick: () => { customTests.splice(i, 1); saveCustom(); initBottomTabs(); } }, "remove")),
      el("div", { class: "io-grid" }, el("div", {}, inTa), el("div", {}, exTa))));
  });
}

function drawAITests(body) {
  const gen = el("button", { class: "accent" }, busyFlags.gen ? "Generating…" : "✨ Generate tests");
  const validate = el("button", {}, busyFlags.validate ? "Validating…" : "Validate with brute force");
  gen.disabled = busyFlags.gen;
  validate.disabled = busyFlags.validate;
  const run = el("button", { class: "primary", onclick: () => runTests("ai") }, "▶ Run AI tests");
  const count = el("select", {}, ...[6, 8, 12, 16].map(n => el("option", { value: n }, n + " tests")));
  count.value = "8";
  gen.onclick = async () => {
    if (busyFlags.gen) return;
    busyFlags.gen = true; initBottomTabs();
    try {
      const r = await API.post("/api/tests/generate", { problem_id: PID, count: +count.value, code: getCode(), language: lang() });
      aiTests = r.tests; toast("generated " + aiTests.length + " tests");
    } catch (e) { toast(e.message, true); }
    finally { busyFlags.gen = false; initBottomTabs(); }
  };
  validate.onclick = async () => {
    if (busyFlags.validate) return;
    busyFlags.validate = true; initBottomTabs();
    try {
      const r = await API.post("/api/tests/validate", { problem_id: PID });
      aiTests = r.tests; toast(`validated ${r.validated}, dropped ${r.dropped}`);
    } catch (e) { toast(e.message, true); }
    finally { busyFlags.validate = false; initBottomTabs(); }
  };
  body.append(el("div", { class: "row", style: "margin-bottom:10px" }, count, gen, validate,
    aiTests.length ? run : "", (busyFlags.gen || busyFlags.validate) ? el("span", { class: "spin" }) : ""),
    el("div", { class: "muted small", style: "margin-bottom:8px" },
      "AI-computed expected outputs are guesses until validated against a correct (brute force / reference) solution."));
  for (const t of aiTests) {
    body.append(el("div", { class: "tcase" },
      el("div", { class: "thead" },
        el("span", { class: "badge" + (t.validated ? " ok" : "") }, t.validated ? "validated" : "unverified"),
        el("span", { class: "muted small", style: "flex:1" }, t.reason || "")),
      el("div", { class: "io-grid" },
        el("div", {}, el("div", { class: "lab" }, "input"), el("pre", { style: "margin:4px 8px" }, t.input)),
        el("div", {}, el("div", { class: "lab" }, "expected"), el("pre", { style: "margin:4px 8px" }, t.expected || "—")))));
  }
  if (!aiTests.length) body.append(el("div", { class: "muted" }, "No AI tests yet. Generate boundary, overflow, corner and hack-style cases from the constraints."));
}

async function runTests(kind) {
  if (!editor) return toast("editor still loading", true);
  const btn = document.getElementById("run-btn");
  busy(btn, true, "Running…");
  toast("running on judge…");
  try {
    const body = { problem_id: PID, language: lang(), code: getCode(), kind };
    if (kind === "custom") body.tests = customTests.filter(t => (t.input || "").trim());
    const r = await API.post("/api/run", body);
    lastResult = { ...r.result, kind };
    bottomTab = "results"; initBottomTabs();
    document.getElementById("bottom").classList.remove("collapsed");
    const v = r.result.verdict;
    toast(`${v} — ${r.result.passed}/${r.result.total} passed`, !(v === "OK" || v === "RUN"));
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
}

function drawResults(body) {
  if (!lastResult) { body.append(el("div", { class: "muted" }, "Run your code to see verdicts here.")); return; }
  const head = el("div", { class: "row", style: "margin-bottom:10px" },
    verdictChip(lastResult.verdict),
    el("b", {}, `${lastResult.passed}/${lastResult.total} passed`),
    el("span", { class: "muted small" }, "(" + lastResult.kind + ")"));
  if (!["OK", "RUN"].includes(lastResult.verdict)) {
    head.append(el("button", { class: "accent", onclick: () => { openAI(); aiFindBug(); } }, "🔎 Find bug with AI"));
  }
  body.append(head);
  for (const r of lastResult.results || []) {
    const row = el("div", { class: "result-row" });
    const rb = el("div", { class: "rbody" });
    if (r.message) rb.append(el("div", { class: "kv" }, "message"), el("pre", {}, r.message));
    if (r.input !== undefined) rb.append(el("div", { class: "kv" }, "input"), el("pre", {}, r.input || ""));
    if (r.expected) rb.append(el("div", { class: "kv" }, "expected"), el("pre", {}, r.expected));
    if (r.stdout !== undefined) rb.append(el("div", { class: "kv" }, "your output"), el("pre", {}, r.stdout || ""));
    if (r.stderr) rb.append(el("div", { class: "kv" }, "stderr"), el("pre", {}, r.stderr));
    row.append(el("div", {
      class: "rhead", onclick: () => row.classList.toggle("open"),
    }, el("b", {}, "#" + (r.i + 1)), verdictChip(r.verdict), el("span", { class: "muted small" }, r.time_ms != null ? r.time_ms + " ms" : "")), rb);
    body.append(row);
  }
}

function drawStress(body) {
  const iters = el("select", {}, ...[10, 20, 30, 50].map(n => el("option", { value: n }, n + " iterations")));
  iters.value = "20";
  const btn = el("button", { class: "accent" }, busyFlags.stress ? "Stress testing…" : "⚔ Run stress test");
  btn.disabled = busyFlags.stress;
  const out = el("div", { class: "stress-box", style: "margin-top:10px" });
  body.append(el("div", { class: "row" }, iters, btn,
    el("span", { class: "muted small" }, P.has_reference ? "brute force: reference solution" : "brute force: AI-generated")), out);
  const render = () => {
    out.innerHTML = "";
    if (busyFlags.stress) {
      out.append(el("div", {}, el("span", { class: "spin" }), " generating tests, comparing against brute force — this can take a minute… (you can switch tabs, it keeps running)"));
      return;
    }
    const s = lastStress;
    if (!s) return;
    if (s.status === "passed") {
      out.append(el("div", {}, verdictChip("OK"), ` matched the brute force on all ${s.iterations} random tests (${s.brute_source} brute).`));
    } else if (s.status === "mismatch") {
      out.append(el("div", { class: "row" }, verdictChip(s.kind || "WA"), el("b", {}, `mismatch on iteration ${s.iteration}`),
        el("button", { onclick: () => { customTests.unshift({ input: s.input, expected: (s.expected || "").trim() }); saveCustom(); toast("failing case added to Custom tests"); } }, "→ add to Custom")),
        el("div", { class: "kv" }, "input"), el("pre", {}, s.input || ""),
        el("div", { class: "kv" }, "expected (brute)"), el("pre", {}, s.expected || ""),
        el("div", { class: "kv" }, "your output"), el("pre", {}, s.got || ""));
    } else if (s.status === "error") {
      out.append(el("div", { class: "muted" }, "stress failed: " + s.message));
    } else {
      out.append(el("div", {}, verdictChip("JUDGE_ERROR"), " " + (s.status || "") + ": "), el("pre", {}, s.message || ""));
    }
  };
  render();
  btn.onclick = async () => {
    if (busyFlags.stress) return;
    busyFlags.stress = true; lastStress = null; initBottomTabs();
    try {
      const { stress: s } = await API.post("/api/stress", { problem_id: PID, code: getCode(), language: lang(), iterations: +iters.value });
      lastStress = s;
    } catch (e) { lastStress = { status: "error", message: e.message }; }
    finally { busyFlags.stress = false; initBottomTabs(); }
  };
}

/* ---------------- AI panel ---------------- */
function openAI() { document.getElementById("ai-pane").classList.add("open"); }

function initAI() {
  document.getElementById("ai-toggle").onclick = () => document.getElementById("ai-pane").classList.toggle("open");
  const actions = document.getElementById("ai-actions");
  const hintLevel = el("select", {}, ...[1, 2, 3, 4, 5].map(n => el("option", { value: n }, "Hint L" + n)));
  actions.append(
    el("button", { onclick: () => aiAction("explain", "Explain this problem", (r) => r.explanation, { audience: "competitive programmer" }) }, "📖 Explain"),
    hintLevel,
    el("button", { onclick: () => aiHint(+hintLevel.value) }, "💡 Get hint"),
    el("button", { onclick: aiFindBug }, "🐞 Find bug"),
    el("button", { onclick: () => aiAction("complexity", "Estimate complexity of my code", (r) => r.analysis, { code: getCode(), language: lang() }) }, "⏱ Complexity"),
  );
  const send = document.getElementById("ai-send"), ta = document.getElementById("ai-text");
  send.onclick = sendChat;
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
  loadChatHistory();
}

function aiMsg(role, content, pending = false) {
  const log = document.getElementById("ai-log");
  const bubble = el("div", { class: "bubble" });
  if (pending) bubble.append(el("span", { class: "spin" }));
  else renderMarkdown(bubble, content);
  const m = el("div", { class: "msg " + role }, el("div", { class: "who" }, role === "user" ? "you" : "✨ AI"), bubble);
  log.append(m); log.scrollTop = log.scrollHeight;
  return bubble;
}

async function loadChatHistory() {
  try {
    const { messages } = await API.get("/api/ai/chat?problem_id=" + PID);
    for (const m of messages) aiMsg(m.role === "user" ? "user" : "assistant", m.content);
    if (!messages.length) aiMsg("assistant", "Hi! I can **explain** the problem, give **progressive hints**, **generate tests**, **find bugs** and **estimate complexity**. I always see the statement, constraints and your current code.");
  } catch (e) { /* ignore */ }
}

async function sendChat() {
  const ta = document.getElementById("ai-text");
  const text = ta.value.trim();
  if (!text) return;
  ta.value = "";
  openAI(); aiMsg("user", text);
  const bubble = aiMsg("assistant", "", true);
  try {
    const r = await API.post("/api/ai/chat", { problem_id: PID, message: text, code: getCode(), language: lang() });
    renderMarkdown(bubble, r.reply);
  } catch (e) { renderMarkdown(bubble, "⚠️ " + e.message); }
  document.getElementById("ai-log").scrollTop = 1e9;
}

async function aiAction(endpoint, label, pick, extra) {
  openAI(); aiMsg("user", label);
  const bubble = aiMsg("assistant", "", true);
  try {
    const r = await API.post("/api/ai/" + endpoint, { problem_id: PID, ...extra });
    renderMarkdown(bubble, pick(r));
  } catch (e) { renderMarkdown(bubble, "⚠️ " + e.message); }
}

async function aiHint(level) {
  openAI(); aiMsg("user", `Give me hint level ${level}/5`);
  const bubble = aiMsg("assistant", "", true);
  try {
    const r = await API.post("/api/ai/hint", { problem_id: PID, level, code: getCode(), language: lang() });
    renderMarkdown(bubble, r.hint);
  } catch (e) { renderMarkdown(bubble, "⚠️ " + e.message); }
}

async function aiFindBug() {
  openAI(); aiMsg("user", "Find the bug in my current code");
  const bubble = aiMsg("assistant", "", true);
  try {
    const r = await API.post("/api/ai/find_bug", { problem_id: PID, code: getCode(), language: lang() });
    renderMarkdown(bubble, r.analysis);
  } catch (e) { renderMarkdown(bubble, "⚠️ " + e.message); }
}
