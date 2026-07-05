import { api } from "./client";

export const getStrategies = () => api().get("/strategies").then((r) => r.data);
export const getIbkrStatus = () => api().get("/ibkr/status").then((r) => r.data);
export const getState = (id) => api().get(`/screener/${id}/state`).then((r) => r.data);
export const getVerdict = (id) => api().get(`/screener/${id}/verdict`).then((r) => r.data);
export const getSpread = (id, params = {}) =>
  api().get(`/screener/${id}/spread`, { params }).then((r) => r.data);

export const previewOrder = (body) =>
  api().post("/orders/preview", body).then((r) => r.data);
export const ticketOrder = (body) =>
  api().post("/orders/ticket", body).then((r) => r.data);

export const listAlertRules = () => api().get("/alerts").then((r) => r.data);
export const createAlertRule = (body) => api().post("/alerts", body).then((r) => r.data);
export const patchAlertRule = (id, body) =>
  api().patch(`/alerts/${id}`, body).then((r) => r.data);
export const deleteAlertRule = (id) => api().delete(`/alerts/${id}`);
export const listAlertEvents = () => api().get("/alerts/events").then((r) => r.data);
