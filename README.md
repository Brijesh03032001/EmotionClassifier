# Emotion-Aware Playlist Generator

This project builds an emotion-aware music mining pipeline on top of Deezer preview audio and Supabase. The current codebase collects songs, extracts audio features from previews, groups songs into emotion clusters, and prepares embeddings for future recommendation or playlist generation.

## Current Pipeline

1. `deezer_store_deeser_songs.py`
   Collects Deezer chart and search tracks, filters to rows with preview URLs, and upserts them into Supabase.
2. `deezer_enrich_deeser_songs.py`
   Downloads each preview and uses `librosa` to estimate audio descriptors such as tempo, energy, brightness, valence, danceability, acousticness, instrumentalness, liveness, and speechiness.
3. `deezer_emotion_clustering.py`
   Runs the original checkpoint-1 baseline clustering using K-Means on `tempo`, `energy`, and `brightness`.
4. `generate_embeddings.py`
   Creates text descriptions and stores vector embeddings for later similarity search.
5. `checkpoint2_experiments.py`
   Runs checkpoint-2 method comparison experiments and writes presentation-ready outputs.

## Checkpoint 2 Additions

The checkpoint-2 script compares multiple predictive/data mining methods on top of the existing pipeline:

- Clustering methods:
  - `KMeans`
  - `AgglomerativeClustering`
  - `GaussianMixture`
- Feature sets:
  - baseline `tempo`, `energy`, `brightness`
  - extended audio feature set using the engineered `librosa` features
- Metrics:
  - silhouette score
  - Davies-Bouldin score
  - Calinski-Harabasz score
- Downstream predictive benchmark:
  - logistic regression
  - random forest
  - gradient boosting

The classification step uses the best clustering labels as pseudo-labels. That is useful for checkpoint 2 comparison, but it is not a substitute for human-labeled emotion ground truth.

## Outputs

Running `checkpoint2_experiments.py` produces:

- `checkpoint2_cluster_results.csv`
- `checkpoint2_classification_results.csv`
- `checkpoint2_report.json`
- `checkpoint2_best_projection.html`

These files are meant to support the checkpoint-2 video presentation by showing:

- baseline vs improved methods
- richer evaluation metrics
- strongest-performing feature set
- future direction toward recommendation / playlist generation

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` with:

```bash
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_TARGET_TABLE=deeser_songs
```

## Recommended Run Order

```bash
python deezer_store_deeser_songs.py
python deezer_enrich_deeser_songs.py
python deezer_emotion_clustering.py
python generate_embeddings.py
python checkpoint2_experiments.py
```

## Suggested Checkpoint 2 Narrative

- The original idea was an emotion-aware playlist generator.
- Checkpoint 1 focused on building the data mining pipeline and creating the emotion-aware dataset.
- Checkpoint 2 compares clustering and predictive methods, highlights weaknesses in the baseline, and identifies better-performing alternatives.
- A future milestone is using the best model outputs for playlist generation and music recommendation.
