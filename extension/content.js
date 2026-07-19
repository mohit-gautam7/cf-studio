/* Adds an "Open in CF Studio" button on Codeforces problem pages. */
(function () {
  const CF_STUDIO = "http://localhost:8000"; // change if you run on another port

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
})();
