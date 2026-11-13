/**
 * Typed client for the Sanad API.
 *
 * Every request carries an `X-Request-Id`; every failure becomes an `ApiError`
 * with the backend `module`, `code` and `requestId`, so the UI can show them
 * and a bug report can point straight at the failing module.
 *
 * Later the endpoint types will be generated from the backend OpenAPI schema.
 */

export interface Problem {
  status: number;
  title: string;
  code: string;
  module: string;
  request_id: string;
  detail?: string;
  errors?: { loc: (string | number)[]; msg: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly module: string;
  readonly requestId: string;
  readonly detail?: string;
  readonly fieldErrors: Problem["errors"];

  constructor(p: Problem) {
    super(`${p.code} (${p.status}) request_id=${p.request_id}`);
    this.name = "ApiError";
    this.status = p.status;
    this.code = p.code;
    this.module = p.module;
    this.requestId = p.request_id;
    this.detail = p.detail;
    this.fieldErrors = p.errors;
  }
}

export interface HealthReport {
  status: "ok" | "degraded";
  components: Record<string, "ok" | "down">;
}

export interface ModuleInfo {
  name: string;
  summary: string;
  depends_on: string[];
  emits: string[];
  listens_to: string[];
  tables: string[];
  endpoints: number;
}

export function newRequestId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

export interface ClientOptions {
  /** "" in the browser (same origin via the proxy), full URL on the server. */
  baseUrl?: string;
  locale?: string;
  fetchImpl?: typeof fetch;
}

export function createClient({ baseUrl = "", locale, fetchImpl = fetch }: ClientOptions = {}) {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const requestId = newRequestId();
    const headers = new Headers(init.headers);
    headers.set("X-Request-Id", requestId);
    headers.set("Accept", "application/json");
    if (locale) headers.set("Accept-Language", locale);

    let res: Response;
    try {
      res = await fetchImpl(`${baseUrl}${path}`, { ...init, headers });
    } catch {
      throw new ApiError({
        status: 0,
        title: "Network error",
        code: "NETWORK_ERROR",
        module: "-",
        request_id: requestId,
      });
    }

    const body: unknown = await res.json().catch(() => null);
    if (!res.ok && !(path.startsWith("/health/") && res.status === 503)) {
      const p = (body ?? {}) as Partial<Problem>;
      throw new ApiError({
        status: res.status,
        title: p.title ?? res.statusText,
        code: p.code ?? `HTTP_${res.status}`,
        module: p.module ?? "-",
        request_id: p.request_id ?? res.headers.get("X-Request-Id") ?? requestId,
        detail: p.detail,
        errors: p.errors,
      });
    }
    return body as T;
  }

  return {
    request,
    health: () => request<HealthReport>("/health/ready"),
    modules: () => request<{ modules: ModuleInfo[] }>("/api/v1/system/modules"),
  };
}

export type ApiClient = ReturnType<typeof createClient>;
