"""
models/ml_training/find_optimal_k.py
======================================
Standalone elbow-method script for automated optimal-K selection in the
K-Means skill clusterer.  Issue #23.

Usage
-----
    python find_optimal_k.py
    python find_optimal_k.py --k-min 5 --k-max 20 --version 1.0
    python find_optimal_k.py --no-plot          # headless / CI mode

Outputs
-------
  1. ml_training/outputs/elbow_curve.png        (skipped with --no-plot)
  2. ml_training/outputs/elbow_result.json
  3. ml_models/v<version>/metadata.json         (patched with "elbow_analysis" key)

Exit codes
----------
  0  optimal K detected and outputs written
  1  fatal error (e.g. no skills loaded)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
_THIS_DIR  = Path(__file__).resolve().parent          # ml_training/
_BACKEND   = _THIS_DIR.parent.parent                  # backend/
_ML_MODELS = _THIS_DIR.parent / "ml_models"           # backend/models/ml_models/
_OUTPUTS   = _THIS_DIR / "outputs"                    # ml_training/outputs/

sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_THIS_DIR))

from versioning import _detect_git_commit             # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("find_optimal_k")


# ── Embedding loader ──────────────────────────────────────────────────────────

def load_embeddings() -> tuple[list[str], np.ndarray]:
    """
    Load skill taxonomy and compute BERT embeddings.
    Reuses the same NLPConfig + _get_taxonomy_embeddings path used during
    training so results are directly comparable.
    """
    from nlp.config import NLPConfig                        # noqa: PLC0415
    from nlp.semantic import _get_taxonomy_embeddings       # noqa: PLC0415

    config = NLPConfig()
    logger.info("Loading taxonomy from: %s", config.SKILL_TAXONOMY_PATH)
    taxonomy = _get_taxonomy_embeddings(config)

    names: list[str] = taxonomy["names"]
    embeddings: np.ndarray = taxonomy["embeddings"]

    if len(names) == 0:
        logger.error("No skills found in taxonomy. Check SKILL_TAXONOMY_PATH.")
        sys.exit(1)

    logger.info("Loaded %d skills  |  embedding dim = %d", len(names), embeddings.shape[1])
    return names, embeddings


# ── Inertia sweep ─────────────────────────────────────────────────────────────

def sweep_inertias(
    embeddings: np.ndarray,
    k_min: int,
    k_max: int,
) -> list[dict[str, Any]]:
    """
    Fit K-Means for each k in [k_min, k_max] and record inertia (WCSS).

    Returns
    -------
    list of {"k": int, "inertia": float}
    """
    from sklearn.cluster import KMeans  # noqa: PLC0415

    # Guard: max k must be < number of samples
    effective_max = min(k_max, len(embeddings) - 1)
    if effective_max < k_min:
        logger.error(
            "Not enough samples (%d) for k_min=%d. Aborting.", len(embeddings), k_min
        )
        sys.exit(1)

    results: list[dict[str, Any]] = []
    logger.info("Sweeping k = %d to %d  (this may take ~30–60 s) ...", k_min, effective_max)

    for k in range(k_min, effective_max + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
        km.fit(embeddings)
        inertia = float(km.inertia_)
        results.append({"k": k, "inertia": round(inertia, 4)})
        logger.info("  k=%2d  |  inertia = %.2f", k, inertia)

    return results


# ── Elbow / knee detection ────────────────────────────────────────────────────

def detect_elbow(inertias: list[dict[str, Any]]) -> tuple[int, str]:
    """
    Detect the optimal K using KneeLocator (primary) or the second-difference
    method (fallback if kneed is unavailable).

    Returns
    -------
    (optimal_k, method_name)
    """
    k_vals    = np.array([r["k"]       for r in inertias])
    inert_vals = np.array([r["inertia"] for r in inertias])

    # ── Primary: KneeLocator ──────────────────────────────────────────────────
    try:
        from kneed import KneeLocator  # noqa: PLC0415

        kneedle = KneeLocator(
            k_vals,
            inert_vals,
            curve="convex",
            direction="decreasing",
            interp_method="interp1d",
        )
        if kneedle.knee is not None:
            optimal_k = int(kneedle.knee)
            logger.info("KneeLocator detected optimal K = %d", optimal_k)
            return optimal_k, "KneeLocator"
        else:
            logger.warning("KneeLocator returned None — falling back to second-difference method.")
    except ImportError:
        logger.warning("kneed not installed — using second-difference fallback.")

    # ── Fallback: second-difference (manual inflection detection) ─────────────
    diffs1 = np.diff(inert_vals)         # first  differences
    diffs2 = np.diff(diffs1)             # second differences
    # The elbow is where the rate of decrease slows most sharply.
    # np.argmax(diffs2) gives the index in diffs2; add 1 to map back to k_vals.
    elbow_idx = int(np.argmax(diffs2)) + 1
    optimal_k = int(k_vals[elbow_idx])
    logger.info("Second-difference fallback detected optimal K = %d", optimal_k)
    return optimal_k, "second_difference"


# ── Elbow curve plot ──────────────────────────────────────────────────────────

def plot_elbow(
    inertias: list[dict[str, Any]],
    optimal_k: int,
    output_path: Path,
) -> None:
    """
    Save a matplotlib elbow curve PNG to output_path.
    """
    import matplotlib                     # noqa: PLC0415
    matplotlib.use("Agg")                 # non-interactive backend — safe for headless
    import matplotlib.pyplot as plt       # noqa: PLC0415

    k_vals     = [r["k"]       for r in inertias]
    inert_vals = [r["inertia"] for r in inertias]

    fig, ax = plt.subplots(figsize=(10, 6))

    # Main elbow line
    ax.plot(k_vals, inert_vals, marker="o", linewidth=2,
            color="#4F8EF7", markersize=6, label="Inertia (WCSS)")

    # Mark the optimal K
    optimal_inertia = next(r["inertia"] for r in inertias if r["k"] == optimal_k)
    ax.axvline(x=optimal_k, color="#E84545", linestyle="--", linewidth=1.8,
               label=f"Optimal K = {optimal_k}")
    ax.scatter([optimal_k], [optimal_inertia], color="#E84545", zorder=5, s=100)

    # Labels and styling
    ax.set_xlabel("Number of Clusters (K)", fontsize=13)
    ax.set_ylabel("Inertia  (Within-Cluster Sum of Squares)", fontsize=13)
    ax.set_title("K-Means Elbow Curve — Skill Clusterer", fontsize=15, fontweight="bold")
    ax.set_xticks(k_vals)
    ax.legend(fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info("Elbow curve saved -> %s", output_path)


# ── Output writers ────────────────────────────────────────────────────────────

def write_outputs(
    inertias: list[dict[str, Any]],
    optimal_k: int,
    detection_method: str,
    k_min: int,
    k_max: int,
    n_skills: int,
    version_dir: Path,
) -> dict[str, Any]:
    """
    Write elbow_result.json and patch metadata.json.
    Returns the full result dict.
    """
    _OUTPUTS.mkdir(parents=True, exist_ok=True)

    run_at = datetime.now(timezone.utc).isoformat()

    result: dict[str, Any] = {
        "run_at":           run_at,
        "git_commit":       _detect_git_commit(),
        "k_min":            k_min,
        "k_max":            k_max,
        "n_skills":         n_skills,
        "optimal_k":        optimal_k,
        "detection_method": detection_method,
        "inertias":         inertias,
    }

    # ── elbow_result.json ─────────────────────────────────────────────────────
    result_path = _OUTPUTS / "elbow_result.json"
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=4)
    logger.info("elbow_result.json written -> %s", result_path)

    # ── metadata.json patch ───────────────────────────────────────────────────
    meta_path = version_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["elbow_analysis"] = {
                "run_at":           run_at,
                "optimal_k":        optimal_k,
                "k_min":            k_min,
                "k_max":            k_max,
                "detection_method": detection_method,
                "plot_path":        str(_OUTPUTS / "elbow_curve.png"),
            }
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=4)
            logger.info("metadata.json patched with 'elbow_analysis' key -> %s", meta_path)
        except Exception as exc:
            logger.warning("Could not patch metadata.json: %s", exc)
    else:
        logger.warning("metadata.json not found at %s — skipping patch.", meta_path)

    return result


# ── Console summary ───────────────────────────────────────────────────────────

def print_summary(result: dict[str, Any]) -> None:
    line = "-" * 52
    print(f"\n{'=' * 52}")
    print("  ELBOW METHOD RESULTS  --  K-Means Skill Clusterer")
    print(f"{'=' * 52}")
    print(f"  Skills embedded : {result['n_skills']}")
    print(f"  K range tested  : {result['k_min']} to {result['k_max']}")
    print(f"  Detection method: {result['detection_method']}")
    print(line)
    print(f"  >>> Recommended optimal K = {result['optimal_k']} <<<")
    print(line)
    print("  Inertia table:")
    for entry in result["inertias"]:
        marker = " <-- OPTIMAL" if entry["k"] == result["optimal_k"] else ""
        print(f"    k={entry['k']:2d}  |  inertia = {entry['inertia']:.2f}{marker}")
    print(f"{'=' * 52}\n")


# ── CLI & main ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run elbow method to find optimal K for the K-Means skill clusterer."
    )
    p.add_argument("--k-min",  type=int, default=5,
                   help="Minimum K to sweep (default: 5)")
    p.add_argument("--k-max",  type=int, default=20,
                   help="Maximum K to sweep (default: 20)")
    p.add_argument("--version", default="1.0",
                   help="Model version dir to patch metadata.json (default: 1.0)")
    p.add_argument("--no-plot", action="store_true",
                   help="Skip saving elbow_curve.png (useful in headless/CI environments)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    version = f"v{args.version}" if not args.version.startswith("v") else args.version
    version_dir = _ML_MODELS / version

    if not version_dir.exists():
        logger.error("Version directory not found: %s", version_dir)
        return 1

    # 1. Load embeddings
    names, embeddings = load_embeddings()
    n_skills = len(names)

    # 2. Sweep inertias
    inertias = sweep_inertias(embeddings, args.k_min, args.k_max)

    # 3. Detect optimal K
    optimal_k, method = detect_elbow(inertias)

    # 4. Plot (unless --no-plot)
    if not args.no_plot:
        plot_elbow(inertias, optimal_k, _OUTPUTS / "elbow_curve.png")
    else:
        logger.info("--no-plot set: skipping elbow_curve.png generation.")

    # 5. Write outputs
    result = write_outputs(
        inertias=inertias,
        optimal_k=optimal_k,
        detection_method=method,
        k_min=args.k_min,
        k_max=args.k_max,
        n_skills=n_skills,
        version_dir=version_dir,
    )

    # 6. Print summary
    print_summary(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
