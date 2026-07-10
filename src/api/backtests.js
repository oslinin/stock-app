import { api } from "./client";

export const compilePreview = (specId) =>
  api().get("/backtests/compile-preview", { params: { spec_id: specId } }).then((r) => r.data);
export const createBacktest = (body) => api().post("/backtests", body).then((r) => r.data);
export const getBacktest = (id) => api().get(`/backtests/${id}`).then((r) => r.data);
export const getEquity = (id) => api().get(`/backtests/${id}/equity`).then((r) => r.data);
export const getSetupSheet = (id) => api().get(`/backtests/${id}/setup-sheet`).then((r) => r.data);
export const runRobustness = (id, body) =>
  api().post(`/backtests/${id}/robustness`, body).then((r) => r.data);
export const listRobustness = (id) => api().get(`/backtests/${id}/robustness`).then((r) => r.data);

export const importOoTradeLog = (specId, file) => {
  const form = new FormData();
  form.append("file", file);
  return api()
    .post(`/backtests/import/oo?spec_id=${specId}`, form, {
      headers: { "content-type": "multipart/form-data" },
    })
    .then((r) => r.data);
};
