import { useEffect, useRef } from "react";
import type { ChatMessage } from "../hooks/useVoiceAssistant";

interface Props {
  messages: Pick<ChatMessage, "id" | "role" | "text">[];
  greeting?: string;
  thinking?: boolean;
}

export function Transcript({ messages, greeting, thinking }: Props) {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages.length, thinking]);

  return (
    <div ref={logRef} className="transcript" role="log" aria-live="polite">
      {greeting && <p className="bubble bubble--assistant">{greeting}</p>}
      {messages.map((m) => (
        <p key={m.id} className={`bubble bubble--${m.role}`}>
          <span className="sr-only">{m.role === "user" ? "You said: " : "Assistant: "}</span>
          {m.text}
        </p>
      ))}
      {thinking && (
        <p className="bubble bubble--assistant bubble--thinking" aria-label="Assistant is thinking">
          <span />
          <span />
          <span />
        </p>
      )}
    </div>
  );
}
