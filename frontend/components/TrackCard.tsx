"use client";

import { usePlayer } from "@/lib/player-context";
import type { Track } from "@/lib/api";
import { Play, Pause, ExternalLink, Zap } from "lucide-react";
import { motion } from "framer-motion";

const CLUSTER_COLORS: Record<number, { primary: string; bg: string; glow: string }> = {
  0: { primary: "#7EC8E3", bg: "rgba(126,200,227,0.12)", glow: "rgba(126,200,227,0.2)" },
  1: { primary: "#BC96E6", bg: "rgba(188,150,230,0.12)", glow: "rgba(188,150,230,0.2)" },
  2: { primary: "#F9D56E", bg: "rgba(249,213,110,0.12)", glow: "rgba(249,213,110,0.2)" },
  3: { primary: "#FF6B6B", bg: "rgba(255,107,107,0.12)", glow: "rgba(255,107,107,0.2)" },
  4: { primary: "#AE759F", bg: "rgba(174,117,159,0.12)", glow: "rgba(174,117,159,0.2)" },
  5: { primary: "#69D2E7", bg: "rgba(105,210,231,0.12)", glow: "rgba(105,210,231,0.2)" },
  6: { primary: "#E8A0BF", bg: "rgba(232,160,191,0.12)", glow: "rgba(232,160,191,0.2)" },
  7: { primary: "#A8BFFF", bg: "rgba(168,191,255,0.12)", glow: "rgba(168,191,255,0.2)" },
};

function WaveformBars({ playing }: { playing: boolean }) {
  return (
    <div className="flex items-center gap-[2px] h-4">
      {[0, 0.1, 0.2, 0.1, 0.15].map((delay, i) => (
        <div
          key={i}
          className="wave-bar"
          style={{
            animationDelay: `${delay}s`,
            animationPlayState: playing ? "running" : "paused",
            height: playing ? undefined : "4px",
          }}
        />
      ))}
    </div>
  );
}

interface TrackCardProps {
  track: Track;
  queue: Track[];
}

export default function TrackCard({ track, queue }: TrackCardProps) {
  const { play, pause, resume, track: currentTrack, isPlaying } = usePlayer();
  const isCurrent = currentTrack?.track_id != null && currentTrack.track_id === track.track_id;
  const isThisPlaying = isCurrent && isPlaying;

  const clusterIdx = (track.emotion_cluster ?? 0) % 8;
  const colors = CLUSTER_COLORS[clusterIdx] ?? CLUSTER_COLORS[1];

  function handlePlay() {
    if (isCurrent) {
      isPlaying ? pause() : resume();
    } else {
      play(track, queue);
    }
  }

  const energyPct = Math.round((track.energy ?? 0) * 100);
  const scorePct = Math.round((track.final_score ?? 0) * 100);

  return (
    <motion.div
      layout
      className={`relative group rounded-2xl overflow-hidden cursor-default ${
        isCurrent ? "glass-card-active" : "glass-card"
      }`}
      whileHover={{ scale: 1.01 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
    >
      {/* Active track: left accent bar */}
      {isCurrent && (
        <motion.div
          layoutId="active-bar"
          className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-full"
          style={{ background: `linear-gradient(180deg, ${colors.primary}, transparent)` }}
        />
      )}

      {/* Hover glow layer */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
        style={{ background: `radial-gradient(ellipse at 20% 50%, ${colors.glow} 0%, transparent 60%)` }}
      />

      <div className="relative flex items-center gap-4 px-5 py-4">
        {/* Position / waveform */}
        <div className="w-6 shrink-0 flex justify-center">
          {isCurrent ? (
            <WaveformBars playing={isThisPlaying} />
          ) : (
            <span className="text-sm text-[#c8a0e0]/50 font-mono group-hover:opacity-0 transition-opacity">
              {track.position}
            </span>
          )}
        </div>

        {/* Play button */}
        <motion.button
          onClick={handlePlay}
          disabled={!track.preview_url}
          whileHover={{ scale: track.preview_url ? 1.1 : 1 }}
          whileTap={{ scale: 0.93 }}
          className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all"
          style={
            track.preview_url
              ? {
                  background: `linear-gradient(135deg, ${colors.primary}CC, ${colors.primary}88)`,
                  boxShadow: `0 4px 20px ${colors.glow}`,
                }
              : { background: "rgba(188,150,230,0.08)" }
          }
          title={track.preview_url ? "Play preview" : "No preview available"}
        >
          {isThisPlaying ? (
            <Pause className="w-3.5 h-3.5 text-[#210B2C]" />
          ) : (
            <Play className="w-3.5 h-3.5 text-[#210B2C] ml-0.5" />
          )}
        </motion.button>

        {/* Track info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-white font-semibold truncate text-sm leading-snug">
              {track.title}
            </span>
            {isCurrent && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full font-bold tracking-wider shrink-0"
                style={{ background: colors.bg, color: colors.primary }}
              >
                NOW PLAYING
              </span>
            )}
          </div>
          <p className="text-[#d4aaee] text-xs truncate">{track.artist}</p>
          {track.transition_note && (
            <p className="text-[#c8a0e0]/50 text-[10px] mt-0.5 italic truncate">
              {track.transition_note}
            </p>
          )}
        </div>

        {/* Energy bar */}
        <div className="hidden sm:flex items-center gap-2 shrink-0">
          <Zap className="w-3 h-3 text-[#AE759F]/40" />
          <div className="w-14 h-1.5 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${energyPct}%` }}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
              style={{ background: `linear-gradient(90deg, ${colors.primary}66, ${colors.primary})` }}
            />
          </div>
          <span className="text-[10px] text-[#AE759F]/40 font-mono w-5">{energyPct}%</span>
        </div>

        {/* BPM */}
        <span className="hidden md:block text-xs text-[#c8a0e0]/60 font-mono w-16 text-right shrink-0">
          {Math.round(track.tempo ?? 0)} BPM
        </span>

        {/* Score badge */}
        <div
          className="hidden sm:block px-2.5 py-1 rounded-full text-[10px] font-bold shrink-0"
          style={{ background: colors.bg, color: colors.primary, border: `1px solid ${colors.primary}30` }}
        >
          {scorePct}%
        </div>

        {/* Cluster label */}
        <div
          className="hidden lg:block text-[10px] px-2 py-0.5 rounded-full shrink-0"
          style={{ background: colors.bg, color: colors.primary }}
        >
          {track.cluster_label}
        </div>

        {/* Deezer link */}
        {track.deezer_link && (
          <a
            href={track.deezer_link}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-[#AE759F]/40 hover:text-[#BC96E6]"
            onClick={(e) => e.stopPropagation()}
            title="Open on Deezer"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </motion.div>
  );
}
