/**
 * Plays server TTS audio, falling back to the browser voice if the audio can't load.
 * Only one voice ever plays: each play gets a token, and callbacks from an older play are ignored.
 */
export interface VoicePlayer {
  play(url: string | null, text: string, onDone: () => void): void;
  stop(): void;
}

export function createVoicePlayer(makeAudio: (url: string) => HTMLAudioElement = (url) => new Audio(url)): VoicePlayer {
  let current: HTMLAudioElement | null = null;
  let token = 0;
  const synth = () => (typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null);

  const stop = () => {
    token += 1;
    const audio = current;
    current = null;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    synth()?.cancel();
  };

  const play = (url: string | null, text: string, onDone: () => void) => {
    stop();
    const mine = token;
    const isCurrent = () => mine === token;
    let settled = false;
    let fellBack = false;

    const finish = () => {
      if (settled || !isCurrent()) return;
      settled = true;
      current = null;
      onDone();
    };

    const speakWithBrowser = () => {
      if (fellBack || settled || !isCurrent()) return;
      fellBack = true;
      current?.pause();
      current = null;
      const speech = synth();
      if (!speech) return finish();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-IN";
      utterance.onend = finish;
      utterance.onerror = finish;
      speech.speak(utterance);
    };

    if (!url) return speakWithBrowser();
    const audio = makeAudio(url);
    current = audio;
    audio.onended = finish;
    audio.onerror = speakWithBrowser;
    audio.play().catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      speakWithBrowser();
    });
  };

  return { play, stop };
}
