import { api } from "./client";

export const listBots = () => api().get("/bots").then((r) => r.data);
export const createBot = (body) => api().post("/bots", body).then((r) => r.data);
export const getBotRuns = (id) => api().get(`/bots/${id}/runs`).then((r) => r.data);
export const startBot = (id) => api().post(`/bots/${id}/start`).then((r) => r.data);
export const pauseBot = (id) => api().post(`/bots/${id}/pause`).then((r) => r.data);
export const killBot = (id) => api().post(`/bots/${id}/kill`).then((r) => r.data);
export const killAllBots = () => api().post("/bots/kill-all").then((r) => r.data);
