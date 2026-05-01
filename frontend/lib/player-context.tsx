"use client";

import React, { createContext, useContext, useState, useRef, useCallback } from "react";
import type { Track } from "./api";

interface PlayerState {
  track: Track | null;
  isPlaying: boolean;
  queue: Track[];
}

interface PlayerContextValue extends PlayerState {
  play: (track: Track, queue?: Track[]) => void;
  pause: () => void;
  resume: () => void;
  next: () => void;
  prev: () => void;
  audioRef: React.RefObject<HTMLAudioElement | null>;
}

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<PlayerState>({
    track: null,
    isPlaying: false,
    queue: [],
  });
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = useCallback((track: Track, queue: Track[] = []) => {
    setState({ track, isPlaying: true, queue });
    if (audioRef.current && track.preview_url) {
      audioRef.current.src = track.preview_url;
      audioRef.current.play().catch(() => {});
    }
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
    setState((s) => ({ ...s, isPlaying: false }));
  }, []);

  const resume = useCallback(() => {
    audioRef.current?.play().catch(() => {});
    setState((s) => ({ ...s, isPlaying: true }));
  }, []);

  const next = useCallback(() => {
    setState((s) => {
      const idx = s.queue.findIndex((t) => t.track_id === s.track?.track_id);
      const nextTrack = s.queue[idx + 1] ?? null;
      if (nextTrack && nextTrack.preview_url && audioRef.current) {
        audioRef.current.src = nextTrack.preview_url;
        audioRef.current.play().catch(() => {});
      }
      return { ...s, track: nextTrack ?? s.track, isPlaying: !!nextTrack };
    });
  }, []);

  const prev = useCallback(() => {
    setState((s) => {
      const idx = s.queue.findIndex((t) => t.track_id === s.track?.track_id);
      const prevTrack = s.queue[idx - 1] ?? null;
      if (prevTrack && prevTrack.preview_url && audioRef.current) {
        audioRef.current.src = prevTrack.preview_url;
        audioRef.current.play().catch(() => {});
      }
      return { ...s, track: prevTrack ?? s.track, isPlaying: !!prevTrack };
    });
  }, []);

  return (
    <PlayerContext.Provider value={{ ...state, play, pause, resume, next, prev, audioRef }}>
      {children}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={next} />
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used inside PlayerProvider");
  return ctx;
}
