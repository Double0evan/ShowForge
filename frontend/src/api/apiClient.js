import { SHOWFORGE_API_BASE_URL } from "./config";

function buildUrl(path) {
  if (!path) return SHOWFORGE_API_BASE_URL || "/";
  if (/^https?:\/\//i.test(path)) return path;
  return `${SHOWFORGE_API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = details.status;
    this.payload = details.payload;
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok || payload?.ok === false) {
    throw new ApiError(payload?.message || payload?.error || "Request failed", {
      status: response.status,
      payload,
    });
  }

  return payload;
}

export const apiClient = {
  async get(path, options = {}) {
    const response = await fetch(buildUrl(path), {
      method: "GET",
      credentials: "same-origin",
      ...options,
    });

    return parseResponse(response);
  },

  async post(path, body, options = {}) {
    const isFormData = body instanceof FormData;

    const response = await fetch(buildUrl(path), {
      method: "POST",
      credentials: "same-origin",
      headers: isFormData ? undefined : { "Content-Type": "application/json" },
      body: isFormData ? body : JSON.stringify(body || {}),
      ...options,
    });

    return parseResponse(response);
  },

  async delete(path, options = {}) {
    const response = await fetch(buildUrl(path), {
      method: "DELETE",
      credentials: "same-origin",
      ...options,
    });

    return parseResponse(response);
  },

  toFormData(values = {}) {
    const formData = new FormData();

    Object.entries(values).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item) => formData.append(key, item));
      } else if (value !== undefined && value !== null) {
        formData.append(key, value);
      }
    });

    return formData;
  },
};
