import axios from "axios";
import { getApiBase, getToken } from "../config";

export function api() {
  const instance = axios.create({ baseURL: getApiBase(), timeout: 45000 });
  instance.interceptors.request.use((cfg) => {
    const token = getToken();
    if (token) cfg.headers.Authorization = `Bearer ${token}`;
    return cfg;
  });
  return instance;
}

export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI's own validation errors are an array of {loc, msg, type};
  // route-level HTTPException(422, {...}) payloads are a plain object —
  // either way, String(detail) would just print "[object Object]".
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || JSON.stringify(d)).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  if (err?.response?.status) return `HTTP ${err.response.status}`;
  return err?.message || "request failed";
}

export function isAuthError(err) {
  return err?.response?.status === 401;
}
