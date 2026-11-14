import { useCallback, useRef, useState } from "react";
import { api, ApiError, type Turn } from "../api/client";
import { useAudioPlayer } from "./useAudioPlayer";
import { MicError, useRecorder } from "./useRecorder";

export type VoiceStatus = "idle" | "listening" | "thinking" | "speaking";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

let localId = 0;
const nextId = () => `m${++localId}`;

export function useVoiceAssistant(onLevel: (level: number) => void) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [handsFree, setHandsFree] = useState(true);
  const conversationRef = useRef<string | null>(null);
  const handsFreeRef = useRef(handsFree);
  handsFreeRef.current = handsFree;
  const recorder = useRecorder(onLevel);
  const player = useAudioPlayer();
  const listenRef = useRef<() => void>(() => undefined);

  const append = (role: ChatMessage["role"], text: string) =>
    setMessages((current) => [...current, { id: nextId(), role, text }]);

  const respond = useCallback(
    (turn: Turn, fromVoice: boolean) => {
      if (turn.conversation_id) conversationRef.current = turn.conversation_id;
      if (turn.transcript && fromVoice) append("user", turn.transcript);
      append("assistant", turn.reply);
      setStatus("speaking");
      player.play(turn.audio_url, turn.reply, () => {
        setStatus("idle");
        if (fromVoice && handsFreeRef.current && turn.reply_message_id) listenRef.current();
      });
    },
    [player],
  );

  const fail = (err: unknown) => {
    setStatus("idle");
    setError(err instanceof MicError || err instanceof ApiError ? err.message : "Something went wrong. Try again.");
  };

  const listen = useCallback(async () => {
    player.stop();
    setError(null);
    setStatus("listening");
    try {
      const audio = await recorder.record();
      if (!audio) return setStatus("idle");
      setStatus("thinking");
      respond(await api.voiceTurn(audio, conversationRef.current), true);
    } catch (err) {
      fail(err);
    }
  }, [player, recorder, respond]);
  listenRef.current = () => void listen();

  const sendText = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      player.stop();
      setError(null);
      append("user", trimmed);
      setStatus("thinking");
      try {
        respond(await api.chatTurn(trimmed, conversationRef.current), false);
      } catch (err) {
        fail(err);
      }
    },
    [player, respond],
  );

  const interrupt = useCallback(() => {
    if (status === "listening") recorder.stop();
    if (status === "speaking") {
      player.stop();
      setStatus("idle");
    }
  }, [player, recorder, status]);

  const reset = useCallback(() => {
    player.stop();
    recorder.stop();
    conversationRef.current = null;
    setMessages([]);
    setStatus("idle");
    setError(null);
  }, [player, recorder]);

  return { status, messages, error, handsFree, setHandsFree, listen, sendText, interrupt, reset };
}
