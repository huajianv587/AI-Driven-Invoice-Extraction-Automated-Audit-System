const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export function getApiBaseUrl() {
  if (API_BASE_URL) {
    return API_BASE_URL.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api`;
  }
  return "http://127.0.0.1:8009";
}

export async function readError(response: Response) {
  const headerRequestId = response.headers.get("x-request-id");
  try {
    const payload = await response.json();
    const detail = payload.detail ?? payload.message ?? "Request failed.";
    const requestIdValue = payload.request_id ?? headerRequestId;
    const requestId = requestIdValue ? ` (request ${requestIdValue})` : "";
    return `${typeof detail === "string" ? detail : "Request failed."}${requestId}`;
  } catch {
    const requestId = headerRequestId ? ` (request ${headerRequestId})` : "";
    return `${response.statusText || "Request failed."}${requestId}`;
  }
}
