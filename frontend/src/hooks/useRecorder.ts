import { useCallback, useRef } from "react";
import { initialVad, rms, stepVad } from "../lib/vad";

const MIME_PREFERENCE = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_PREFERENCE.find((type) => MediaRecorder.isTypeSupported(type));
}

export class MicError extends Error {}

/**
 * Records one utterance. Stops on its own after a pause in speech (voice activity detection),
 * or when stop() is called. Resolves to null when nothing was said.
 */
export function useRecorder(onLevel: (level: number) => void) {
  const stopRef = useRef<(() => void) | null>(null);

  const record = useCallback(async (): Promise<Blob | null> => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new MicError("This browser can't record audio. Type your question instead.");
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      throw new MicError("Microphone access is blocked. Allow it in the browser's address bar, or type instead.");
    }

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const vad = initialVad(performance.now());
    let frame = 0;
    let aborted = false;

    return new Promise<Blob | null>((resolve) => {
      const finish = () => {
        cancelAnimationFrame(frame);
        stream.getTracks().forEach((track) => track.stop());
        void context.close();
        onLevel(0);
        stopRef.current = null;
        resolve(aborted || chunks.length === 0 ? null : new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.ondataavailable = (event) => event.data.size > 0 && chunks.push(event.data);
      recorder.onstop = finish;

      const stop = (abort = false) => {
        aborted = abort;
        if (recorder.state !== "inactive") recorder.stop();
      };
      stopRef.current = () => stop(!vad.heardSpeech);

      const tick = () => {
        analyser.getByteTimeDomainData(samples);
        const level = rms(samples);
        onLevel(level);
        const decision = stepVad(vad, level, performance.now());
        if (decision === "continue") frame = requestAnimationFrame(tick);
        else stop(decision === "abort");
      };
      recorder.start(250);
      frame = requestAnimationFrame(tick);
    });
  }, [onLevel]);

  const stop = useCallback(() => stopRef.current?.(), []);

  return { record, stop };
}
