export const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8003";

const API_HEADERS = {
  "X-API-Key": "12345",
};

async function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: {
      ...API_HEADERS,
      ...(options.headers || {}),
    },
  });
}

function buildStatusError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getBackendErrorMessage(payload, fallbackMessage) {
  if (!payload) {
    return fallbackMessage;
  }

  const detail = payload.detail;
  if (typeof detail === "string") {
    return detail;
  }

  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string") {
      return detail.message;
    }
    if (typeof detail.error === "string") {
      return detail.error;
    }
  }

  if (typeof payload.message === "string") {
    return payload.message;
  }

  return fallbackMessage;
}

function buildApiError(error, fallbackMessage) {
  if (error?.code === "ECONNABORTED") {
    return new Error("Model is loading, please wait...");
  }

  const code = error?.response?.data?.detail?.code;
  if (code === "file_too_large") {
    return new Error("File too large. Max size: 200MB");
  }

  const backendMessage = getBackendErrorMessage(error?.response?.data, fallbackMessage);
  return new Error(backendMessage || fallbackMessage);
}

export async function uploadPdf(file, onUploadProgress) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await apiFetch(`${API_BASE}/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    const data = await res.json();
    if (typeof onUploadProgress === "function") {
      onUploadProgress({ loaded: 1, total: 1 });
    }
    return data;
  } catch (error) {
    throw buildApiError(error, "Upload failed");
  }
}

export async function queryApi(query) {
  try {
    const res = await apiFetch(`${API_BASE}/agent/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (res.status === 429) throw buildStatusError(429, "Too many requests");
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    const data = await res.json();
    return {
      answer: data.answer,
      status: "ok",
      guard_fired: false,
      retrieval_score: null,
      sources: [
        ...data.rag_sources.filter(Boolean).map((s, i) => ({
          id: i + 1,
          text: `Retrieved from internal document`,
          document: s,
          page: 1,
          type: "doc"
        })),
        ...data.web_sources.filter(Boolean).map((s, i) => ({
          id: data.rag_sources.length + i + 1,
          text: `Retrieved from web`,
          document: s,
          page: 1,
          type: "web"
        })),
      ],
      route: data.route,
      steps: data.steps,
    };
  } catch (error) {
    throw buildApiError(error, "Model is loading, please wait...");
  }
}

export async function queryRagByDocument(query, documentId) {
  try {
    const res = await apiFetch(`${API_BASE}/agent/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (res.status === 429) throw buildStatusError(429, "Too many requests");
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    const data = await res.json();
    return {
      answer: data.answer,
      status: "ok",
      guard_fired: false,
      retrieval_score: null,
      sources: [
        ...data.rag_sources.filter(Boolean).map((s, i) => ({
          id: i + 1,
          text: `Retrieved from internal document`,
          document: s,
          page: 1,
          type: "doc"
        })),
        ...data.web_sources.filter(Boolean).map((s, i) => ({
          id: data.rag_sources.length + i + 1,
          text: `Retrieved from web`,
          document: s,
          page: 1,
          type: "web"
        })),
      ],
      route: data.route,
      steps: data.steps,
    };
  } catch (error) {
    throw buildApiError(error, "Model is loading, please wait...");
  }
}

export async function listDocuments() {
  try {
    const res = await apiFetch(`${API_BASE}/documents`, {
      method: "GET",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    const data = await res.json();
    console.log("DOCUMENTS RESPONSE:", data);
    return data;
  } catch (error) {
    throw buildApiError(error, "Failed to load documents.");
  }
}

export function pollTaskStatus(taskId, { onDone, onError, intervalMs = 2000 } = {}) {
  if (!taskId) {
    onError?.(new Error("Missing task id"));
    return () => {};
  }

  let stopped = false;
  let timer = null;

  const stop = () => {
    stopped = true;
    if (timer) {
      window.clearTimeout(timer);
    }
  };

  const poll = async () => {
    if (stopped) {
      return;
    }

    try {
      const res = await apiFetch(`${API_BASE}/tasks/${taskId}`, {
        method: "GET",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error: ${res.status} ${text}`);
      }
      const data = await res.json();
      const status = data?.status;

      if (status === "done") {
        stop();
        onDone?.(data);
        return;
      }

      if (status === "failed") {
        stop();
        onError?.(new Error("Processing failed"));
        return;
      }

      timer = window.setTimeout(poll, intervalMs);
    } catch (error) {
      stop();
      onError?.(buildApiError(error, "Failed to check task status"));
    }
  };

  poll();
  return stop;
}

export async function deleteDocument(documentId) {
  if (!documentId) return null;
  try {
    const res = await apiFetch(`${API_BASE}/documents/${documentId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    return await res.json();
  } catch (error) {
    throw buildApiError(error, "Failed to delete document.");
  }
}

export async function resetRag() {
  try {
    const res = await apiFetch(`${API_BASE}/reset`, {
      method: "POST",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    const data = await res.json();
    return data;
  } catch (error) {
    throw buildApiError(error, "Failed to clear documents.");
  }
}
