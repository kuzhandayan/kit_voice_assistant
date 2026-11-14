import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createVoicePlayer } from "./voicePlayer";

class FakeAudio {
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  paused = false;
  rejectPlay: (err: unknown) => void = () => undefined;
  play = () => new Promise<void>((_, reject) => (this.rejectPlay = reject));
  pause = () => void (this.paused = true);
  removeAttribute = () => undefined;
  load = () => undefined;
}

const spoken: string[] = [];
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  spoken.length = 0;
  vi.stubGlobal("SpeechSynthesisUtterance", class { constructor(public text: string) {} lang = ""; onend = null; onerror = null; });
  vi.stubGlobal("window", { speechSynthesis: { speak: (u: { text: string }) => spoken.push(u.text), cancel: vi.fn() } });
});
afterEach(() => vi.unstubAllGlobals());

function setup() {
  const audios: FakeAudio[] = [];
  const player = createVoicePlayer(() => {
    const audio = new FakeAudio();
    audios.push(audio);
    return audio as unknown as HTMLAudioElement;
  });
  return { player, audios };
}

describe("voice player", () => {
  it("does not speak an old reply when a new play interrupts a loading one", async () => {
    const { player, audios } = setup();
    player.play("/a", "old reply", vi.fn());
    player.play("/b", "new reply", vi.fn());
    audios[0].rejectPlay(new Error("interrupted"));
    await flush();
    expect(spoken).toEqual([]);
    expect(audios[0].paused).toBe(true);
  });

  it("does not speak after stop, even if the old audio errors", async () => {
    const { player, audios } = setup();
    const done = vi.fn();
    player.play("/a", "reply", done);
    player.stop();
    audios[0].onerror?.();
    audios[0].rejectPlay(new Error("aborted"));
    await flush();
    expect(spoken).toEqual([]);
    expect(done).not.toHaveBeenCalled();
  });

  it("falls back to the browser voice once when load fails both ways", async () => {
    const { player, audios } = setup();
    player.play("/a", "reply", vi.fn());
    audios[0].onerror?.();
    audios[0].rejectPlay(new Error("not supported"));
    await flush();
    expect(spoken).toEqual(["reply"]);
  });

  it("calls done once when audio ends", () => {
    const { player, audios } = setup();
    const done = vi.fn();
    player.play("/a", "reply", done);
    audios[0].onended?.();
    audios[0].onended?.();
    expect(done).toHaveBeenCalledTimes(1);
  });
});
