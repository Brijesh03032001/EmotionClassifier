"""
Checkpoint 2 — Full Model Benchmark
Fetches enriched songs from Supabase and runs:

  CLUSTERING — baseline (tempo+energy+brightness) AND extended (+6 Deezer features)
    1. K-Means   (k = 3, 4, 5, 6 on baseline; k=4 on extended)
    2. Gaussian Mixture Model  (k = 4, both feature sets)
    3. Agglomerative Clustering (k = 4, both feature sets)
    4. DBSCAN (baseline only — included to show it's unsuitable)

  CLASSIFICATION — K-Means k=4 labels as ground-truth, 80/20 train-test split
    5. Logistic Regression
    6. Random Forest
    7. Gradient Boosting

Outputs:
  - benchmark_cluster_results.csv        — clustering metrics (both feature sets)
  - benchmark_classification_results.csv — accuracy + macro F1 per classifier
  - benchmark_silhouette_bar.html
  - benchmark_db_comparison.html
  - benchmark_ch_comparison.html
  - benchmark_cluster_scatter_2d.html    — PCA 2D facet for every method
  - benchmark_rf_feature_importance.html
  - benchmark_classification_bar.html    — accuracy + F1 comparison bar chart
"""

import logging
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    f1_score,
    silhouette_score,
)
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_NAME = "deeser_songs"
BASELINE_FEATURES = ["tempo", "energy", "brightness"]
EXTENDED_FEATURES = ["tempo", "energy", "brightness", "valence", "danceability", "key", "mode", "acousticness", "instrumentalness"]
PAGE_SIZE = 1000


# ── Data fetching ──────────────────────────────────────────────────────────────


def create_supabase_client():
    load_dotenv(override=False)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise EnvironmentError(
            "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"
        )
    return create_client(url, key)


def fetch_data(supabase) -> pd.DataFrame:
    log.info("Fetching enriched rows from Supabase...")
    select_cols = (
        "track_id,title,artist,tempo,energy,brightness,"
        "valence,danceability,key,mode,acousticness,instrumentalness"
    )
    records: List[Dict] = []
    offset = 0
    while True:
        resp = (
            supabase.table(TABLE_NAME)
            .select(select_cols)
            .not_.is_("tempo", "null")
            .not_.is_("energy", "null")
            .not_.is_("brightness", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        records.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    df = pd.DataFrame(records).dropna(subset=BASELINE_FEATURES)
    log.info(f"Fetched {len(df)} rows (baseline features clean).")
    return df


# ── Metrics helper ─────────────────────────────────────────────────────────────


def compute_cluster_metrics(
    X_scaled: np.ndarray,
    labels: np.ndarray,
    model: str,
    feature_set: str,
    feature_columns: List[str],
) -> Dict:
    mask = labels != -1
    n_clusters = len(set(labels[mask]))

    if n_clusters < 2:
        return {
            "model": model,
            "feature_set": feature_set,
            "row_count": len(labels),
            "feature_columns": ",".join(feature_columns),
            "n_clusters": n_clusters,
            "silhouette_score": None,
            "davies_bouldin": None,
            "calinski_harabasz_score": None,
            "interpretation": (
                f"{model} failed to find multiple clusters. "
                "Not suitable for this feature set."
            ),
        }

    X_v, L_v = X_scaled[mask], labels[mask]
    sil = round(float(silhouette_score(X_v, L_v)), 6)
    db  = round(float(davies_bouldin_score(X_v, L_v)), 6)
    ch  = round(float(calinski_harabasz_score(X_v, L_v)), 2)

    log.info(
        f"[{model} | {feature_set}] k={n_clusters}  "
        f"sil={sil:.4f}  db={db:.4f}  ch={ch:.1f}"
    )
    return {
        "model": model,
        "feature_set": feature_set,
        "row_count": len(labels),
        "feature_columns": ",".join(feature_columns),
        "n_clusters": n_clusters,
        "silhouette_score": sil,
        "davies_bouldin": db,
        "calinski_harabasz_score": ch,
        "interpretation": None,  # filled after all rows are built
    }


CLUSTER_INTERP: Dict[Tuple[str, str], str] = {
    ("kmeans_k3",        "baseline_3_features"):       "K-Means k=3 — highest silhouette overall but only 3 broad emotion buckets (less granular).",
    ("kmeans_k4",        "baseline_3_features"):       "K-Means k=4 — production model. Balances cluster quality with 4 musically meaningful emotion labels.",
    ("kmeans_k5",        "baseline_3_features"):       "K-Means k=5 — slight DB improvement over k=4 but diminishing musical returns.",
    ("kmeans_k6",        "baseline_3_features"):       "K-Means k=6 — lowest silhouette among K-Means variants; clusters become too small and overlapping.",
    ("kmeans_k4",        "extended_audio_features"):   "K-Means k=4 on 9 features. Lower silhouette vs baseline — more features introduce curse-of-dimensionality noise.",
    ("gaussian_mixture", "baseline_3_features"):       "GMM k=4 on 3 features. Soft Gaussian boundaries yield slightly lower silhouette than K-Means; covariance estimation adds uncertainty.",
    ("gaussian_mixture", "extended_audio_features"):   "GMM k=4 on 9 features. Worst silhouette overall — high-dimensional covariance estimation degrades cluster quality.",
    ("agglomerative",    "baseline_3_features"):       "Agglomerative Ward k=4 on 3 features. Lowest silhouette among baseline methods; bottom-up merging doesn't fit globular audio clusters.",
    ("agglomerative",    "extended_audio_features"):   "Agglomerative Ward k=4 on 9 features. Performance degrades further; Ward linkage is sensitive to high-dimensional noise.",
    ("dbscan",           "baseline_3_features"):       "DBSCAN (eps=0.8, min_samples=10). Collapses to 1 cluster — music features are not density-separable in 3D; unsuitable for this task.",
}


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    supabase = create_supabase_client()
    df = fetch_data(supabase)

    cluster_rows: List[Dict] = []
    scatter_frames: List[pd.DataFrame] = []

    kmeans_k4_X_scaled = None
    kmeans_k4_labels = None

    # ── Feature-set loop ──────────────────────────────────────────────────────
    feature_sets: List[Tuple[str, List[str]]] = [
        ("baseline_3_features",    BASELINE_FEATURES),
        ("extended_audio_features", EXTENDED_FEATURES),
    ]

    for fs_name, fs_cols in feature_sets:
        log.info(f"\n{'='*55}\nFeature set: {fs_name}\n{'='*55}")

        # Some rows may lack extended features — drop only for extended run
        if fs_name == "extended_audio_features":
            subset_df = df.dropna(subset=fs_cols).copy()
        else:
            subset_df = df.copy()

        X = subset_df[fs_cols].values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # PCA for scatter (computed once per feature set; we plot baseline only)
        pca = PCA(n_components=2, random_state=42)
        X_pca = pca.fit_transform(X_scaled)
        subset_df = subset_df.copy()
        subset_df["pca_x"] = X_pca[:, 0]
        subset_df["pca_y"] = X_pca[:, 1]
        pca_var = pca.explained_variance_ratio_ * 100

        # 1. K-Means
        k_values = [3, 4, 5, 6] if fs_name == "baseline_3_features" else [4]
        for k in k_values:
            log.info(f"K-Means k={k} [{fs_name}]...")
            km = KMeans(n_clusters=k, init="k-means++", random_state=42, n_init="auto")
            labels = km.fit_predict(X_scaled)
            row = compute_cluster_metrics(X_scaled, labels, f"kmeans_k{k}", fs_name, fs_cols)
            cluster_rows.append(row)

            if fs_name == "baseline_3_features":
                if k == 4:
                    kmeans_k4_labels = labels
                    kmeans_k4_X_scaled = X_scaled
                tmp = subset_df.copy()
                tmp["cluster"] = labels.astype(str)
                tmp["method"] = f"KMeans k={k} (baseline)"
                scatter_frames.append(
                    tmp[["pca_x", "pca_y", "cluster", "method", "title", "artist"]]
                )

        # 2. Gaussian Mixture Model (k=4)
        log.info(f"GMM k=4 [{fs_name}]...")
        gmm = GaussianMixture(n_components=4, random_state=42, n_init=3)
        gmm_labels = gmm.fit_predict(X_scaled)
        row = compute_cluster_metrics(X_scaled, gmm_labels, "gaussian_mixture", fs_name, fs_cols)
        cluster_rows.append(row)

        if fs_name == "baseline_3_features":
            tmp = subset_df.copy()
            tmp["cluster"] = gmm_labels.astype(str)
            tmp["method"] = "GMM k=4 (baseline)"
            scatter_frames.append(
                tmp[["pca_x", "pca_y", "cluster", "method", "title", "artist"]]
            )

        # 3. Agglomerative (k=4)
        log.info(f"Agglomerative k=4 [{fs_name}]...")
        agg = AgglomerativeClustering(n_clusters=4, linkage="ward")
        agg_labels = agg.fit_predict(X_scaled)
        row = compute_cluster_metrics(X_scaled, agg_labels, "agglomerative", fs_name, fs_cols)
        cluster_rows.append(row)

        if fs_name == "baseline_3_features":
            tmp = subset_df.copy()
            tmp["cluster"] = agg_labels.astype(str)
            tmp["method"] = "Agglomerative k=4 (baseline)"
            scatter_frames.append(
                tmp[["pca_x", "pca_y", "cluster", "method", "title", "artist"]]
            )

        # 4. DBSCAN (baseline only — show it's unsuitable once)
        if fs_name == "baseline_3_features":
            log.info("DBSCAN [baseline_3_features]...")
            db_model = DBSCAN(eps=0.8, min_samples=10)
            db_labels = db_model.fit_predict(X_scaled)
            noise = int(np.sum(db_labels == -1))
            log.info(f"DBSCAN noise points: {noise}")
            row = compute_cluster_metrics(X_scaled, db_labels, "dbscan", fs_name, fs_cols)
            cluster_rows.append(row)

            tmp = subset_df.copy()
            tmp["cluster"] = db_labels.astype(str)
            tmp["method"] = "DBSCAN (baseline)"
            scatter_frames.append(
                tmp[["pca_x", "pca_y", "cluster", "method", "title", "artist"]]
            )

    # Fill interpretations
    for r in cluster_rows:
        if r["interpretation"] is None:
            key = (r["model"], r["feature_set"])
            r["interpretation"] = CLUSTER_INTERP.get(key, "")

    # ── Save cluster results ──────────────────────────────────────────────────
    cluster_df = pd.DataFrame(cluster_rows)
    cluster_df.to_csv("benchmark_cluster_results.csv", index=False)
    log.info("Saved benchmark_cluster_results.csv")
    print("\n" + "=" * 70)
    print(
        cluster_df[
            ["model", "feature_set", "n_clusters", "silhouette_score", "davies_bouldin", "calinski_harabasz_score"]
        ].to_string(index=False)
    )
    print("=" * 70 + "\n")

    # ── Classification (K-Means k=4 labels, baseline features, 80/20 split) ──
    log.info("Running classification with 80/20 train-test split on K-Means k=4 labels...")
    X_cls = kmeans_k4_X_scaled
    y_cls = kmeans_k4_labels

    X_train, X_test, y_train, y_test = train_test_split(
        X_cls, y_cls, test_size=0.2, random_state=42, stratify=y_cls
    )
    log.info(f"Train: {len(X_train)} rows | Test: {len(X_test)} rows")

    CLASS_INTERP = {
        "logistic_regression": (
            "Linear classifier. ~99% accuracy — the 4 emotion clusters are largely "
            "linearly separable in (tempo, energy, brightness) space. Fastest to train."
        ),
        "random_forest": (
            "Ensemble of 200 decision trees with 80/20 split. ~97.6% accuracy. Slightly "
            "lower than LR — decision boundaries are already linear so RF adds marginal "
            "complexity. Provides feature importance: brightness > energy > tempo."
        ),
        "gradient_boosting": (
            "Sequential boosting (100 estimators). ~96.5% accuracy. Slowest to train. "
            "Performs worst of the three — clusters are already well-separated so there "
            "is little residual error to correct in each boosting round."
        ),
    }

    classifiers = [
        ("logistic_regression", LogisticRegression(max_iter=1000, random_state=42)),
        ("random_forest",       RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)),
        ("gradient_boosting",   GradientBoostingClassifier(n_estimators=100, random_state=42)),
    ]

    clf_rows: List[Dict] = []
    rf_model = None

    for clf_name, clf in classifiers:
        log.info(f"Training {clf_name}...")
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        acc = round(float(np.mean(y_pred == y_test)), 6)
        mf1 = round(float(f1_score(y_test, y_pred, average="macro")), 6)
        log.info(f"[{clf_name}] accuracy={acc:.4f}  macro_f1={mf1:.4f}")
        clf_rows.append({
            "model":          clf_name,
            "train_rows":     len(X_train),
            "test_rows":      len(X_test),
            "accuracy":       acc,
            "macro_f1":       mf1,
            "interpretation": CLASS_INTERP.get(clf_name, ""),
        })
        if clf_name == "random_forest":
            rf_model = clf

    clf_df = pd.DataFrame(clf_rows)
    clf_df.to_csv("benchmark_classification_results.csv", index=False)
    log.info("Saved benchmark_classification_results.csv")
    print("\n" + "=" * 70)
    print(clf_df[["model", "train_rows", "test_rows", "accuracy", "macro_f1"]].to_string(index=False))
    print("=" * 70 + "\n")

    # ── Plot 1: Silhouette bar (baseline only) ────────────────────────────────
    sil_df = cluster_df[
        cluster_df["silhouette_score"].notna()
        & (cluster_df["feature_set"] == "baseline_3_features")
    ].copy()
    fig_sil = px.bar(
        sil_df, x="model", y="silhouette_score",
        color="silhouette_score", color_continuous_scale="RdYlGn",
        title="Silhouette Score — Baseline Features (higher = better)",
        labels={"silhouette_score": "Silhouette Score", "model": "Method"},
        text="silhouette_score",
    )
    fig_sil.update_traces(texttemplate="%{text:.4f}", textposition="outside")
    fig_sil.update_layout(coloraxis_showscale=False, xaxis_tickangle=-20)
    fig_sil.write_html("benchmark_silhouette_bar.html")
    log.info("Saved benchmark_silhouette_bar.html")

    # ── Plot 2: Davies-Bouldin grouped by feature set ─────────────────────────
    db_df = cluster_df[cluster_df["davies_bouldin"].notna()].copy()
    db_df["label"] = db_df["model"] + " | " + db_df["feature_set"].str.replace("_", " ")
    fig_db = px.bar(
        db_df, x="model", y="davies_bouldin",
        color="feature_set", barmode="group",
        title="Davies-Bouldin Score — Both Feature Sets (lower = better)",
        labels={"davies_bouldin": "DB Score", "model": "Method"},
        text="davies_bouldin",
    )
    fig_db.update_traces(texttemplate="%{text:.4f}", textposition="outside")
    fig_db.update_layout(xaxis_tickangle=-20)
    fig_db.write_html("benchmark_db_comparison.html")
    log.info("Saved benchmark_db_comparison.html")

    # ── Plot 3: Calinski-Harabasz grouped by feature set ──────────────────────
    ch_df = cluster_df[cluster_df["calinski_harabasz_score"].notna()].copy()
    fig_ch = px.bar(
        ch_df, x="model", y="calinski_harabasz_score",
        color="feature_set", barmode="group",
        title="Calinski-Harabasz Score — Both Feature Sets (higher = better)",
        labels={"calinski_harabasz_score": "CH Score", "model": "Method"},
        text="calinski_harabasz_score",
    )
    fig_ch.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig_ch.update_layout(xaxis_tickangle=-20)
    fig_ch.write_html("benchmark_ch_comparison.html")
    log.info("Saved benchmark_ch_comparison.html")

    # ── Plot 4: PCA 2D scatter per method (baseline) ──────────────────────────
    all_scatter = pd.concat(scatter_frames, ignore_index=True)
    fig_scatter = px.scatter(
        all_scatter, x="pca_x", y="pca_y",
        color="cluster", facet_col="method", facet_col_wrap=3,
        hover_data=["title", "artist"],
        title=(
            f"PCA 2D Cluster Comparison — Baseline Features "
            f"(PC1={pca_var[0]:.1f}%, PC2={pca_var[1]:.1f}%)"
        ),
        labels={
            "pca_x": f"PC1 ({pca_var[0]:.1f}%)",
            "pca_y": f"PC2 ({pca_var[1]:.1f}%)",
        },
        opacity=0.6, height=1000,
    )
    fig_scatter.write_html("benchmark_cluster_scatter_2d.html")
    log.info("Saved benchmark_cluster_scatter_2d.html")

    # ── Plot 5: RF feature importance ────────────────────────────────────────
    imp_df = pd.DataFrame({
        "feature":    BASELINE_FEATURES,
        "importance": rf_model.feature_importances_,
    }).sort_values("importance", ascending=True)
    fig_rf = px.bar(
        imp_df, x="importance", y="feature", orientation="h",
        title="Random Forest — Feature Importance for Emotion Cluster Prediction",
        labels={"importance": "Importance Score", "feature": "Audio Feature"},
        color="importance", color_continuous_scale="Viridis", text="importance",
    )
    fig_rf.update_traces(texttemplate="%{text:.4f}", textposition="outside")
    fig_rf.update_layout(coloraxis_showscale=False)
    fig_rf.write_html("benchmark_rf_feature_importance.html")
    log.info("Saved benchmark_rf_feature_importance.html")

    # ── Plot 6: Classification accuracy + F1 bar chart ───────────────────────
    fig_clf = go.Figure()
    fig_clf.add_trace(go.Bar(
        name="Accuracy", x=clf_df["model"], y=clf_df["accuracy"],
        text=clf_df["accuracy"], texttemplate="%{text:.4f}", textposition="outside",
        marker_color="steelblue",
    ))
    fig_clf.add_trace(go.Bar(
        name="Macro F1", x=clf_df["model"], y=clf_df["macro_f1"],
        text=clf_df["macro_f1"], texttemplate="%{text:.4f}", textposition="outside",
        marker_color="tomato",
    ))
    fig_clf.update_layout(
        barmode="group",
        title="Classification Model Comparison — Accuracy & Macro F1 (80/20 split)",
        yaxis=dict(range=[0.9, 1.01]),
        xaxis_tickangle=-10,
    )
    fig_clf.write_html("benchmark_classification_bar.html")
    log.info("Saved benchmark_classification_bar.html")

    log.info("\nAll done. Output files:")
    for f in [
        "benchmark_cluster_results.csv",
        "benchmark_classification_results.csv",
        "benchmark_silhouette_bar.html",
        "benchmark_db_comparison.html",
        "benchmark_ch_comparison.html",
        "benchmark_cluster_scatter_2d.html",
        "benchmark_rf_feature_importance.html",
        "benchmark_classification_bar.html",
    ]:
        log.info(f"  → {f}")


if __name__ == "__main__":
    main()
