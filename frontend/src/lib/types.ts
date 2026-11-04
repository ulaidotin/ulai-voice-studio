// Mirrors backend/app/schemas.py. Keep in step with it.

export type Opening = "agent" | "caller";
export type TrunkDirection = "inbound" | "outbound";
export type CallDirection = "web" | "outbound" | "inbound";
export type CallStatus = "queued" | "ringing" | "in_progress" | "completed" | "no_answer" | "failed";
export type CallEventKind = "transcript" | "tool_call" | "status";
export type Transport = "auto" | "udp" | "tcp" | "tls";
export type ToolParamType = "string" | "number" | "integer" | "boolean";

export const FINAL_STATUSES: CallStatus[] = ["completed", "no_answer", "failed"];
export const isActive = (s: CallStatus) => !FINAL_STATUSES.includes(s);

export interface Me {
  username: string;
}

export interface Variable {
  name: string;
  default: string;
  description: string;
}

export interface ToolParameter {
  name: string;
  type: ToolParamType;
  description: string;
  required: boolean;
  enum: string[];
}

export interface Tool {
  name: string;
  description: string;
  url: string;
  method: "GET" | "POST";
  headers: Record<string, string>;
  parameters: ToolParameter[];
  timeout_seconds: number;
}

export interface AgentIn {
  name: string;
  description: string;
  prompt: string;
  greeting: string;
  closing: string;
  opening: Opening;
  model: string;
  voice: string;
  language: string;
  temperature: number;
  allow_interruptions: boolean;
  greeting_interruptible: boolean;
  silence_monitor: boolean;
  backchannel_gate: boolean;
  background_noise: boolean;
  voicemail_detection: boolean;
  max_call_duration_seconds: number;
  engagement_timeout_seconds: number;
  variables: Variable[];
  tools: Tool[];
}

export interface Agent extends AgentIn {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface AgentSummary {
  id: string;
  name: string;
  description: string;
  voice: string;
  language: string;
  opening: Opening;
  updated_at: string;
  calls_total: number;
  calls_last_7d: number;
  inbound_numbers: string[];
}

export interface Trunk {
  id: string;
  name: string;
  direction: TrunkDirection;
  enabled: boolean;
  numbers: string[];
  allowed_addresses: string[];
  agent: { id: string; name: string } | null;
  address: string;
  transport: Transport;
  username: string;
  created_at: string;
  updated_at: string;
}

export interface InboundTrunkIn {
  name: string;
  numbers: string[];
  allowed_addresses: string[];
  agent_id: string | null;
}

export interface OutboundTrunkIn {
  name: string;
  address: string;
  transport: Transport;
  username: string;
  password: string;
  numbers: string[];
}

export interface WebCallOut {
  call_id: string;
  session_id: string;
  participant_id: string;
  ticket: string;
  node_address: string;
  events_token: string | null;
  control_plane_url: string;
  ice_servers: RTCIceServer[];
}

export interface OutboundCallIn {
  agent_id: string;
  trunk_id: string;
  to_number: string;
  from_number?: string | null;
  variables: Record<string, string>;
}

export interface CallEvent {
  seq: number;
  kind: CallEventKind;
  speaker: string;
  text: string;
  data: Record<string, unknown>;
  elapsed_ms: number | null;
  created_at: string;
}

export interface Call {
  id: string;
  agent_id: string | null;
  agent_name: string;
  direction: CallDirection;
  status: CallStatus;
  trunk_id: string | null;
  from_number: string;
  to_number: string;
  variables: Record<string, string>;
  created_at: string;
  answered_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  end_reason: string;
  disposition: string;
  error: string;
  usage: { prompt_tokens?: number; response_tokens?: number; cached_tokens?: number };
}

export interface CallDetail extends Call {
  events: CallEvent[];
}

export interface CallPage {
  items: Call[];
  total: number;
  page: number;
  page_size: number;
}

export interface DailyCount {
  date: string;
  web: number;
  inbound: number;
  outbound: number;
}

export interface Overview {
  active_calls: number;
  calls_today: number;
  calls_7d: number;
  answer_rate_7d: number | null;
  avg_duration_7d: number | null;
  total_minutes_7d: number;
  daily: DailyCount[];
  recent: Call[];
  agents: number;
  trunks: number;
}

export interface Health {
  ulai: "ok" | "unconfigured" | "error";
  ulai_detail: string;
  project_id: string | null;
  google_credentials: boolean;
  inbound_listener: "running" | "idle" | "error";
}

export interface Catalog {
  models: { id: string; name: string; description: string }[];
  voices: { id: string; style: string }[];
  languages: { id: string; name: string }[];
  /** Filled in by the studio on every call. */
  builtin_variables: { name: string; description: string }[];
}

export type AgentState = "listening" | "thinking" | "speaking";

export type LiveMessage =
  | { type: "call"; call: Call }
  | { type: "event"; call_id: string; event: CallEvent }
  | { type: "interim"; call_id: string; speaker: string; text: string }
  | { type: "agent_state"; call_id: string; state: AgentState };
