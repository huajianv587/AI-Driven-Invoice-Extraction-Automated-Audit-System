const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8009";

export function getApiBaseUrl() {
  return API_BASE_URL.replace(/\/$/, "");
}

export async function readError(response: Response) {
  try {
    const payload = await response.json();
    const detail = payload.detail ?? payload.message ?? "Request failed.";
    const requestId = payload.request_id ? ` (request ${payload.request_id})` : "";
    return `${typeof detail === "string" ? detail : "Request failed."}${requestId}`;
  } catch {
    return response.statusText || "Request failed.";
  }
}
