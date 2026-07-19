/* CF Studio extension:
   1) On problem pages: adds an "⚡ Open in CF Studio" button.
   2) On submit pages opened from CF Studio (#cfstudio=... in the URL):
      fills your code and picks the language — you review and click Submit. */
(function () {
  const CF_STUDIO = "http://localhost:8000"; // change this if your CF Studio runs elsewhere (e.g. your Render URL)

  const LANG_MATCHERS = {
    cpp: [/G\+\+23/i, /G\+\+20/i, /G\+\+17/i, /G\+\+/i],
    python: [/^(?!.*PyPy).*Python 3/i, /PyPy 3/i],
    java: [/Java 2\d/i, /Java 1\d/i, /Java/i],
    kotlin: [/Kotlin 2/i, /Kotlin/i],
    rust: [/Rust.*2024/i, /Rust/i],
    go: [/^Go /i],
    javascript: [/JavaScript/i, /Node/i],
    csharp: [/C# 1\d/i, /C#(?! Mono)/, /C#/],
  };

  function banner(text) {
    const b = document.createElement("div");
    b.textContent = text;
    Object.assign(b.style, {
      position: "fixed", top: "12px", right: "12px", zIndex: 99999,
      background: "#1c2129", color: "#3fb950", border: "1px solid #3fb950",
      borderRadius: "8px", padding: "10px 14px", fontSize: "13px", fontWeight: "600",
      fontFamily: "system-ui, sans-serif", boxShadow: "0 4px 14px rgba(0,0,0,.45)",
    });
    document.body.appendChild(b);
    setTimeout(() => b.remove(), 6000);
  }

  function autofill() {
    const m = location.hash.match(/[#&]cfstudio=([^&]+)/);
    if (!m) return;
    let payload;
    try {
      payload = JSON.parse(decodeURIComponent(escape(atob(decodeURIComponent(m[1])))));
    } catch (e) { return; }
    history.replaceState(null, "", location.pathname + location.search);

    const ta = document.getElementById("sourceCodeTextarea");
    if (ta && payload.code) {
      ta.value = payload.code;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      ta.dispatchEvent(new Event("change", { bubbles: true }));
      try { // if the fancy editor toggle is on, sync it too
        const toggle = document.getElementById("toggleEditorCheckbox");
        if (toggle && toggle.checked && window.ace) {
          window.ace.edit("editor").setValue(payload.code, -1);
        }
      } catch (e) { /* textarea is what the form submits; good enough */ }
    }
    const langSel = document.querySelector("select[name=programTypeId]");
    const matchers = LANG_MATCHERS[payload.lang] || [];
    if (langSel) {
      outer: for (const rx of matchers) {
        for (const opt of langSel.options) {
          if (rx.test(opt.text)) {
            langSel.value = opt.value;
            langSel.dispatchEvent(new Event("change", { bubbles: true }));
            break outer;
          }
        }
      }
    }
    banner("✅ Code filled from CF Studio — review it, then click Submit.");
  }

  function addOpenButton() {
    const isProblemPage =
      /\/(problemset\/problem\/\d+\/[A-Z][0-9]?|(contest|gym)\/\d+\/problem\/[A-Z][0-9]?)/i.test(location.pathname);
    if (!isProblemPage || document.getElementById("cfstudio-open-btn")) return;
    const btn = document.createElement("a");
    btn.id = "cfstudio-open-btn";
    btn.textContent = "⚡ Open in CF Studio";
    btn.href = CF_STUDIO + "/import?url=" + encodeURIComponent(location.href);
    btn.target = "_blank";
    btn.rel = "noopener";
    Object.assign(btn.style, {
      position: "fixed", right: "18px", bottom: "18px", zIndex: 99999,
      background: "#1c2129", color: "#ffa116", border: "1px solid #ffa116",
      borderRadius: "8px", padding: "9px 14px", fontSize: "13px", fontWeight: "600",
      fontFamily: "system-ui, sans-serif", textDecoration: "none",
      boxShadow: "0 4px 14px rgba(0,0,0,.45)", cursor: "pointer",
    });
    btn.addEventListener("mouseenter", () => (btn.style.background = "#ffa116", btn.style.color = "#0d1117"));
    btn.addEventListener("mouseleave", () => (btn.style.background = "#1c2129", btn.style.color = "#ffa116"));
    document.body.appendChild(btn);
  }

  if (/\/submit/.test(location.pathname)) autofill();
  else addOpenButton();
})();
