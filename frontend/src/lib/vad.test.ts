import { describe, expect, it } from "vitest";
import { DEFAULT_VAD, initialVad, rms, stepVad } from "./vad";

describe("stepVad", () => {
  it("keeps recording while waiting for speech", () => {
    const state = initialVad(0);
    expect(stepVad(state, 0.001, 1000)).toBe("continue");
  });

  it("aborts when nobody speaks", () => {
    const state = initialVad(0);
    expect(stepVad(state, 0.001, DEFAULT_VAD.noSpeechTimeoutMs)).toBe("abort");
  });

  it("stops after silence that follows speech", () => {
    const state = initialVad(0);
    stepVad(state, 0.2, 500);
    expect(stepVad(state, 0.001, 1000)).toBe("continue");
    expect(stepVad(state, 0.001, 500 + DEFAULT_VAD.silenceMs)).toBe("stop");
  });

  it("stops at the maximum length", () => {
    const state = initialVad(0);
    stepVad(state, 0.2, 100);
    expect(stepVad(state, 0.2, DEFAULT_VAD.maxMs)).toBe("stop");
  });
});

describe("rms", () => {
  it("is zero for silence", () => {
    expect(rms(new Uint8Array([128, 128, 128]))).toBe(0);
  });
});
