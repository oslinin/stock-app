import { api } from "./client";

export const getProviders = () =>
  api().get("/marketdata/providers").then((r) => r.data);
export const getQuote = (symbol, source) =>
  api()
    .get("/marketdata/quote", { params: { symbol, ...(source && { source }) } })
    .then((r) => r.data);
export const getExpiries = (symbol, source) =>
  api()
    .get("/marketdata/expiries", { params: { symbol, ...(source && { source }) } })
    .then((r) => r.data);
export const getChain = (symbol, { expiry, source, greeks } = {}) =>
  api()
    .get("/marketdata/chain", {
      params: {
        symbol,
        ...(expiry && { expiry }),
        ...(source && { source }),
        ...(greeks !== undefined && { greeks }),
      },
    })
    .then((r) => r.data);
export const getBars = (symbol, params = {}) =>
  api().get("/marketdata/bars", { params: { symbol, ...params } }).then((r) => r.data);
export const getIndicators = (symbol, params = {}) =>
  api()
    .get("/marketdata/indicators", { params: { symbol, ...params } })
    .then((r) => r.data);
export const getIvRank = (symbol) =>
  api().get("/marketdata/ivrank", { params: { symbol } }).then((r) => r.data);
export const analyzeStructure = (body) =>
  api().post("/analytics/structure", body).then((r) => r.data);
