"use client";

import { useState, useRef } from "react";
import { Search, Loader2, ChevronDown, Headphones } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";
import { fetchPlaylist, type PlaylistResponse } from "@/lib/api";
import TrackCard from "./TrackCard";
import { usePlayer } from "@/lib/player-context";

const EXAMPLE_PROMPTS = [
  "I need energy to crush my morning workout",
  "Cozy Sunday rain vibes while reading",
  "Late night drive through empty city streets",
  "Hype me up before a big presentation",
  "Melancholic but beautiful — let me feel it",
  "Focus music for deep work, no distractions",
  "Chill summer evening with friends",
  "I can't sleep, calm my restless mind",
];

const VIBES = [
  { key: "energetic", emoji: "⚡" },
  { key: "chill", emoji: "🌊" },
  { key: "melancholic", emoji: "🌧" },
  { key: "happy", emoji: "☀️" },
  { key: "focus", emoji: "🎯" },
  { key: "romantic", emoji: "🌹" },
];

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0, transition: { duration: 0.65, ease: [0.22, 1, 0.36, 1] } },
};

const slideRight = {
  hidden: { opacity: 0, x: 48, scale: 0.96 },
  show: { opacity: 1, x: 0, scale: 1, transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.3 } },
};

export default function HeroSection() {
  const [prompt, setPrompt] = useState("");
  const [vibe, setVibe] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlaylistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { play } = usePlayer();

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const q = prompt.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPlaylist(q, vibe, 10);
      setResult(data);
      setTimeout(() => {
        document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Is the API running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* ── Hero ── */}
      <section
        id="discover"
        className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16"
      >
        {/* Two-column layout */}
        <div className="w-full max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">

          {/* Left column — search + text */}
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="flex flex-col items-start"
          >
            {/* Badge */}
            <motion.div variants={fadeUp} className="mb-7">
              <div className="inline-flex items-center gap-2 px-4 py-2 glass rounded-full text-sm font-medium text-[#e8c8ff] border border-[#BC96E6]/25">
                <Headphones className="w-3.5 h-3.5 text-[#BC96E6]" />
                <span>Emotion-Driven Music Discovery</span>
              </div>
            </motion.div>

            {/* Headline */}
            <motion.h1
              variants={fadeUp}
              className="text-left text-5xl sm:text-6xl lg:text-7xl font-black leading-[1.0] mb-5 tracking-tight"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              <span className="text-white">Music that</span>
              <br />
              <span className="italic gradient-text glow-text">feels right.</span>
            </motion.h1>

            <motion.p
              variants={fadeUp}
              className="text-left text-[#e0c8f8] text-lg max-w-lg mb-10 leading-relaxed"
            >
              Describe your mood — raw, messy, complex. Our pipeline maps your words
              to audio emotion clusters and retrieves what you actually need.
            </motion.p>

            {/* Search box */}
            <motion.form
              variants={fadeUp}
              onSubmit={handleSubmit}
              className="w-full glass-strong rounded-2xl p-2"
              style={{ boxShadow: "0 0 0 1px rgba(188,150,230,0.25), 0 24px 64px rgba(13,5,23,0.7)" }}
            >
              <textarea
                ref={inputRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
                placeholder="Describe how you feel or what you need music for..."
                rows={2}
                className="w-full bg-transparent px-4 pt-3 pb-1 text-white placeholder-[#9a7ab8] resize-none outline-none text-base leading-relaxed"
              />
              <div className="flex items-center justify-between px-3 pb-2 gap-2 mt-1">
                <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
                  {VIBES.map((v) => (
                    <motion.button
                      key={v.key}
                      type="button"
                      whileTap={{ scale: 0.93 }}
                      onClick={() => setVibe(vibe === v.key ? null : v.key)}
                      className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                        vibe === v.key
                          ? "bg-[#BC96E6] text-[#210B2C] font-semibold shadow-lg shadow-[#BC96E6]/25"
                          : "glass text-[#d4aaee] hover:text-white hover:border-[#BC96E6]/40"
                      }`}
                    >
                      {v.emoji} {v.key}
                    </motion.button>
                  ))}
                </div>
                <motion.button
                  type="submit"
                  disabled={loading || !prompt.trim()}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#BC96E6] to-[#AE759F] text-[#210B2C] font-bold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity shadow-lg shadow-[#BC96E6]/30 shrink-0"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  {loading ? "Finding..." : "Find Music"}
                </motion.button>
              </div>
            </motion.form>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mt-3 px-4 py-3 rounded-xl bg-red-900/30 border border-red-500/30 text-red-200 text-sm w-full"
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Example prompts */}
            <motion.div variants={fadeUp} className="mt-7 w-full">
              <p className="text-[10px] text-[#c8a0e0]/50 mb-3 uppercase tracking-[0.2em]">
                Try an example
              </p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_PROMPTS.map((p) => (
                  <motion.button
                    key={p}
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => { setPrompt(p); inputRef.current?.focus(); }}
                    className="px-3 py-1.5 glass rounded-full text-xs text-[#d4aaee] hover:text-white hover:border-[#BC96E6]/30 transition-colors"
                  >
                    {p}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          </motion.div>

          {/* Right column — landing.png showcase */}
          <motion.div
            variants={slideRight}
            initial="hidden"
            animate="show"
            className="hidden lg:flex items-center justify-center relative"
          >
            {/* Glow backdrop */}
            <div
              className="absolute inset-0 rounded-3xl float-img-glow pointer-events-none"
              style={{
                background: "radial-gradient(ellipse at center, rgba(188,150,230,0.18) 0%, transparent 70%)",
                filter: "blur(40px)",
                transform: "scale(1.2)",
              }}
            />

            {/* Screenshot frame */}
            <div
              className="relative float-img rounded-2xl overflow-hidden"
              style={{
                boxShadow: `
                  0 0 0 1px rgba(188,150,230,0.3),
                  0 0 0 4px rgba(33,11,44,0.8),
                  0 0 0 5px rgba(188,150,230,0.15),
                  0 32px 80px rgba(13,5,23,0.8),
                  0 0 120px rgba(188,150,230,0.12)
                `,
                transform: "rotate(-1deg)",
              }}
            >
              {/* Browser-chrome top bar */}
              <div
                className="flex items-center gap-1.5 px-4 py-3"
                style={{ background: "rgba(20,8,32,0.95)", borderBottom: "1px solid rgba(188,150,230,0.1)" }}
              >
                <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                <div
                  className="ml-3 flex-1 max-w-[180px] h-5 rounded-full text-[10px] text-[#9a7ab8] flex items-center justify-center"
                  style={{ background: "rgba(188,150,230,0.08)", border: "1px solid rgba(188,150,230,0.12)" }}
                >
                  localhost:3000
                </div>
              </div>
              <Image
                src="/landing.png"
                alt="Moodify — emotion-driven playlist interface"
                width={680}
                height={420}
                className="w-full h-auto block"
                priority
              />
            </div>

            {/* Floating stat pill — top right */}
            <motion.div
              initial={{ opacity: 0, x: 20, y: -10 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{ delay: 1.1, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              className="absolute -top-4 -right-4 glass rounded-xl px-4 py-2.5 text-center"
              style={{ boxShadow: "0 8px 32px rgba(13,5,23,0.6), 0 0 0 1px rgba(188,150,230,0.2)" }}
            >
              <p className="text-2xl font-black text-white">0.74</p>
              <p className="text-[10px] text-[#c8a0e0] uppercase tracking-wider">Precision@5</p>
            </motion.div>

            {/* Floating stat pill — bottom left */}
            <motion.div
              initial={{ opacity: 0, x: -20, y: 10 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{ delay: 1.3, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              className="absolute -bottom-4 -left-4 glass rounded-xl px-4 py-2.5 text-center"
              style={{ boxShadow: "0 8px 32px rgba(13,5,23,0.6), 0 0 0 1px rgba(188,150,230,0.2)" }}
            >
              <p className="text-2xl font-black text-white">10k+</p>
              <p className="text-[10px] text-[#c8a0e0] uppercase tracking-wider">Songs indexed</p>
            </motion.div>
          </motion.div>
        </div>

        {/* Scroll cue */}
        <AnimatePresence>
          {!result && (
            <motion.a
              href="#moods"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ delay: 1.8 }}
              className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 text-[#c8a0e0]/40 hover:text-[#BC96E6] transition-colors text-xs"
            >
              <span>Explore moods</span>
              <ChevronDown className="w-4 h-4 animate-bounce" />
            </motion.a>
          )}
        </AnimatePresence>
      </section>

      {/* ── Results ── */}
      <AnimatePresence>
        {result && (
          <motion.section
            id="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="w-full max-w-4xl mx-auto px-6 pb-40"
          >
            {/* Results header */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="mb-8 flex items-start justify-between gap-4"
            >
              <div>
                <h2
                  className="text-2xl font-bold text-white mb-1.5"
                  style={{ fontFamily: "var(--font-heading)" }}
                >
                  Your Playlist
                </h2>
                <p className="text-[#c8a0e0] text-sm">
                  &ldquo;{result.prompt}&rdquo; &middot; {result.tracks.length} tracks &middot;{" "}
                  <span className="text-[#BC96E6]">{result.generation_ms}ms</span>
                </p>
              </div>
              {result.tracks[0] && (
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => play(result.tracks[0], result.tracks)}
                  className="px-4 py-2 glass rounded-xl text-[#e8c8ff] text-sm border border-[#BC96E6]/25 hover:bg-[#BC96E6]/15 transition-all shrink-0 font-medium"
                >
                  ▶ Play All
                </motion.button>
              )}
            </motion.div>

            {/* Track list — staggered entrance */}
            <motion.div
              variants={{ show: { transition: { staggerChildren: 0.07 } } }}
              initial="hidden"
              animate="show"
              className="flex flex-col gap-2.5"
            >
              {result.tracks.map((track, i) => (
                <motion.div
                  key={track.track_id ?? i}
                  variants={{
                    hidden: { opacity: 0, y: 20, scale: 0.97 },
                    show: {
                      opacity: 1,
                      y: 0,
                      scale: 1,
                      transition: {
                        type: "spring",
                        stiffness: 220,
                        damping: 24,
                        delay: i * 0.04,
                      },
                    },
                  }}
                  style={{ originY: 1 }}
                >
                  <TrackCard track={track} queue={result.tracks} />
                </motion.div>
              ))}
            </motion.div>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}
