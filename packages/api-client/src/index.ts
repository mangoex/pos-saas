export const API_BASE_URL = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const isSuperadminEndpoint = endpoint.startsWith("/superadmin");
  const masterToken = typeof window !== "undefined" ? localStorage.getItem("saas_master_token") : null;
  const token = (isSuperadminEndpoint && masterToken)
    ? masterToken
    : (typeof window !== "undefined" ? (localStorage.getItem("auth_token") || sessionStorage.getItem("auth_token")) : null);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem("auth_token");
      sessionStorage.removeItem("auth_token");
      // Could trigger a redirect to /login here if we use a global event or react context
    }

    let errorData;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiError(response.status, "unknown_error", "An unknown error occurred");
    }

    throw new ApiError(
      response.status,
      errorData.detail?.code || "api_error",
      errorData.detail?.message || errorData.detail || "API Error"
    );
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}
