export interface VadConfig {
  speechThreshold: number;
  silenceMs: number;
  noSpeechTimeoutMs: number;
  maxMs: number;
}

export interface VadState {
  startedAt: number;
  heardSpeech: boolean;
  lastSpeechAt: number;
}

export type VadDecision = "continue" | "stop" | "abort";

export const DEFAULT_VAD: VadConfig = {
  speechThreshold: 0.035,
  silenceMs: 1200,
  noSpeechTimeoutMs: 8000,
  maxMs: 30000,
};

export function initialVad(now: number): VadState {
  return { startedAt: now, heardSpeech: false, lastSpeechAt: now };
}

/** Decides whether to keep recording based on the current mic level (RMS 0..1). */
export function stepVad(state: VadState, level: number, now: number, config: VadConfig = DEFAULT_VAD): VadDecision {
  if (level >= config.speechThreshold) {
    state.heardSpeech = true;
    state.lastSpeechAt = now;
  }
  if (now - state.startedAt >= config.maxMs) return state.heardSpeech ? "stop" : "abort";
  if (!state.heardSpeech) return now - state.startedAt >= config.noSpeechTimeoutMs ? "abort" : "continue";
  return now - state.lastSpeechAt >= config.silenceMs ? "stop" : "continue";
}

export function rms(samples: Uint8Array): number {
  let sum = 0;
  for (const value of samples) {
    const centred = (value - 128) / 128;
    sum += centred * centred;
  }
  return Math.sqrt(sum / samples.length);
}
