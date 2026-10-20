const BASE_URL = `${import.meta.env.VITE_API_BASE_URL || ""}/api/v1`;
const TOKEN_KEY = "deallens.token";

let authToken = safeStorage(() => localStorage.getItem(TOKEN_KEY));
let unauthorizedHandler = null;

function safeStorage(fn) {
  try {
    return fn();
  } catch {
    return null;
  }
}

export function setAuthToken(token) {
  authToken = token;
  safeStorage(() => (token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY)));
}

export function getAuthToken() {
  return authToken;
}

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function toApiError(response) {
  let message = `Request failed (${response.status})`;
  let details;
  try {
    const body = await response.json();
    message = body?.error?.message || body?.detail || message;
    details = body?.error?.details;
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 401 && unauthorizedHandler) unauthorizedHandler();
  return new ApiError(message, response.status, details);
}

function authHeaders(extra = {}) {
  return authToken ? { ...extra, Authorization: `Bearer ${authToken}` } : extra;
}

function buildUrl(path, params) {
  const url = `${BASE_URL}${path}`;
  if (!params) return url;
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.append(key, value);
  });
  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

async function request(method, path, { body, params, signal } = {}) {
  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      signal,
      headers: authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  get: (path, params, signal) => request("GET", path, { params, signal }),
  post: (path, body) => request("POST", path, { body: body ?? {} }),
  patch: (path, body) => request("PATCH", path, { body }),
  delete: (path) => request("DELETE", path),

  /** Multipart upload with progress callback (fetch has no upload progress). */
  upload(path, formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", buildUrl(path));
      if (authToken) xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        let data = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else {
          if (xhr.status === 401 && unauthorizedHandler) unauthorizedHandler();
          reject(new ApiError(data?.error?.message || `Upload failed (${xhr.status})`, xhr.status));
        }
      };
      xhr.onerror = () => reject(new ApiError("Upload failed: cannot reach the server.", 0));
      xhr.send(formData);
    });
  },

  /** Fetch a protected file and return an object URL. */
  async blobUrl(path) {
    const response = await fetch(buildUrl(path), { headers: authHeaders() });
    if (!response.ok) throw await toApiError(response);
    return URL.createObjectURL(await response.blob());
  },

  /**
   * POST and consume a Server-Sent Events stream.
   * handlers: { meta, token, done, error } keyed by event name.
   */
  async stream(path, body, handlers, signal) {
    let response;
    try {
      response = await fetch(buildUrl(path), {
        method: "POST",
        signal,
        headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
        body: JSON.stringify(body),
      });
    } catch (error) {
      if (error.name === "AbortError") return;
      throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
    }
    if (!response.ok) throw await toApiError(response);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        let data = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7).trim();
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (data && handlers[event]) handlers[event](JSON.parse(data));
      }
    }
  },
};
