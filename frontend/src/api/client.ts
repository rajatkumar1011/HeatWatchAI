import axios from "axios";

const TOKEN_KEY = "heatwatch_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({
  baseURL: "/api/v1",
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Extract a user-facing message from any API error (FR-10). */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as { error?: { message?: string; details?: unknown } } | undefined;
    if (body?.error?.message) {
      const details = body.error.details as { messages?: string[] } | undefined;
      if (details?.messages?.length) return `${body.error.message} ${details.messages.join(" ")}`;
      return body.error.message;
    }
    if (err.code === "ERR_NETWORK") return "Cannot reach the HeatWatch AI server. Check your connection and try again.";
    return err.message || "Unexpected error.";
  }
  return String(err);
}

export function downloadFile(path: string) {
  // authenticated download via blob
  return api
    .get(path, { responseType: "blob" })
    .then((resp) => {
      const disposition: string = resp.headers["content-disposition"] || "";
      const match = /filename="?([^";]+)"?/.exec(disposition);
      const filename = match?.[1] ?? `heatwatch-report-${Date.now()}`;
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    })
    .catch((err) => Promise.reject(new Error(errorMessage(err))));
}
