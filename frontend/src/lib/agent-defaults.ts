import type { AgentIn, Tool } from "./types";

// Same defaults as AgentBase in backend/app/schemas.py.
export function emptyAgent(name = "Untitled agent"): AgentIn {
  return {
    name,
    description: "",
    prompt: "",
    greeting: "",
    closing: "",
    opening: "agent",
    model: "gemini-live-2.5-flash-native-audio",
    voice: "Puck",
    language: "",
    temperature: 0.7,
    allow_interruptions: true,
    greeting_interruptible: true,
    silence_monitor: true,
    backchannel_gate: true,
    background_noise: false,
    voicemail_detection: false,
    max_call_duration_seconds: 900,
    engagement_timeout_seconds: 30,
    variables: [],
    tools: [],
  };
}

export function emptyTool(): Tool {
  return { name: "", description: "", url: "", method: "POST", headers: {}, parameters: [], timeout_seconds: 10 };
}

/** The editable fields of an agent, in a stable shape for comparing against what's saved. */
export function toAgentIn(a: AgentIn): AgentIn {
  const {
    name,
    description,
    prompt,
    greeting,
    closing,
    opening,
    model,
    voice,
    language,
    temperature,
    allow_interruptions,
    greeting_interruptible,
    silence_monitor,
    backchannel_gate,
    background_noise,
    voicemail_detection,
    max_call_duration_seconds,
    engagement_timeout_seconds,
    variables,
    tools,
  } = a;
  return {
    name,
    description,
    prompt,
    greeting,
    closing,
    opening,
    model,
    voice,
    language,
    temperature,
    allow_interruptions,
    greeting_interruptible,
    silence_monitor,
    backchannel_gate,
    background_noise,
    voicemail_detection,
    max_call_duration_seconds,
    engagement_timeout_seconds,
    variables,
    tools,
  };
}
