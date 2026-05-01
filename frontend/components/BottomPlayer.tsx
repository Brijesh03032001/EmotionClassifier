"use client";

import { usePlayer } from "@/lib/player-context";
import { Play, Pause, SkipBack, SkipForward, Music2, ExternalLink } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function BottomPlayer() {
  const { track, isPlaying, pause, resume, next, prev, audioRef } = usePlayer();
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(30);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    function onMeta() {
      if (audio) setDuration(audio.duration || 30);
    }

    function tick() {
      if (audio) setProgress(audio.currentTime);
      rafRef.current = requestAnimationFrame(tick);
    }

    if (isPlaying) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    }

    audio.addEventListener("loadedmetadata", onMeta);
    return () => {
      audio.removeEventListener("loadedmetadata", onMeta);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, audioRef]);

  function seek(e: React.MouseEvent<HTMLDivElement>) {
    const audio = audioRef.current;
    if (!audio) return;
    const rect = e.currentTarget.getBoundingClientRect();
    audio.currentTime = ((e.clientX - rect.left) / rect.width) * (duration || 30);
  }

  const fmtTime = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  const progressPct = duration ? (progress / duration) * 100 : 0;

  return (
    <AnimatePresence>
      {track && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 28 }}
          className="fixed bottom-0 left-0 right-0 z-50"
          style={{
            background: "rgba(13, 5, 23, 0.85)",
            backdropFilter: "blur(40px)",
            WebkitBackdropFilter: "blur(40px)",
            borderTop: "1px solid rgba(188,150,230,0.15)",
          }}
        >
          {/* Seek bar */}
          <div
            className="h-1 w-full bg-white/5 cursor-pointer group/seek"
            onClick={seek}
          >
            <div
              className="h-full relative transition-none"
              style={{
                width: `${progressPct}%`,
                background: "linear-gradient(90deg, #BC96E6, #AE759F)",
              }}
            >
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow-lg shadow-[#BC96E6]/40 opacity-0 group-hover/seek:opacity-100 transition-opacity scale-0 group-hover/seek:scale-100" />
            </div>
          </div>

          <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
            {/* Track info */}
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <motion.div
                animate={isPlaying ? { rotate: 360 } : { rotate: 0 }}
                transition={isPlaying ? { duration: 4, repeat: Infinity, ease: "linear" } : {}}
                className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-[#55286F] to-[#210B2C] flex items-center justify-center border border-[#BC96E6]/20"
              >
                <Music2 className="w-4 h-4 text-[#BC96E6]" />
              </motion.div>
              <div className="min-w-0">
                <AnimatePresence mode="wait">
                  <motion.p
                    key={track.track_id ?? track.title}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    className="text-white text-sm font-medium truncate"
                  >
                    {track.title}
                  </motion.p>
                </AnimatePresence>
                <p className="text-[#AE759F]/60 text-xs truncate">{track.artist}</p>
              </div>
              {track.deezer_link && (
                <a
                  href={track.deezer_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-[#AE759F]/30 hover:text-[#BC96E6] transition-colors hidden sm:block"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>

            {/* Controls */}
            <div className="flex items-center gap-5">
              <motion.button
                whileHover={{ scale: 1.15 }}
                whileTap={{ scale: 0.9 }}
                onClick={prev}
                className="text-[#AE759F]/50 hover:text-[#BC96E6] transition-colors"
              >
                <SkipBack className="w-5 h-5" />
              </motion.button>

              <motion.button
                whileHover={{ scale: 1.08 }}
                whileTap={{ scale: 0.93 }}
                onClick={isPlaying ? pause : resume}
                className="w-11 h-11 rounded-full flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, #BC96E6, #AE759F)",
                  boxShadow: "0 4px 24px rgba(188,150,230,0.35)",
                }}
              >
                {isPlaying ? (
                  <Pause className="w-4 h-4 text-[#210B2C]" />
                ) : (
                  <Play className="w-4 h-4 text-[#210B2C] ml-0.5" />
                )}
              </motion.button>

              <motion.button
                whileHover={{ scale: 1.15 }}
                whileTap={{ scale: 0.9 }}
                onClick={next}
                className="text-[#AE759F]/50 hover:text-[#BC96E6] transition-colors"
              >
                <SkipForward className="w-5 h-5" />
              </motion.button>
            </div>

            {/* Time */}
            <div className="hidden md:flex items-center gap-2 text-xs text-[#AE759F]/40 font-mono flex-1 justify-end">
              <span>{fmtTime(progress)}</span>
              <span className="text-[#AE759F]/20">/</span>
              <span>{fmtTime(duration)}</span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
