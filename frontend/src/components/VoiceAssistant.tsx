import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useVoiceAssistant } from "../hooks/useVoiceAssistant";
import { Transcript } from "./Transcript";
import { VoiceOrb } from "./VoiceOrb";

interface Props {
  greeting: string;
  suggestions: string[];
  layout?: "compact" | "wide";
}

/** One assistant for every mode. The server decides what it can do from the session. */
export function VoiceAssistant({ greeting, suggestions, layout = "compact" }: Props) {
  const orbRef = useRef<HTMLButtonElement>(null);
  const onLevel = useCallback((level: number) => {
    orbRef.current?.style.setProperty("--level", Math.min(level * 6, 1).toFixed(3));
  }, []);
  const assistant = useVoiceAssistant(onLevel);
  const [draft, setDraft] = useState("");

  const pressOrb = () => (assistant.status === "idle" ? void assistant.listen() : assistant.interrupt());

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code === "Space" && event.target === document.body) {
        event.preventDefault();
        pressOrb();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void assistant.sendText(draft);
    setDraft("");
  };

  return (
    <section className={`assistant assistant--${layout}`} aria-label="Voice assistant">
      <div className="assistant__control">
        <VoiceOrb ref={orbRef} status={assistant.status} onPress={pressOrb} />
        <label className="toggle">
          <input type="checkbox" checked={assistant.handsFree} onChange={(e) => assistant.setHandsFree(e.target.checked)} />
          Keep listening after each reply
        </label>
        {assistant.error && (
          <p className="notice notice--error" role="alert">
            {assistant.error}
          </p>
        )}
      </div>

      <div className="assistant__conversation">
        <Transcript messages={assistant.messages} greeting={greeting} thinking={assistant.status === "thinking"} />
        {assistant.messages.length === 0 && (
          <div className="suggestions" aria-label="Try asking">
            {suggestions.map((s) => (
              <button key={s} type="button" className="chip" onClick={() => void assistant.sendText(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        <form className="composer" onSubmit={submit}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Or type your question"
            aria-label="Type your question"
            maxLength={1000}
          />
          <button type="submit" className="btn" disabled={!draft.trim() || assistant.status === "thinking"}>
            Send
          </button>
        </form>
        {assistant.messages.length > 0 && (
          <button type="button" className="link-button" onClick={assistant.reset}>
            Start a new conversation
          </button>
        )}
      </div>
    </section>
  );
}
