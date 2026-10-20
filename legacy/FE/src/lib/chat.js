export const defaultTopK = Number(import.meta.env.VITE_CHAT_TOP_K_DEFAULT || "3");
export const themeStorageKey = "rag-chatbot-theme";

export const providerOptions = [
  { value: "default", label: "Server Default" },
  { value: "mock", label: "Mock" },
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Gemini" },
  { value: "groq", label: "Groq" },
  { value: "openrouter", label: "OpenRouter" },
];

export const responseModeOptions = [
  { value: "stream", label: "Streaming" },
  { value: "ask", label: "Non-Streaming" },
];

export const rerankStrategyOptions = [
  { value: "default", label: "Server Default" },
  { value: "fast", label: "Custom" },
  { value: "hybrid", label: "Hybrid" },
  { value: "neural", label: "Neural" },
];

export const retrievalModeOptions = [
  { value: "default", label: "Server Default" },
  { value: "exact", label: "Exact" },
  { value: "ann_rerank", label: "ANN + Rerank" },
];

export function formatRerankStrategyLabel(value) {
  if (value === "fast") {
    return "Custom";
  }

  if (value === "hybrid") {
    return "Hybrid";
  }

  if (value === "neural") {
    return "Neural";
  }

  return value;
}

export function formatRetrievalModeLabel(value) {
  if (value === "ann_rerank") {
    return "ANN + Rerank";
  }

  if (value === "exact") {
    return "Exact";
  }

  return value;
}

export const sampleQuestions = [
  "Who is eligible for membership in this plan?",
  "What counties are included in the service area?",
  "Should a member use the Medicare card or the UnitedHealthcare UCard for covered services?",
];

export function createMessage(role, content, extra = {}) {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    createdAt: new Date().toISOString(),
    ...extra,
  };
}

export async function readErrorMessage(response) {
  try {
    const data = await response.json();
    return data.error?.message || data.detail || data.message || "";
  } catch {
    return "";
  }
}

export function formatDate(value, options) {
  if (!value) {
    return "Unknown";
  }

  return new Date(value).toLocaleString([], options);
}

export function formatTime(value) {
  return formatDate(value, {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatLatency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return null;
  }

  const numericValue = Number(value);

  if (numericValue >= 1000) {
    return `${(numericValue / 1000).toFixed(1)}s`;
  }

  return `${Math.round(numericValue)}ms`;
}

export function formatSimilarity(score) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) {
    return null;
  }

  return Number(score).toFixed(3);
}

export function getInitialThemePreference() {
  if (typeof window === "undefined") {
    return "system";
  }

  const storedPreference = window.localStorage.getItem(themeStorageKey);

  if (storedPreference === "light" || storedPreference === "dark") {
    return storedPreference;
  }

  return "system";
}

export function resolveTheme(themePreference, prefersDarkMode) {
  if (themePreference === "light" || themePreference === "dark") {
    return themePreference;
  }

  return prefersDarkMode ? "dark" : "light";
}
