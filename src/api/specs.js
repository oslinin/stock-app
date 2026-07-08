import { api } from "./client";

export const listSpecs = (params = {}) =>
  api().get("/specs", { params }).then((r) => r.data);
export const getSpec = (id) => api().get(`/specs/${id}`).then((r) => r.data);
export const createSpec = (body) => api().post("/specs", body).then((r) => r.data);
export const updateSpec = (id, body) =>
  api().put(`/specs/${id}`, body).then((r) => r.data);
export const approveSpec = (id) =>
  api().post(`/specs/${id}/approve`).then((r) => r.data);
export const getSpecDoc = (id, params = {}) =>
  api().get(`/specs/${id}/doc`, { params }).then((r) => r.data);
export const getSpecPayoff = (id, params = {}) =>
  api().get(`/specs/${id}/payoff`, { params }).then((r) => r.data);
