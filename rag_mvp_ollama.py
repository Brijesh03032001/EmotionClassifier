import os
from typing import List

import ollama
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client

TABLE_RPC = "match_songs"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL = "llama3"
TARGET_VECTOR_DIM = 1536


def create_supabase_client() -> Client:
    load_dotenv(override=False)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )

    if not url or not key:
        raise EnvironmentError(
            "Missing SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY)"
        )

    return create_client(url, key)


def fit_vector_dim(
    vector: List[float], target_dim: int = TARGET_VECTOR_DIM
) -> List[float]:
    if len(vector) == target_dim:
        return vector
    if len(vector) > target_dim:
        return vector[:target_dim]
    return vector + [0.0] * (target_dim - len(vector))


def retrieve_songs(
    query: str,
    supabase: Client,
    embed_model: SentenceTransformer,
    match_threshold: float = 0.2,
    match_count: int = 5,
) -> str:
    query_vector = (
        embed_model.encode(query, convert_to_numpy=True).astype(float).tolist()
    )
    query_vector = fit_vector_dim(query_vector, TARGET_VECTOR_DIM)

    response = supabase.rpc(
        TABLE_RPC,
        {
            "query_embedding": query_vector,
            "match_threshold": match_threshold,
            "match_count": match_count,
        },
    ).execute()

    rows = response.data or []
    if not rows:
        return "No matching songs found in vector search."

    lines = []
    for item in rows:
        title = item.get("title", "Unknown")
        artist = item.get("artist", "Unknown")
        text = item.get("text_for_embedding", "")
        similarity = item.get("similarity", 0)
        lines.append(
            f"- {title} by {artist} (similarity={similarity:.4f})\n  Context: {text}"
        )

    return "\n".join(lines)


def generate_playlist_explanation(user_query: str, retrieved_context: str) -> str:
    system_prompt = (
        "You are an Expert Emotional DJ. Recommend songs only from the provided retrieved context. "
        "Explain briefly why each recommendation fits the user mood journey using cues like tempo, energy, "
        "brightness, and emotion cluster context. Keep it engaging and concise."
    )

    user_prompt = (
        f"User request:\n{user_query}\n\n"
        f"Retrieved songs context:\n{retrieved_context}\n\n"
        "Return a short playlist recommendation with reasoning for each song."
    )

    result = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return result["message"]["content"]


def main() -> None:
    supabase = create_supabase_client()
    embed_model = SentenceTransformer(MODEL_NAME)

    print("Local RAG MVP ready. Type your prompt (or 'exit').")

    while True:
        user_query = input("\nYou: ").strip()
        if user_query.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        try:
            context = retrieve_songs(user_query, supabase, embed_model)
            print("\nRetrieved Matches:\n")
            print(context)

            answer = generate_playlist_explanation(user_query, context)
            print("\nEmotional DJ:\n")
            print(answer)
        except Exception as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
