"""Quick verification script for Issue #23 outputs."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # ml_training/ -> models/ -> backend/

png_path      = BASE / "models/ml_training/outputs/elbow_curve.png"
json_path     = BASE / "models/ml_training/outputs/elbow_result.json"
metadata_path = BASE / "models/ml_models/v1.0/metadata.json"

results = []

def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"  [{status}] {label}" + (f"  |  {detail}" if detail else ""))

print("\n" + "=" * 58)
print("  Issue #23 Verification — Elbow Method Outputs")
print("=" * 58)

# ── Check 1: PNG ──────────────────────────────────────────────
print("\n[1] Elbow curve PNG")
check("elbow_curve.png exists", png_path.exists(),
      f"{png_path.stat().st_size} bytes" if png_path.exists() else "FILE MISSING")

# ── Check 2: elbow_result.json ────────────────────────────────
print("\n[2] elbow_result.json")
if json_path.exists():
    d = json.loads(json_path.read_text(encoding="utf-8"))
    n_entries = len(d.get("inertias", []))
    expected  = d.get("k_max", 0) - d.get("k_min", 0) + 1
    check("File exists", True, str(json_path))
    check("optimal_k is an int", isinstance(d.get("optimal_k"), int),
          f"optimal_k = {d.get('optimal_k')}")
    check("k_min == 5", d.get("k_min") == 5, f"k_min = {d.get('k_min')}")
    check("k_max == 20", d.get("k_max") == 20, f"k_max = {d.get('k_max')}")
    check("inertia entries count correct",
          n_entries == expected,
          f"{n_entries} entries (expected {expected})")
    check("detection_method present", bool(d.get("detection_method")),
          d.get("detection_method"))
else:
    check("elbow_result.json exists", False, "FILE MISSING")

# ── Check 3: metadata.json patch ──────────────────────────────
print("\n[3] metadata.json patch (no data loss)")
if metadata_path.exists():
    m = json.loads(metadata_path.read_text(encoding="utf-8"))
    check("elbow_analysis key present", "elbow_analysis" in m)
    check("optimal_k inside elbow_analysis",
          "optimal_k" in m.get("elbow_analysis", {}),
          str(m.get("elbow_analysis", {}).get("optimal_k")))
    check("existing model_name preserved", "model_name" in m, m.get("model_name", "MISSING"))
    check("existing extra field preserved", "extra" in m)
    check("existing training_date preserved", "training_date" in m)
else:
    check("metadata.json exists", False, "FILE MISSING")

# ── Summary ───────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
print(f"\n{'=' * 58}")
print(f"  RESULT: {passed}/{total} checks passed")
print(f"{'=' * 58}\n")

sys.exit(0 if all(results) else 1)
