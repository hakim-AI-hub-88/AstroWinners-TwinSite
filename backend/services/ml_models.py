#############################################################################
# MACHINE LEARNING MODELS (unsupervised - scikit-learn)
#
# Why this file exists:
#   Adds two machine-learning views that are INDEPENDENT of the weighted
#   similarity score, so the jury can see whether different methods agree.
#
#   Model A - "Planetary environment space" (PCA, 2 components)
#     Projects every cell of Earth (Atacama), Mars and the Moon on a 2-D map
#     from the 6 features shared by the three bodies. Shows where the Atacama
#     sits relative to Mars and the Moon.
#
#   Model B - "Terrain types" (K-means clustering)
#     Learns terrain types shared by the three bodies from the terrain shape
#     only (slope, roughness, relief). The number of types is chosen
#     automatically with the silhouette score. Temperatures are left out on
#     purpose: with them, clusters simply separate the bodies (Atacama nights
#     are much warmer), which Model A already shows. Albedo is left out because
#     it is measured by different instruments on each body.
#
# Scientific rules:
#   - unsupervised only: no labels; the NASA validation sites are never used
#   - harmonized + NORMALIZED data only (the "calculation" role)
#   - balanced training sample: the same number of cells per body, so Mars
#     (1.8 M cells) does not dominate Earth (1,099 cells)
#   - fixed random seed: identical results at every start
#
# Output of insights(): JSON-ready dict for GET /api/ml (points for the
# interactive scatter plot, terrain types, agreement with the score ranking).
#############################################################################
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from services import data_loader
from utils import config

log = logging.getLogger(__name__)

ENV_FEATURES = ["slope", "roughness", "relief", "temperature_day", "temperature_night", "albedo"]
TERRAIN_FEATURES = ["slope", "roughness", "relief"]
SAMPLE_PER_BODY = 3000          # training sample per body (balanced)
PLOT_PER_BODY = 1500            # Mars / Moon points drawn in the scatter plot
K_RANGE = range(3, 7)           # candidate numbers of terrain types
SEED = 42
TYPE_NAMES = ["Flat plains", "Gentle / rolling terrain", "Rugged terrain", "Mountainous terrain",
              "Very rugged terrain", "Extreme relief"]
TYPE_COLORS = ["#4cc38a", "#f2c14e", "#ff7a45", "#d7191c", "#9b59b6", "#5c0a1f"]


def _complete(df, cols):
    return df.dropna(subset=cols)


#############################################
# TRAINING (once per server start, ~5 s)
#############################################
PREDICT_CHUNK = 200_000                     # rows per K-means predict() call (memory bound)


#############################################
# PRE-TRAINED MODELS (small hosts)
# `python -m services.ml_models export <file.npz>` trains once (e.g. at Docker build time) and saves
# the fitted parameters. With TWINSITE_ML_MODELS pointing at that file the server applies them with
# NumPy and never imports scikit-learn, saving ~100 MB of RAM. Same data + same seed = same models.
#############################################
class _SavedPCA:
    def __init__(self, mean, components, evr):
        self.mean_, self.components_, self.explained_variance_ratio_ = mean, components, evr

    def transform(self, x):
        return (np.asarray(x) - self.mean_) @ self.components_.T


class _SavedKMeans:
    def __init__(self, centers):
        self.cluster_centers_ = centers

    def predict(self, x):
        x = np.asarray(x, dtype=self.cluster_centers_.dtype)
        out = np.empty(len(x), dtype=np.int64)
        for start in range(0, len(x), PREDICT_CHUNK):
            chunk = x[start:start + PREDICT_CHUNK]
            d = ((chunk[:, None, :] - self.cluster_centers_[None, :, :]) ** 2).sum(axis=2)
            out[start:start + PREDICT_CHUNK] = d.argmin(axis=1)
        return out


def export(path) -> None:
    """Train with scikit-learn and save the fitted parameters for _load_saved()."""
    import json
    m = models()
    np.savez(path, pca_mean=m["pca"].mean_, pca_components=m["pca"].components_,
             pca_evr=m["pca"].explained_variance_ratio_, centers=m["kmeans"].cluster_centers_,
             k=m["k"], silhouettes=json.dumps(m["silhouettes"]),
             **{f"share_{b}": v for b, v in m["share"].items()},
             **{f"centroid_{b}": v for b, v in m["centroids_env"].items()})


def _load_saved(path) -> dict:
    import json
    z = np.load(path)
    km = _SavedKMeans(z["centers"])
    order = np.argsort(km.cluster_centers_.mean(axis=1))
    remap = np.empty_like(order)
    remap[order] = np.arange(len(order))
    bodies = {b: data_loader.LOADERS[b]() for b in ("earth", "mars", "moon")}
    log.info("ML models loaded from %s (k=%d, no scikit-learn import)", path, int(z["k"]))
    return {"pca": _SavedPCA(z["pca_mean"], z["pca_components"], z["pca_evr"]), "kmeans": km,
            "predict_type": lambda a: remap[km.predict(a)], "k": int(z["k"]),
            "silhouettes": {int(k): v for k, v in json.loads(str(z["silhouettes"])).items()},
            "share": {b: z[f"share_{b}"] for b in bodies}, "centroids_env": {b: z[f"centroid_{b}"] for b in bodies},
            "bodies": bodies}


@lru_cache(maxsize=1)
def models() -> dict:
    import os
    saved = os.environ.get("TWINSITE_ML_MODELS")
    if saved and os.path.isfile(saved):
        return _load_saved(saved)
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score

    rng = np.random.default_rng(SEED)
    bodies = {b: data_loader.LOADERS[b]() for b in ("earth", "mars", "moon")}

    def balanced(cols):
        parts, weights = [], []
        for b, df in bodies.items():
            a = df[cols].dropna().to_numpy()      # only the needed columns: no full-frame copy
            idx = rng.choice(len(a), min(SAMPLE_PER_BODY, len(a)), replace=False)
            parts.append(a[idx])
            weights.append(np.full(len(idx), SAMPLE_PER_BODY / len(idx)))  # equal total weight per body
        return np.vstack(parts), np.concatenate(weights)

    # ---- Model A: PCA on the 6 shared features
    env_x, _ = balanced(ENV_FEATURES)
    pca = PCA(n_components=2, random_state=SEED).fit(env_x)

    # ---- Model B: K-means on terrain shape, k chosen by silhouette
    ter_x, ter_w = balanced(TERRAIN_FEATURES)
    candidates = {}
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(ter_x, sample_weight=ter_w)
        candidates[k] = (silhouette_score(ter_x, km.labels_, sample_size=4000, random_state=SEED), km)
    best_k = max(candidates, key=lambda k: candidates[k][0])
    km = candidates[best_k][1]
    # order types from flattest to most rugged so names/colours are meaningful
    order = np.argsort(km.cluster_centers_.mean(axis=1))
    remap = np.empty_like(order)
    remap[order] = np.arange(len(order))

    def predict_type(a):
        return remap[km.predict(a)]

    # Terrain-type share per body. Predicted in chunks over the needed columns only, so the
    # 1.8M-row Mars grid never needs a full copy plus a full distance matrix (fits 512 MB hosts);
    # labels are identical to a single predict() call.
    share = {}
    for b, df in bodies.items():
        a = df[TERRAIN_FEATURES].dropna().to_numpy()
        counts = np.zeros(best_k, dtype=np.int64)
        for start in range(0, len(a), PREDICT_CHUNK):
            counts += np.bincount(predict_type(a[start:start + PREDICT_CHUNK]), minlength=best_k)
        share[b] = counts / max(len(a), 1)
        del a

    centroids_env = {b: df[ENV_FEATURES].dropna().mean().to_numpy() for b, df in bodies.items()}
    log.info("ML models trained: PCA %.0f%% variance, K-means k=%d (silhouette %.3f)",
             100 * pca.explained_variance_ratio_.sum(), best_k, candidates[best_k][0])
    return {"pca": pca, "kmeans": km, "predict_type": predict_type, "k": best_k,
            "silhouettes": {k: round(float(v[0]), 3) for k, v in candidates.items()},
            "share": share, "centroids_env": centroids_env, "rng": rng, "bodies": bodies}


#############################################
# HELPERS
#############################################
def _axis_label(component: np.ndarray) -> str:
    """Human-readable meaning of a PCA axis from its strongest loadings."""
    idx = np.argsort(-np.abs(component))[:3]
    parts = [("+" if component[i] > 0 else "−") + " " + ENV_FEATURES[i].replace("_", " ") for i in idx]
    return ", ".join(parts)


def _k(lat, lon) -> tuple[float, float]:
    """Cell key robust to float32 storage (cell centres sit on 0.005-degree offsets)."""
    return round(float(lat), 3), round(float(lon), 3)


def _r(a, d=3):
    return np.round(np.asarray(a, dtype=float), d).tolist()


@lru_cache(maxsize=1)
def _plot_background() -> dict:
    """Fixed random sample of Mars and Moon cells for the scatter plot (same at every request)."""
    m = models()
    rng = np.random.default_rng(SEED + 1)
    out = {}
    for b in ("mars", "moon"):
        df = _complete(m["bodies"][b], ENV_FEATURES)
        idx = rng.choice(len(df), min(PLOT_PER_BODY, len(df)), replace=False)
        sub = df.iloc[idx]
        xy = m["pca"].transform(sub[ENV_FEATURES].to_numpy())
        types = m["predict_type"](sub[TERRAIN_FEATURES].to_numpy())
        out[b] = [[*_r(p, 3), int(t)] for p, t in zip(xy, types)]
    return out


#############################################
# INSIGHTS FOR ONE TARGET (GET /api/ml)
#############################################
def insights(result: dict) -> dict:
    m = models()
    pca, k = m["pca"], m["k"]
    t = result["target"]
    planet = t["planet"]

    # Target cells (normalized, role 1) - same 50 km window as the score
    window = data_loader.extract_target_window(data_loader.LOADERS[planet](), t["lat"], t["lon"], t["window_km"],
                                               config.BODY_RADIUS_M[planet])
    win_env = _complete(window, ENV_FEATURES)
    win_ter = _complete(window, TERRAIN_FEATURES)
    target_xy = pca.transform(win_env[ENV_FEATURES].to_numpy()) if len(win_env) else np.empty((0, 2))
    target_types = m["predict_type"](win_ter[TERRAIN_FEATURES].to_numpy()) if len(win_ter) else np.array([], int)
    dist = np.bincount(target_types, minlength=k) / max(len(target_types), 1)
    target_type = int(dist.argmax()) if len(target_types) else None

    # Earth (Atacama) cells: PCA position, terrain type, similarity score
    # Earth zone of this analysis (Atacama = training zone; other zones are projected with the
    # same fitted models - like applying a trained model to new data)
    zone = (result.get("zone") or {}).get("id", config.DEFAULT_ZONE)
    earth = data_loader.load_zone(zone, "normalized")
    scores = {_k(c["lat"], c["lon"]): c["score"] for c in result["map"]}
    ranked = {_k(r["lat"], r["lon"]): r["rank"] for r in result["ranking"]}
    e_ter = _complete(earth, TERRAIN_FEATURES)
    e_types = {_k(la, lo): int(tt) for la, lo, tt in zip(e_ter["latitude"], e_ter["longitude"],
                                                         m["predict_type"](e_ter[TERRAIN_FEATURES].to_numpy()))}
    e_env = _complete(earth, ENV_FEATURES)
    e_xy = pca.transform(e_env[ENV_FEATURES].to_numpy())
    earth_points = []
    for lat, lon, (x, y) in zip(e_env["latitude"], e_env["longitude"], e_xy):
        key = _k(lat, lon)
        earth_points.append([round(float(x), 3), round(float(y), 3), e_types.get(key), key[0], key[1],
                             scores.get(key), ranked.get(key)])

    # Agreement between the ML terrain type and the score ranking
    top_types = [e_types.get(_k(r["lat"], r["lon"])) for r in result["ranking"]]
    same_top = sum(tt == target_type for tt in top_types) if target_type is not None else 0
    same_scores = [s for (key, s) in scores.items() if s is not None and e_types.get(key) == target_type]
    other_scores = [s for (key, s) in scores.items() if s is not None and e_types.get(key) not in (None, target_type)]

    # Distances between body centroids in the 6-D normalized space
    c = m["centroids_env"]
    zone_centroid = _complete(earth, ENV_FEATURES)[ENV_FEATURES].mean().to_numpy()
    d_mars = float(np.linalg.norm(zone_centroid - c["mars"]))
    d_moon = float(np.linalg.norm(zone_centroid - c["moon"]))
    zone_counts = np.bincount(np.array(list(e_types.values()), int), minlength=k) if e_types else np.zeros(k)
    zone_share = zone_counts / max(zone_counts.sum(), 1)

    types = []
    for i in range(k):
        center = m["kmeans"].cluster_centers_[np.argsort(m["kmeans"].cluster_centers_.mean(axis=1))[i]]
        types.append({"id": i, "name": TYPE_NAMES[i], "color": TYPE_COLORS[i],
                      "centroid": {f: round(float(v), 3) for f, v in zip(TERRAIN_FEATURES, center)},
                      "share_pct": {**{b: round(100 * float(m["share"][b][i]), 1) for b in ("earth", "mars", "moon")},
                                    "zone": round(100 * float(zone_share[i]), 1)},
                      "target_share_pct": round(100 * float(dist[i]), 1)})

    return {
        "pca": {
            "explained_variance_pct": _r(100 * pca.explained_variance_ratio_, 1),
            "axis_labels": [_axis_label(pca.components_[0]), _axis_label(pca.components_[1])],
            "earth": earth_points,                         # [x, y, type, lat, lon, score, rank]
            "background": _plot_background(),             # mars / moon: [x, y, type]
            "target": _r(target_xy, 3),
            "target_center": _r(target_xy.mean(axis=0), 3) if len(target_xy) else None,
            "centroid_distance": {"earth_mars": round(d_mars, 3), "earth_moon": round(d_moon, 3)},
        },
        "clustering": {
            "algorithm": "K-means", "features": TERRAIN_FEATURES, "k": k, "silhouettes": m["silhouettes"],
            "types": types, "target_type": target_type,
            "target_type_share_pct": round(100 * float(dist[target_type]), 1) if target_type is not None else None,
            "atacama_same_type_pct": round(100 * float(zone_share[target_type]), 1) if target_type is not None else None,
            "zone_same_type_pct": round(100 * float(zone_share[target_type]), 1) if target_type is not None else None,
            "earth_types": [[lat, lon, tt] for (lat, lon), tt in e_types.items()],
        },
        "agreement": {
            "top10_same_type": same_top, "top10_count": len(result["ranking"]),
            "mean_score_same_type": round(float(np.mean(same_scores)), 1) if same_scores else None,
            "mean_score_other_types": round(float(np.mean(other_scores)), 1) if other_scores else None,
        },
        "zone": zone,
        "method": ("Unsupervised scikit-learn models trained on a balanced sample (3,000 cells per body: Atacama, Mars, "
                   "Moon) of the harmonized normalized data; fixed seed; validation sites never used."
                   + ("" if zone == config.DEFAULT_ZONE else
                      f" The {config.EARTH_ZONES[zone]['name']} zone is projected with the same fitted models.")),
    }


if __name__ == "__main__":                     # python -m services.ml_models export <file.npz>
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "export":
        logging.basicConfig(level=logging.INFO)
        export(sys.argv[2])
    else:
        sys.exit("usage: python -m services.ml_models export <file.npz>")
