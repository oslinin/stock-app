import { api } from "./client";

export const listWatchlist = () => api().get("/watchlist").then((r) => r.data);
export const addWatchlistSymbol = (body) =>
  api().post("/watchlist", body).then((r) => r.data);
export const removeWatchlistSymbol = (symbol) =>
  api().delete(`/watchlist/${symbol}`);

export const listScreeners = () =>
  api().get("/watchlist/screeners").then((r) => r.data);
export const runScreener = (id, params = {}) =>
  api().post(`/watchlist/screeners/${id}/run`, params).then((r) => r.data);
