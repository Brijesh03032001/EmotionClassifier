"use client";

import { motion } from "framer-motion";

const MOODS = [
  { label: "Energetic", emoji: "⚡", desc: "High-BPM bangers to get you moving", color: "#BC96E6", glow: "rgba(188,150,230,0.3)" },
  { label: "Chill", emoji: "🌊", desc: "Easy, breezy, go-with-the-flow vibes", color: "#7EC8E3", glow: "rgba(126,200,227,0.3)" },
  { label: "Focus", emoji: "🎯", desc: "Deep work sessions, zero distractions", color: "#D8B4E2", glow: "rgba(216,180,226,0.3)" },
  { label: "Melancholic", emoji: "🌧", desc: "Beautiful sadness — feel it fully", color: "#9B59B6", glow: "rgba(155,89,182,0.3)" },
  { label: "Happy", emoji: "☀️", desc: "Pure sunshine, feel-good anthems", color: "#F9D56E", glow: "rgba(249,213,110,0.3)" },
  { label: "Romantic", emoji: "🌹", desc: "Slow burns and heart-flutter moments", color: "#E8A0BF", glow: "rgba(232,160,191,0.3)" },
  { label: "Epic", emoji: "🔥", desc: "Cinematic hype for big moments", color: "#FF6B6B", glow: "rgba(255,107,107,0.3)" },
  { label: "Sleep", emoji: "🌙", desc: "Soft and slow — drift away peacefully", color: "#A8BFFF", glow: "rgba(168,191,255,0.3)" },
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.07, delayChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 30, scale: 0.95 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: "spring", stiffness: 200, damping: 20 } },
};

interface MoodBrowseProps {
  onSelect: (mood: string) => void;
}

export default function MoodBrowse({ onSelect }: MoodBrowseProps) {
  return (
    <section id="moods" className="max-w-7xl mx-auto px-6 py-28 w-full">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.6 }}
        className="mb-16 text-center"
      >
        <div className="inline-flex items-center gap-2 px-4 py-1.5 glass rounded-full text-xs text-[#BC96E6] border border-[#BC96E6]/20 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-[#BC96E6] animate-pulse" />
          8 emotion profiles trained on 10K+ tracks
        </div>
        <h2
          className="text-5xl md:text-6xl font-black text-white mb-4 leading-tight"
          style={{ fontFamily: "var(--font-heading)" }}
        >
          Browse by{" "}
          <span className="italic gradient-text">Mood</span>
        </h2>
        <p className="text-[#AE759F]/60 text-lg max-w-md mx-auto">
          Pick a vibe and describe your moment — the AI handles the rest.
        </p>
      </motion.div>

      <motion.div
        variants={container}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4"
      >
        {MOODS.map((mood) => (
          <motion.button
            key={mood.label}
            variants={item}
            whileHover={{ scale: 1.04, y: -4 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onSelect(mood.label.toLowerCase())}
            className="relative glass-card rounded-2xl p-6 text-left overflow-hidden group"
            style={{ "--glow": mood.glow } as React.CSSProperties}
          >
            {/* Hover glow */}
            <div
              className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-2xl pointer-events-none"
              style={{ background: `radial-gradient(circle at 30% 30%, ${mood.glow} 0%, transparent 70%)` }}
            />

            {/* Top accent line */}
            <div
              className="absolute top-0 left-0 right-0 h-[2px] opacity-0 group-hover:opacity-100 transition-opacity duration-300"
              style={{ background: `linear-gradient(90deg, transparent, ${mood.color}, transparent)` }}
            />

            <div
              className="text-2xl mb-5 w-11 h-11 flex items-center justify-center rounded-xl relative z-10"
              style={{ background: `${mood.color}18`, border: `1px solid ${mood.color}30` }}
            >
              {mood.emoji}
            </div>
            <h3
              className="text-white font-bold text-sm mb-1.5 relative z-10 transition-colors duration-200"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              {mood.label}
            </h3>
            <p className="text-[#AE759F]/55 text-xs leading-relaxed relative z-10">{mood.desc}</p>

            {/* Corner arrow */}
            <div
              className="absolute bottom-4 right-4 w-6 h-6 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 translate-x-1 group-hover:translate-x-0"
              style={{ background: `${mood.color}22`, color: mood.color }}
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2 8L8 2M8 2H3M8 2V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </motion.button>
        ))}
      </motion.div>
    </section>
  );
}
