const BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const USER_KEY = "shambalink_user";
const LEGACY_TOKEN_KEY = "shambalink_access_token";
let accessToken = null;
try { localStorage.removeItem(LEGACY_TOKEN_KEY); } catch {}
export const getToken = () => accessToken;
export const savedUser = () => { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; } };
export const saveSession = (token, user) => { accessToken = token; localStorage.removeItem(LEGACY_TOKEN_KEY); localStorage.setItem(USER_KEY, JSON.stringify(user)); };
export const clearSession = () => { accessToken = null; localStorage.removeItem(LEGACY_TOKEN_KEY); localStorage.removeItem(USER_KEY); };

function notifyConnectivity(online) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("shambalink:connectivity", { detail: { online } }));
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", "Bearer " + token);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response;
  try {
    response = await fetch(BASE + path, { ...options, headers });
    notifyConnectivity(true);
  } catch (error) {
    notifyConnectivity(false);
    throw error;
  }
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
