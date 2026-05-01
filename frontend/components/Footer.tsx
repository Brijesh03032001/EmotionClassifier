import { Music2, GitBranch } from "lucide-react";

export default function Footer() {
  return (
    <footer
      id="about"
      className="border-t border-[rgba(188,150,230,0.1)] mt-auto"
    >
      <div className="max-w-7xl mx-auto px-6 py-12 grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Brand */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#BC96E6] to-[#AE759F] flex items-center justify-center">
              <Music2 className="w-3.5 h-3.5 text-[#210B2C]" />
            </div>
            <span
              className="text-lg font-bold text-white"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              Moodify
            </span>
          </div>
          <p className="text-[#AE759F]/50 text-sm leading-relaxed max-w-xs">
            AI-powered emotional music retrieval. Describe your feeling, get
            the perfect soundtrack.
          </p>
        </div>

        {/* Tech stack */}
        <div>
          <h4 className="text-white text-sm font-semibold mb-4 uppercase tracking-wider">
            Under the Hood
          </h4>
          <ul className="space-y-2 text-[#AE759F]/60 text-sm">
            <li>sentence-transformers/all-MiniLM-L6-v2</li>
            <li>Supabase pgvector (1536-dim)</li>
            <li>FastAPI + Python 3.11</li>
            <li>Next.js 14 + shadcn/ui</li>
            <li>Deezer 30s Preview API</li>
          </ul>
        </div>

        {/* Project info */}
        <div>
          <h4 className="text-white text-sm font-semibold mb-4 uppercase tracking-wider">
            Project
          </h4>
          <ul className="space-y-2 text-[#AE759F]/60 text-sm">
            <li>Data Mining Course Project</li>
            <li>Emotion Clustering + RAG Retrieval</li>
            <li>Benchmark avg quality: 0.7180</li>
            <li>Precision@5: 0.74</li>
          </ul>
          <div className="mt-4 flex items-center gap-2 text-[#AE759F]/40 text-xs">
            <GitBranch className="w-3.5 h-3.5" />
            <span>emotion-classifier</span>
          </div>
        </div>
      </div>

      <div className="border-t border-[rgba(188,150,230,0.08)] py-4">
        <p className="text-center text-[#AE759F]/30 text-xs">
          30-second previews via Deezer API &middot; No audio stored &middot; For educational use
        </p>
      </div>
    </footer>
  );
}
