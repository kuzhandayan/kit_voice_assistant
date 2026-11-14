export type Role = "public" | "student" | "teacher";

export interface Me {
  role: Role;
  user_id: number | null;
  login_id: string | null;
  name: string | null;
  profile: Record<string, string | number | null>;
}

export interface Turn {
  conversation_id: string | null;
  transcript: string;
  reply: string;
  reply_message_id: number | null;
  audio_url: string | null;
  provider: string | null;
  tools: { name: string; status: string }[];
}

export interface Course {
  id: number;
  code: string;
  name: string;
  department: string;
  min_12th_percent: number;
  annual_fee: number;
  hostel_fee: number;
  seats: number;
}

export interface College {
  name: string;
  tagline: string;
  description: string;
  contact: { phone: string; email: string; website: string; address: string };
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

const REQUEST_TIMEOUT_MS = 60_000;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS), ...init });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0, "network");
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error ?? {};
    throw new ApiError(error.message ?? "Something went wrong.", response.status, error.code ?? "error");
  }
  return body as T;
}

const json = (data: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  me: () => request<Me>("/api/auth/me"),
  login: (login_id: string, password: string) => request<Me>("/api/auth/login", json({ login_id, password })),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  home: () => request<{ college: College; courses: Course[] }>("/api/public/home"),
  chatTurn: (text: string, conversationId: string | null) =>
    request<Turn>("/api/chat/turn", json({ text, conversation_id: conversationId })),
  voiceTurn: (audio: Blob, conversationId: string | null) => {
    const form = new FormData();
    const extension = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("audio", audio, `speech.${extension}`);
    if (conversationId) form.append("conversation_id", conversationId);
    return request<Turn>("/api/voice/turn", { method: "POST", body: form });
  },
  history: () => request<ConversationSummary[]>("/api/history"),
  conversation: (id: string) =>
    request<ConversationSummary & { messages: StoredMessage[] }>(`/api/history/${encodeURIComponent(id)}`),
};
