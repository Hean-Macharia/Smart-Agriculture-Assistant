const BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "shambalink_access_token";
const USER_KEY = "shambalink_user";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const savedUser = () => { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; } };
export const saveSession = (token, user) => { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); };
export const clearSession = () => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); };

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", "Bearer " + token);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(BASE + path, { ...options, headers });
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = body && typeof body === "object" ? body.detail : "";
    const message = response.status === 503 && detail === "Database temporarily unavailable"
      ? "This service is temporarily unavailable. Please try again shortly."
      : Array.isArray(detail) ? detail.map((item) => item.msg).join(", ")
      : typeof detail === "string" ? detail
      : detail && typeof detail === "object" ? detail.message || "The request could not be completed."
      : "Request failed (" + response.status + ")";
    const error = new Error(message);
    error.status = response.status;
    error.response = body;
    throw error;
  }
  return body;
}
export async function products(params = {}) {
  const query = new URLSearchParams();
  Object.entries({ limit: 12, ...params }).forEach(([key, value]) => { if (value !== "" && value !== null && value !== undefined) query.set(key, String(value)); });
  return api("/marketplace/products?" + query);
}
export async function login(email, password) {
  const result = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  saveSession(result.access_token, result.user);
  return result.user;
}
export async function register(data, role) {
  await api("/auth/register/" + role, { method: "POST", body: JSON.stringify(data) });
  return login(data.email, data.password);
}
