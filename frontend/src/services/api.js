import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// withCredentials so the httpOnly session cookie rides along on every
// request -- required since the frontend (5173) and backend (8000) are
// different origins even though both are localhost.
export const api = axios.create({ baseURL: API_BASE, withCredentials: true });

// Without this, a session that expires mid-use (cookie expiry, a backend
// restart) leaves every subsequent request failing with 401 while most
// call sites just `.catch(() => {})` it -- the UI quietly stops updating
// with no indication anything is wrong, instead of sending the user back
// to the login screen. AuthContext registers itself here (via
// setUnauthorizedHandler) rather than being imported directly, since this
// module is imported *by* AuthContext.
let onUnauthorized = null;
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      onUnauthorized?.();
    }
    return Promise.reject(error);
  },
);

export const register = (email, password) =>
  api.post("/api/auth/register", { email, password }).then((r) => r.data);
export const login = (email, password) =>
  api.post("/api/auth/login", { email, password }).then((r) => r.data);
export const logout = () => api.post("/api/auth/logout").then((r) => r.data);
export const getMe = () => api.get("/api/auth/me").then((r) => r.data);
export const forgotPassword = (email) =>
  api.post("/api/auth/forgot-password", { email }).then((r) => r.data);
export const resetPassword = (token, password) =>
  api.post("/api/auth/reset-password", { token, password }).then((r) => r.data);
export const deleteAccount = (password) =>
  api.delete("/api/auth/account", { data: { password } }).then((r) => r.data);
export const verifyTwoFactor = (pendingToken, code) =>
  api
    .post("/api/auth/2fa/verify", { pending_token: pendingToken, code })
    .then((r) => r.data);
export const getTwoFactorStatus = () =>
  api.get("/api/auth/2fa/status").then((r) => r.data);
export const setupTwoFactor = () =>
  api.post("/api/auth/2fa/setup").then((r) => r.data);
export const enableTwoFactor = (code) =>
  api.post("/api/auth/2fa/enable", { code }).then((r) => r.data);
export const disableTwoFactor = (password) =>
  api.post("/api/auth/2fa/disable", { password }).then((r) => r.data);

export const getStats = () => api.get("/api/stats").then((r) => r.data);
export const getCategories = () => api.get("/api/categories").then((r) => r.data);
export const getLogs = (limit = 50) =>
  api.get(`/api/logs?limit=${limit}`).then((r) => r.data);
export const getAgentCommands = ({ type, source, limit = 20 } = {}) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (type) params.set("type", type);
  if (source) params.set("source", source);
  return api.get(`/api/agent-commands?${params.toString()}`).then((r) => r.data);
};
export const getRules = () => api.get("/api/rules").then((r) => r.data);
export const updateRules = (rules) =>
  api.put("/api/rules", rules).then((r) => r.data);
export const getOnboardingTemplates = () =>
  api.get("/api/onboarding/templates").then((r) => r.data);
export const applyOnboardingTemplate = (id) =>
  api.post(`/api/onboarding/templates/${id}/apply`).then((r) => r.data);
export const completeOnboarding = () =>
  api.post("/api/auth/onboarding-complete").then((r) => r.data);
export const undoLastOperation = () =>
  api.post("/api/undo").then((r) => r.data);
export const undoLog = (logId) =>
  api.post(`/api/logs/${logId}/undo`).then((r) => r.data);
export const previewRule = (type, match) =>
  api.post("/api/rules/preview", { type, match }).then((r) => r.data);
export const simulateRules = (candidateRules) =>
  api.post("/api/rules/simulate", candidateRules).then((r) => r.data);
export const generateAIRule = (prompt) =>
  api.post("/api/rules/ai-generate", { prompt }).then((r) => r.data);
export const checkRuleConflicts = (candidateRules) =>
  api.post("/api/rules/conflicts", { rules: candidateRules ?? null }).then((r) => r.data);
export const reclassifyLog = (logId, category) =>
  api.post(`/api/logs/${logId}/reclassify`, { category }).then((r) => r.data);
export const getCategoryFiles = (category) =>
  api.get(`/api/categories/${encodeURIComponent(category)}/files`).then((r) => r.data);
export const deleteCategoryFile = (category, path) =>
  api
    .delete(`/api/categories/${encodeURIComponent(category)}/files`, { data: { path } })
    .then((r) => r.data);
export const organizeExistingFiles = () =>
  api.post("/api/organize-existing").then((r) => r.data);
export const previewOrganizeExisting = () =>
  api.post("/api/organize/preview").then((r) => r.data);
export const getUnclassifiedSuggestions = (commandId) =>
  api.post("/api/unclassified/suggestions", { command_id: commandId ?? null }).then((r) => r.data);
export const analyzeDuplicates = (commandId) =>
  api.post("/api/duplicates/analyze", { command_id: commandId ?? null }).then((r) => r.data);
export const searchFiles = (query, commandId) =>
  api.post("/api/files/search", { query, command_id: commandId ?? null }).then((r) => r.data);
export const getOrganizationHealth = () =>
  api.get("/api/health/organization").then((r) => r.data);
export const simulateDownloadUrl = () => `${API_BASE}/api/simulate-download`;
// The ?t= cache-buster matters: this URL serves different bytes every time
// a new version ships, and a browser that already cached an older response
// to this exact URL (as happened during testing) keeps serving it forever
// -- a Cache-Control header on a later response can't retroactively evict
// an entry the browser cached before that header existed. A unique query
// string every click sidesteps the cache entirely rather than depending on
// the browser to honor no-store correctly in every situation.
export const agentInstallerUrl = () => `${API_BASE}/api/settings/agent-installer?t=${Date.now()}`;
export const getWeeklyReports = (weeks = 4) =>
  api.get(`/api/reports/weekly?weeks=${weeks}`).then((r) => r.data);
export const getHealth = () => api.get("/api/health").then((r) => r.data);
export const generateAgentToken = (scope = "full") =>
  api.post("/api/auth/agent-token", { scope }).then((r) => r.data);
export const updateWatchFolder = (path) =>
  api.put("/api/settings/watch-folder", { path }).then((r) => r.data);
export const browseFolder = () =>
  api.post("/api/settings/browse-folder").then((r) => r.data);
export const addWatchFolder = (path) =>
  api.post("/api/settings/watch-folders", { path }).then((r) => r.data);
export const removeWatchFolder = (path) =>
  api.delete("/api/settings/watch-folders", { data: { path } }).then((r) => r.data);
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
