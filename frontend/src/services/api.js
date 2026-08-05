import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// withCredentials so the httpOnly session cookie rides along on every
// request -- required since the frontend (5173) and backend (8000) are
// different origins even though both are localhost.
export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

export const register = (email, password) =>
  api.post("/api/auth/register", { email, password }).then((r) => r.data);
export const login = (email, password) =>
  api.post("/api/auth/login", { email, password }).then((r) => r.data);
export const logout = () => api.post("/api/auth/logout").then((r) => r.data);
export const getMe = () => api.get("/api/auth/me").then((r) => r.data);

export const getStats = () => api.get("/api/stats").then((r) => r.data);
export const getCategories = () => api.get("/api/categories").then((r) => r.data);
export const getLogs = (limit = 50) =>
  api.get(`/api/logs?limit=${limit}`).then((r) => r.data);
export const getRules = () => api.get("/api/rules").then((r) => r.data);
export const updateRules = (rules) =>
  api.put("/api/rules", rules).then((r) => r.data);
export const undoLastOperation = () =>
  api.post("/api/undo").then((r) => r.data);
export const previewRule = (type, match) =>
  api.post("/api/rules/preview", { type, match }).then((r) => r.data);
export const reclassifyLog = (logId, category) =>
  api.post(`/api/logs/${logId}/reclassify`, { category }).then((r) => r.data);
export const organizeExistingFiles = () =>
  api.post("/api/organize-existing").then((r) => r.data);
export const simulateDownload = () =>
  api.post("/api/simulate-download").then((r) => r.data);
export const getWeeklyReports = (weeks = 4) =>
  api.get(`/api/reports/weekly?weeks=${weeks}`).then((r) => r.data);
export const getHealth = () => api.get("/api/health").then((r) => r.data);
export const updateWatchFolder = (path) =>
  api.put("/api/settings/watch-folder", { path }).then((r) => r.data);
export const csvReportUrl = (since, until) => {
  const params = new URLSearchParams();
  if (since) params.set("since", since);
  if (until) params.set("until", until);
  const qs = params.toString();
  return `${API_BASE}/api/reports/csv${qs ? `?${qs}` : ""}`;
};
export const excelReportUrl = () => `${API_BASE}/api/reports/excel`;
export const pdfReportUrl = () => `${API_BASE}/api/reports/pdf`;
export const wsUrl = () => `${API_BASE.replace(/^http/, "ws")}/ws`;
