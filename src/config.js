// Backend connection settings. The API base can be baked in at build time
// (VITE_API_BASE) or set at runtime from the Screener settings panel; the
// token is runtime-only (localStorage) so no secret ever ships in the build.
const BASE_KEY = "vix.apiBase";
const TOKEN_KEY = "vix.apiToken";

export function getApiBase() {
  return (
    localStorage.getItem(BASE_KEY) || import.meta.env.VITE_API_BASE || ""
  ).replace(/\/+$/, "");
}

export function setApiBase(value) {
  if (value) localStorage.setItem(BASE_KEY, value.trim());
  else localStorage.removeItem(BASE_KEY);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(value) {
  if (value) localStorage.setItem(TOKEN_KEY, value.trim());
  else localStorage.removeItem(TOKEN_KEY);
}

export function hasBackend() {
  return Boolean(getApiBase());
}
