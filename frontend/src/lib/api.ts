import type {
  Agent,
  AgentIn,
  AgentSummary,
  Call,
  CallDetail,
  CallPage,
  Catalog,
  Health,
  InboundTrunkIn,
  Me,
  OutboundCallIn,
  OutboundTrunkIn,
  Overview,
  Trunk,
  WebCallOut,
} from "./types";

/** One field-level problem from a 422, e.g. { path: ["tools", 0, "url"], message: "..." }. */
export interface FieldError {
  path: (string | number)[];
  message: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields: FieldError[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface PydanticError {
  loc?: (string | number)[];
  msg?: string;
}

function humanise(msg: string): string {
  // Pydantic prefixes custom validator messages with "Value error, ".
  return msg.replace(/^Value error, /, "").replace(/^String should have at least 1 character$/, "Required");
}

async function toError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    // not JSON
  }
  if (typeof detail === "string") return new ApiError(detail, res.status);
  if (Array.isArray(detail)) {
    const fields = (detail as PydanticError[]).map((d) => ({
      path: (d.loc ?? []).filter((p) => p !== "body"),
      message: humanise(d.msg ?? "Invalid value"),
    }));
    const first = fields[0];
    const where = first?.path.length ? `${first.path.join(" › ")}: ` : "";
    return new ApiError(first ? `${where}${first.message}` : "Some fields are invalid", res.status, fields);
  }
  if (res.status === 502) return new ApiError("Ulai Voice Infra couldn't complete the request.", res.status);
  return new ApiError(`Request failed (${res.status})`, res.status);
}

function toLogin() {
  if (typeof window === "undefined" || window.location.pathname === "/login") return;
  const next = window.location.pathname + window.location.search;
  // A full page load on purpose: nothing cached from the expired session should survive.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    toLogin();
    throw new ApiError("Your session has ended. Sign in again.", 401);
  }
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface CallFilters {
  status?: string;
  direction?: string;
  agent_id?: string;
  q?: string;
}

export const api = {
  login: (username: string, password: string) =>
    request<Me>("/auth/login", { method: "POST", json: { username, password } }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<Me>("/auth/me"),

  overview: () => request<Overview>("/overview"),
  health: () => request<Health>("/health"),
  catalog: () => request<Catalog>("/catalog"),

  agents: () => request<AgentSummary[]>("/agents"),
  agent: (id: string) => request<Agent>(`/agents/${id}`),
  createAgent: (body: AgentIn) => request<Agent>("/agents", { method: "POST", json: body }),
  updateAgent: (id: string, body: AgentIn) => request<Agent>(`/agents/${id}`, { method: "PUT", json: body }),
  duplicateAgent: (id: string) => request<Agent>(`/agents/${id}/duplicate`, { method: "POST" }),
  deleteAgent: (id: string) => request<void>(`/agents/${id}`, { method: "DELETE" }),

  trunks: () => request<Trunk[]>("/trunks"),
  createInbound: (body: InboundTrunkIn) => request<Trunk>("/trunks/inbound", { method: "POST", json: body }),
  createOutbound: (body: OutboundTrunkIn) => request<Trunk>("/trunks/outbound", { method: "POST", json: body }),
  updateTrunk: (id: string, body: Record<string, unknown>) =>
    request<Trunk>(`/trunks/${id}`, { method: "PATCH", json: body }),
  setTrunkEnabled: (id: string, enabled: boolean) =>
    request<Trunk>(`/trunks/${id}/enabled`, { method: "PUT", json: { enabled } }),
  deleteTrunk: (id: string) => request<void>(`/trunks/${id}`, { method: "DELETE" }),

  calls: (filters: CallFilters & { page: number; page_size: number }) =>
    request<CallPage>(`/calls${query({ ...filters })}`),
  call: (id: string) => request<CallDetail>(`/calls/${id}`),
  /** `draft` runs the call on unsaved edits instead of the saved agent. */
  startWebCall: (agent_id: string, variables: Record<string, string>, draft?: AgentIn) =>
    request<WebCallOut>("/calls/web", { method: "POST", json: { agent_id, variables, draft } }),
  startOutboundCall: (body: OutboundCallIn) => request<Call>("/calls/outbound", { method: "POST", json: body }),
  endCall: (id: string) => request<Call>(`/calls/${id}/end`, { method: "POST" }),
  exportUrl: (filters: CallFilters) => `/api/calls/export.csv${query({ ...filters })}`,
};

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
