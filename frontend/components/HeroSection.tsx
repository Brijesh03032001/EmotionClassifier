"use client";

import { useState, useRef } from "react";
import { Search, Loader2, Sparkles, ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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
  { key: "epic", emoji: "🔥" },
  { key: "sleep", emoji: "🌙" },
];

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1, delayChildren: 0.2 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
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
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="flex flex-col items-center w-full max-w-3xl"
        >
          {/* Badge */}
          <motion.div variants={fadeUp} className="mb-8">
            <div className="flex items-center gap-2 px-4 py-2 glass rounded-full text-sm text-[#BC96E6] border border-[#BC96E6]/20">
              <Sparkles className="w-3.5 h-3.5" />
              <span>AI-Powered Emotion Music Retrieval</span>
            </div>
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={fadeUp}
            className="text-center text-6xl sm:text-7xl md:text-8xl font-black leading-[1.0] mb-6 tracking-tight"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            <span className="text-white">Music that </span>
            <br />
            <span className="italic gradient-text glow-text">feels right.</span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="text-center text-[#D8B4E2]/50 text-xl max-w-lg mb-12 leading-relaxed"
          >
            Describe your mood in plain English. Our AI finds the perfect tracks to
            match how you feel — not just what you typed.
          </motion.p>

          {/* Search box */}
          <motion.form
            variants={fadeUp}
            onSubmit={handleSubmit}
            className="w-full glass-strong rounded-2xl p-2 relative"
            style={{ boxShadow: "0 0 0 1px rgba(188,150,230,0.2), 0 20px 60px rgba(33,11,44,0.6)" }}
          >
            {/* Animated border glow on focus */}
            <div className="flex flex-col gap-2">
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
                className="w-full bg-transparent px-4 pt-3 pb-1 text-white placeholder-[#AE759F]/40 resize-none outline-none text-base leading-relaxed"
              />
              <div className="flex items-center justify-between px-3 pb-2 gap-2">
                <div className="flex flex-wrap gap-1.5 flex-1 min-w-0">
                  {VIBES.slice(0, 5).map((v) => (
                    <motion.button
                      key={v.key}
                      type="button"
                      whileTap={{ scale: 0.93 }}
                      onClick={() => setVibe(vibe === v.key ? null : v.key)}
                      className={`px-2.5 py-0.5 rounded-full text-xs transition-all ${
                        vibe === v.key
                          ? "bg-[#BC96E6] text-[#210B2C] font-semibold shadow-lg shadow-[#BC96E6]/20"
                          : "glass text-[#D8B4E2]/60 hover:text-[#BC96E6] hover:border-[#BC96E6]/30"
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
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-[#BC96E6] to-[#AE759F] text-[#210B2C] font-semibold text-sm hover:opacity-90 disabled:opacity-40 transition-opacity shadow-lg shadow-[#BC96E6]/25 shrink-0"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Search className="w-4 h-4" />
                  )}
                  {loading ? "Finding..." : "Find Music"}
                </motion.button>
              </div>
            </div>
          </motion.form>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-4 px-4 py-3 rounded-xl bg-red-900/30 border border-red-500/30 text-red-300 text-sm w-full"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Example prompts */}
          <motion.div variants={fadeUp} className="mt-8 w-full">
            <p className="text-[10px] text-[#AE759F]/40 mb-3 text-center uppercase tracking-[0.2em]">
              Try an example
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {EXAMPLE_PROMPTS.map((p) => (
                <motion.button
                  key={p}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => {
                    setPrompt(p);
                    inputRef.current?.focus();
                  }}
                  className="px-3 py-1.5 glass rounded-full text-xs text-[#D8B4E2]/60 hover:text-[#BC96E6] hover:border-[#BC96E6]/25 transition-colors"
                >
                  {p}
                </motion.button>
              ))}
            </div>
          </motion.div>
        </motion.div>

        {/* Scroll cue */}
        <AnimatePresence>
          {!result && (
            <motion.a
              href="#moods"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ delay: 1.5 }}
              className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 text-[#AE759F]/30 hover:text-[#BC96E6] transition-colors text-xs"
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
                  className="text-2xl font-bold text-white mb-1"
                  style={{ fontFamily: "var(--font-heading)" }}
                >
                  Your Playlist
                </h2>
                <p className="text-[#AE759F]/60 text-sm">
                  &ldquo;{result.prompt}&rdquo; &middot; {result.tracks.length} tracks &middot;{" "}
                  <span className="text-[#BC96E6]/70">{result.generation_ms}ms</span>
                </p>
              </div>
              {result.tracks[0] && (
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => play(result.tracks[0], result.tracks)}
                  className="px-4 py-2 glass rounded-xl text-[#BC96E6] text-sm border border-[#BC96E6]/20 hover:bg-[#BC96E6]/10 transition-all shrink-0"
                >
                  ▶ Play All
                </motion.button>
              )}
            </motion.div>

            {/* Track list */}
            <motion.div
              variants={{ show: { transition: { staggerChildren: 0.05 } } }}
              initial="hidden"
              animate="show"
              className="flex flex-col gap-2"
            >
              {result.tracks.map((track, i) => (
                <motion.div
                  key={track.track_id ?? i}
                  variants={{
                    hidden: { opacity: 0, x: -16 },
                    show: { opacity: 1, x: 0, transition: { type: "spring", stiffness: 200, damping: 22 } },
                  }}
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
