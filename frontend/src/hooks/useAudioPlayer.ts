import { useEffect, useMemo } from "react";
import { createVoicePlayer } from "../lib/voicePlayer";

export function useAudioPlayer() {
  const player = useMemo(() => createVoicePlayer(), []);
  useEffect(() => player.stop, [player]);
  return player;
}
