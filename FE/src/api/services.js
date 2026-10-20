/** Typed-ish endpoint wrappers: components never build URLs themselves. */
import { api } from "./client";

export const authApi = {
  login: (email, password) => api.post("/auth/login", { email, password }),
  register: (payload) => api.post("/auth/register", payload),
  me: () => api.get("/auth/me"),
  updateMe: (payload) => api.patch("/auth/me", payload),
  changePassword: (payload) => api.post("/auth/change-password", payload),
};

export const usersApi = {
  list: (q) => api.get("/users", { q }),
  create: (payload) => api.post("/users", payload),
  update: (id, payload) => api.patch(`/users/${id}`, payload),
};

export const dashboardApi = {
  summary: () => api.get("/dashboard"),
  status: () => api.get("/system/status"),
};

export const dealsApi = {
  list: (params) => api.get("/deals", params),
  get: (id) => api.get(`/deals/${id}`),
  create: (payload) => api.post("/deals", payload),
  update: (id, payload) => api.patch(`/deals/${id}`, payload),
  remove: (id) => api.delete(`/deals/${id}`),
  members: (id) => api.get(`/deals/${id}/members`),
  addMember: (id, payload) => api.post(`/deals/${id}/members`, payload),
  removeMember: (id, memberId) => api.delete(`/deals/${id}/members/${memberId}`),
  activity: (id, limit = 100) => api.get(`/deals/${id}/activity`, { limit }),
};

export const documentsApi = {
  list: (dealId, params) => api.get(`/deals/${dealId}/documents`, params),
  get: (dealId, docId) => api.get(`/deals/${dealId}/documents/${docId}`),
  upload: (dealId, files, category, description, onProgress) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("category", category);
    if (description) form.append("description", description);
    return api.upload(`/deals/${dealId}/documents`, form, onProgress);
  },
  update: (dealId, docId, payload) => api.patch(`/deals/${dealId}/documents/${docId}`, payload),
  remove: (dealId, docId) => api.delete(`/deals/${dealId}/documents/${docId}`),
  reprocess: (dealId, docId) => api.post(`/deals/${dealId}/documents/${docId}/reprocess`),
  chunks: (dealId, docId, offset = 0, limit = 20) =>
    api.get(`/deals/${dealId}/documents/${docId}/chunks`, { offset, limit }),
  fileUrl: (dealId, docId) => api.blobUrl(`/deals/${dealId}/documents/${docId}/download`),
};

export const chatApi = {
  conversations: (dealId) => api.get(`/deals/${dealId}/conversations`),
  create: (dealId, title) => api.post(`/deals/${dealId}/conversations`, { title }),
  rename: (dealId, id, title) => api.patch(`/deals/${dealId}/conversations/${id}`, { title }),
  remove: (dealId, id) => api.delete(`/deals/${dealId}/conversations/${id}`),
  messages: (dealId, id) => api.get(`/deals/${dealId}/conversations/${id}/messages`),
  ask: (dealId, id, payload, handlers, signal) =>
    api.stream(`/deals/${dealId}/conversations/${id}/messages`, payload, handlers, signal),
  feedback: (dealId, id, messageId, feedback) =>
    api.post(`/deals/${dealId}/conversations/${id}/messages/${messageId}/feedback`, { feedback }),
  search: (dealId, payload) => api.post(`/deals/${dealId}/search`, payload),
};

export const diligenceApi = {
  checklist: (dealId) => api.get(`/deals/${dealId}/checklist`),
  createItem: (dealId, payload) => api.post(`/deals/${dealId}/checklist`, payload),
  updateItem: (dealId, id, payload) => api.patch(`/deals/${dealId}/checklist/${id}`, payload),
  removeItem: (dealId, id) => api.delete(`/deals/${dealId}/checklist/${id}`),
  reviewChecklist: (dealId) => api.post(`/deals/${dealId}/checklist/ai-review`),

  risks: (dealId, params) => api.get(`/deals/${dealId}/risks`, params),
  createRisk: (dealId, payload) => api.post(`/deals/${dealId}/risks`, payload),
  updateRisk: (dealId, id, payload) => api.patch(`/deals/${dealId}/risks/${id}`, payload),
  removeRisk: (dealId, id) => api.delete(`/deals/${dealId}/risks/${id}`),

  startAnalysis: (dealId, payload) => api.post(`/deals/${dealId}/analysis`, payload),
  analysisRuns: (dealId) => api.get(`/deals/${dealId}/analysis`),
  analysisRun: (dealId, runId) => api.get(`/deals/${dealId}/analysis/${runId}`),
};
