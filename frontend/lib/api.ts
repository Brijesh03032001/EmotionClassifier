export interface Track {
  position: number;
  track_id: string | null;
  title: string | null;
  artist: string | null;
  tempo: number;
  energy: number;
  brightness: number;
  emotion_cluster: number | null;
  cluster_label: string;
  similarity: number;
  final_score: number;
  transition_note: string;
  preview_url: string | null;
  deezer_link: string | null;
}

export interface PlaylistResponse {
  prompt: string;
  vibe: string;
  inferred_vibe: string;
  intent_type: string;
  tempo_range: [number, number] | null;
  energy_range: [number, number] | null;
  tracks: Track[];
  generation_ms: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchPlaylist(
  prompt: string,
  vibe?: string | null,
  topN = 10
): Promise<PlaylistResponse> {
  const res = await fetch(`${API_BASE}/playlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, vibe: vibe || "", top_n: topN }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function fetchVibes(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/vibes`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  // API returns { vibes: string[], tip: string }
  return Array.isArray(data) ? data : (data.vibes ?? []);
}
