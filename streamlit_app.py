"""
Streamlit frontend for the EmotionClassifier Playlist API.

Usage (after starting the API):
    emclass/bin/streamlit run streamlit_app.py
"""

import requests
import streamlit as st

API_URL = "http://localhost:8000"


@st.cache_data(ttl=3600, show_spinner=False)
def _fresh_preview_url(track_id: str) -> str | None:
    """Fetch a live Deezer preview URL using the public Deezer API (no auth needed).
    Results are cached for 1 hour to avoid hammering the API."""
    try:
        r = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=5)
        if r.status_code == 200:
            return r.json().get("preview")  # 30-second MP3 URL
    except Exception:
        pass
    return None


CLUSTER_COLORS = {
    "Calm / Relaxed": "#4A90D9",
    "Hype / Energetic": "#E85D5D",
    "Cheerful / Uplifting": "#F5A623",
    "Tense / Intense": "#9B59B6",
    "Unknown": "#888888",
}

CLUSTER_EMOJI = {
    "Calm / Relaxed": "🌙",
    "Hype / Energetic": "⚡",
    "Cheerful / Uplifting": "☀️",
    "Tense / Intense": "🌀",
    "Unknown": "🎵",
}

EXAMPLE_PROMPTS = [
    "I'm feeling anxious. Help me calm down.",
    "My energy is low. Hype me up hard.",
    "Need soft sleepy songs to fall asleep quickly.",
    "I'm working out. Give me intense bangers.",
    "Take me from stressed to calm and focused.",
    "Feeling sad. Lift my mood with something hopeful.",
    "Explore something new I haven't heard before.",
    "I need deep focus music for studying.",
]

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EmotionClassifier · Playlist",
    page_icon="🎵",
    layout="centered",
)

st.markdown(
    """
<style>
.track-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 5px solid var(--accent);
}
.track-title { font-size: 1.05rem; font-weight: 700; color: #fff; }
.track-artist { font-size: 0.9rem; color: #aaa; margin-bottom: 6px; }
.track-meta { font-size: 0.8rem; color: #ccc; }
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 6px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🎵 EmotionClassifier")
st.caption("Type how you feel — get a playlist that matches.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    top_n = st.slider("Tracks to return", 1, 10, 5)
    vibe_hint = st.selectbox(
        "Vibe hint (optional)",
        [
            "— auto-detect —",
            "calm",
            "melancholic",
            "relaxing",
            "focus",
            "sleep",
            "cheerful",
            "hopeful",
            "euphoric",
            "hype",
            "workout",
            "anxious",
        ],
    )
    vibe = "" if vibe_hint == "— auto-detect —" else vibe_hint

    st.divider()
    st.header("💡 Example prompts")
    for ex in EXAMPLE_PROMPTS:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state["prompt_input"] = ex

    st.divider()
    st.caption("API: " + API_URL)

# ---------------------------------------------------------------------------
# Main input
# ---------------------------------------------------------------------------
prompt = st.text_area(
    "Your mood / request",
    value=st.session_state.get("prompt_input", ""),
    placeholder="e.g. I'm feeling anxious. Help me calm down.",
    height=90,
    key="prompt_input",
)

col_btn, col_clear = st.columns([3, 1])
with col_btn:
    submitted = st.button(
        "🎧 Generate Playlist", type="primary", use_container_width=True
    )
with col_clear:
    if st.button("Clear", use_container_width=True):
        st.session_state["prompt_input"] = ""
        st.rerun()

# ---------------------------------------------------------------------------
# API call + results
# ---------------------------------------------------------------------------
if submitted:
    if not prompt.strip():
        st.warning("Please enter a mood or request first.")
    else:
        with st.spinner("Finding your songs…"):
            try:
                resp = requests.post(
                    f"{API_URL}/playlist",
                    json={"prompt": prompt.strip(), "vibe": vibe, "top_n": top_n},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.exceptions.ConnectionError:
                st.error(
                    "Cannot reach the API. Start it with:\n\n"
                    "`emclass/bin/uvicorn api:app --reload --port 8000`"
                )
                st.stop()
            except requests.exceptions.HTTPError as e:
                st.error(f"API error {resp.status_code}: {resp.text}")
                st.stop()

        # Intent summary
        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Intent type", data["intent_type"].replace("-", " ").title())
        with c2:
            tr = data.get("tempo_range")
            st.metric("Tempo range (BPM)", f"{tr[0]}–{tr[1]}" if tr else "—")
        with c3:
            er = data.get("energy_range")
            st.metric("Energy range", f"{er[0]:.2f}–{er[1]:.2f}" if er else "—")

        st.subheader(f"🎶 Your playlist ({len(data['tracks'])} tracks)")

        # Energy bar chart
        if data["tracks"]:
            import pandas as pd

            chart_df = pd.DataFrame(
                [
                    {
                        "#": f"{t['position']}. {t['title'][:28]}…"
                        if len(t["title"] or "") > 28
                        else f"{t['position']}. {t['title']}",
                        "Energy": t["energy"],
                        "Tempo": t["tempo"],
                    }
                    for t in data["tracks"]
                ]
            )
            with st.expander("📊 Energy & Tempo chart", expanded=True):
                tab1, tab2 = st.tabs(["Energy", "Tempo"])
                with tab1:
                    st.bar_chart(chart_df.set_index("#")["Energy"])
                with tab2:
                    st.bar_chart(chart_df.set_index("#")["Tempo"])

        # Track cards
        for t in data["tracks"]:
            label = t.get("cluster_label", "Unknown")
            color = CLUSTER_COLORS.get(label, "#888")
            emoji = CLUSTER_EMOJI.get(label, "🎵")
            note = t.get("transition_note", "")
            note_html = f"&nbsp;&nbsp;·&nbsp;&nbsp;<em>{note}</em>" if note else ""
            preview = t.get("preview_url")
            # Deezer CDN URLs expire — refresh via public API using track_id
            if t.get("track_id"):
                fresh = _fresh_preview_url(str(t["track_id"]))
                if fresh:
                    preview = fresh

            st.markdown(
                f"""
<div class="track-card" style="--accent:{color};">
  <div class="track-title">{t["position"]}. {t.get("title", "—")}</div>
  <div class="track-artist">{t.get("artist", "—")}</div>
  <div class="track-meta">
    <span class="badge" style="background:{color}22;color:{color};">{emoji} {label}</span>
    &nbsp;⚡ Energy <strong>{t["energy"]:.2f}</strong>
    &nbsp;🥁 Tempo <strong>{t["tempo"]:.0f} BPM</strong>
    &nbsp;⭐ Score <strong>{t["final_score"]:.3f}</strong>
    {note_html}
  </div>
  {('<div style="margin-top:8px;"><a href="' + t["deezer_link"] + '" target="_blank" style="color:' + color + ';font-size:0.82rem;text-decoration:none;">🔗 Open on Deezer</a></div>') if t.get("deezer_link") else ""}
</div>
""",
                unsafe_allow_html=True,
            )
            if preview:
                st.audio(preview, format="audio/mp3")
            elif t.get("deezer_link"):
                st.markdown(f"[▶ Listen on Deezer]({t['deezer_link']})")

        # Raw JSON expander
        with st.expander("🔍 Raw API response"):
            st.json(data)
