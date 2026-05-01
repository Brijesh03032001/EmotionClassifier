"use client";

import Link from "next/link";
import { Music2 } from "lucide-react";
import { motion } from "framer-motion";

export default function Navbar() {
  return (
    <motion.header
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="fixed top-0 left-0 right-0 z-50"
      style={{
        background: "rgba(13, 5, 23, 0.7)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        borderBottom: "1px solid rgba(188,150,230,0.1)",
      }}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#BC96E6] to-[#AE759F] flex items-center justify-center shadow-lg shadow-[#BC96E6]/25 group-hover:shadow-[#BC96E6]/40 transition-shadow">
            <Music2 className="w-4 h-4 text-[#210B2C]" />
          </div>
          <span
            className="text-xl font-bold tracking-tight text-white"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            Moodify
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm text-[#D8B4E2]/50">
          {["Discover", "Moods", "About"].map((item) => (
            <a
              key={item}
              href={`#${item.toLowerCase()}`}
              className="hover:text-[#BC96E6] transition-colors relative group/nav"
            >
              {item}
              <span className="absolute -bottom-0.5 left-0 w-0 h-px bg-[#BC96E6] group-hover/nav:w-full transition-all duration-300" />
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass text-xs text-[#BC96E6] border border-[#BC96E6]/20">
          <span className="w-1.5 h-1.5 rounded-full bg-[#BC96E6] animate-pulse" />
          AI Active
        </div>
      </div>
    </motion.header>
  );
}
