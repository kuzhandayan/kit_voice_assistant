import { forwardRef } from "react";
import type { VoiceStatus } from "../hooks/useVoiceAssistant";

const LABEL: Record<VoiceStatus, string> = {
  idle: "Tap to talk",
  listening: "Listening… tap to stop",
  thinking: "Thinking…",
  speaking: "Speaking… tap to interrupt",
};

interface Props {
  status: VoiceStatus;
  onPress: () => void;
}

/** The mic control. Its ring scales with the live mic level via the --level CSS variable. */
export const VoiceOrb = forwardRef<HTMLButtonElement, Props>(function VoiceOrb({ status, onPress }, ref) {
  return (
    <div className="orb-wrap">
      <button
        ref={ref}
        type="button"
        className={`orb orb--${status}`}
        onClick={onPress}
        disabled={status === "thinking"}
        aria-label={LABEL[status]}
        aria-live="polite"
      >
        <span className="orb__ring" aria-hidden />
        <svg className="orb__icon" viewBox="0 0 24 24" aria-hidden>
          {status === "speaking" ? (
            <path d="M7 7h3v10H7zM14 7h3v10h-3z" />
          ) : (
            <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
          )}
        </svg>
      </button>
      <p className="orb__status">{LABEL[status]}</p>
    </div>
  );
});
