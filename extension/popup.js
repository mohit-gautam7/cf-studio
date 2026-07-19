const HOSTED = "https://cf-studio.onrender.com";
const LOCAL = "http://localhost:8000";

const radios = [...document.querySelectorAll('input[name=mode]')];
const customInput = document.getElementById("custom-url");
const savedNote = document.getElementById("saved");

function save() {
  const mode = radios.find(r => r.checked)?.value || "hosted";
  const server = mode === "hosted" ? HOSTED : mode === "local" ? LOCAL
    : (customInput.value.trim().replace(/\/+$/, "") || HOSTED);
  chrome.storage.sync.set({ server }, () => {
    savedNote.textContent = "saved ✓  (" + server + ")";
    setTimeout(() => (savedNote.textContent = ""), 2500);
  });
}

chrome.storage.sync.get({ server: HOSTED }, ({ server }) => {
  const mode = server === HOSTED ? "hosted" : server === LOCAL ? "local" : "custom";
  radios.find(r => r.value === mode).checked = true;
  if (mode === "custom") customInput.value = server;
});

radios.forEach(r => r.addEventListener("change", save));
customInput.addEventListener("input", () => {
  radios.find(r => r.value === "custom").checked = true;
  save();
});
