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
  if (err?.response?.data?.detail) return String(err.response.data.detail);
  if (err?.response?.status) return `HTTP ${err.response.status}`;
  return err?.message || "request failed";
}

export function isAuthError(err) {
  return err?.response?.status === 401;
}
