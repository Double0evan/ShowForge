const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "";

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function getInventory() {
  return requestJson("/api/inventory");
}

export async function getUsers() {
  return requestJson("/api/users");
}

export async function getMembers() {
  return requestJson("/api/members");
}

export async function getHealth() {
  return requestJson("/health");
}
