import { useCallback, useEffect, useRef } from "react";

/** Plays server TTS audio; falls back to the browser voice if the audio can't load. */
export function useAudioPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audioRef.current = null;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);

  const speakWithBrowser = useCallback((text: string, onDone: () => void) => {
    if (!("speechSynthesis" in window)) return onDone();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.onend = onDone;
    utterance.onerror = onDone;
    window.speechSynthesis.speak(utterance);
  }, []);

  const play = useCallback(
    (url: string | null, text: string, onDone: () => void) => {
      stop();
      if (!url) return speakWithBrowser(text, onDone);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        audioRef.current = null;
        onDone();
      };
      audio.onerror = () => {
        audioRef.current = null;
        speakWithBrowser(text, onDone);
      };
      audio.play().catch(() => speakWithBrowser(text, onDone));
    },
    [speakWithBrowser, stop],
  );

  useEffect(() => stop, [stop]);

  return { play, stop };
}
