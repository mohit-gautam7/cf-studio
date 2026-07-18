/* API client + auth/session helpers */
const API = {
  token() { return localStorage.getItem("cfs_token"); },
  user() { try { return JSON.parse(localStorage.getItem("cfs_user") || "null"); } catch { return null; } },
  setSession(tok, user) { localStorage.setItem("cfs_token", tok); localStorage.setItem("cfs_user", JSON.stringify(user)); },
  logout() { localStorage.removeItem("cfs_token"); localStorage.removeItem("cfs_user"); location.href = "/login"; },

  async call(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (this.token()) headers["Authorization"] = "Bearer " + this.token();
    const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    let data = {};
    try { data = await res.json(); } catch { /* empty */ }
    if (res.status === 401 && !path.startsWith("/api/login") && !path.startsWith("/api/register")) {
      this.logout(); throw new Error("login required");
    }
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    return data;
  },
  get(path) { return this.call("GET", path); },
  post(path, body) { return this.call("POST", path, body || {}); },
};

function requireAuth() {
  if (!API.token()) { location.href = "/login"; return false; }
  return true;
}
