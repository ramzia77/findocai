import type {
  AuditResponse,
  DocType,
  DocumentsResponse,
  HealthResponse,
  IngestResponse,
  QueryResponse,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

interface ApiConfig {
  baseUrl: string;
  apiKey: string;
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
  } catch {
    // response wasn't JSON -- fall through to the generic message below
  }
  return `Request failed with status ${response.status}`;
}

async function request<T>(
  config: ApiConfig,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (config.apiKey) headers.set("X-API-Key", config.apiKey);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${config.baseUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Could not reach ${config.baseUrl} -- check the API base URL in Settings.`);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getHealth(config: ApiConfig): Promise<HealthResponse> {
  return request<HealthResponse>(config, "/health");
}

export function ingestDocument(
  config: ApiConfig,
  file: File,
  docType: DocType,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", docType);
  return request<IngestResponse>(config, "/ingest", { method: "POST", body: form });
}

export function askQuestion(
  config: ApiConfig,
  question: string,
  docType: DocType | null,
  topK: number,
): Promise<QueryResponse> {
  return request<QueryResponse>(config, "/query", {
    method: "POST",
    body: JSON.stringify({ question, doc_type: docType, top_k: topK }),
  });
}

export function listDocuments(config: ApiConfig): Promise<DocumentsResponse> {
  return request<DocumentsResponse>(config, "/documents");
}

export function deleteDocument(config: ApiConfig, docId: string): Promise<void> {
  return request<void>(config, `/documents/${encodeURIComponent(docId)}`, { method: "DELETE" });
}

export function listAudit(config: ApiConfig, limit = 50): Promise<AuditResponse> {
  return request<AuditResponse>(config, `/audit?limit=${limit}`);
}
