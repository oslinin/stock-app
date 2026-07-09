import { api } from "./client";

export const listPositions = (groupBy) =>
  api()
    .get("/portfolio/positions", { params: groupBy ? { group_by: groupBy } : {} })
    .then((r) => r.data);
export const getSummary = () => api().get("/portfolio/summary").then((r) => r.data);
export const getRisk = () => api().get("/portfolio/risk").then((r) => r.data);
export const getBeta = (symbol) =>
  api().get("/portfolio/beta", { params: { symbol } }).then((r) => r.data);

export const uploadFidelityCsv = (file, accountLabel = "default") => {
  const form = new FormData();
  form.append("file", file);
  form.append("account_label", accountLabel);
  return api()
    .post("/portfolio/fidelity/upload", form, {
      headers: { "content-type": "multipart/form-data" },
    })
    .then((r) => r.data);
};
