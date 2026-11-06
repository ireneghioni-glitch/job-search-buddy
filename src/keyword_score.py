# src/keyword_score.py
"""
keyword_score.py
================
Deterministic keyword-based scoring of job postings against the candidate
profile.

This is a second, LLM-independent score. It does NOT replace the LLM triage
in analyze_all.py; it complements it. If both agree (LLM high + keyword high),
the signal is strong. If they disagree, the posting deserves a manual read.
"""

import argparse
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT_DIR / "jobs"
OUTPUTS_DIR = ROOT_DIR / "outputs"

KEYWORD_FAMILIES = [
    # --- Core data science / programming (weight 3) ---
    ("python",        3, ["python"]),
    ("sql",           3, ["sql"]),
    ("pandas_numpy",  3, ["pandas", "numpy"]),
    ("ml_libs",       3, ["scikit-learn", "scikit learn", "sklearn", "pytorch",
                          "tensorflow", "xgboost"]),
    ("ml_concepts",   3, ["machine learning", "deep learning", "neural network",
                          "random forest", "gradient boosting"]),

    # --- Chemistry / materials domain ---
    ("chemistry_generic", 1, ["chemistry", "chemical", "chimica", "chimie"]),
    ("materials",     4, ["materials science", "materials informatics",
                          "material science", "polymer", "formulation"]),
    ("uv_curing",     4, ["uv-curing", "uv curing", "photoinitiator",
                          "uv-curable"]),
    ("inks_coatings", 4, ["inkjet", "ink formulation", "coating", "coatings"]),
    ("analytical",    3, ["hplc", "uplc", "gc-ms", "gc-fid", "nmr", "dsc",
                          "ft-ir", "spectroscopy", "chromatography",
                          "rheology", "rheological"]),

    # --- Cheminformatics / domain-specific tooling (weight 4) ---
    ("rdkit",         4, ["rdkit", "mordred", "smiles", "cheminformatics",
                          "molecular descriptor"]),
    ("doe",           3, ["design of experiments", "doe", "factorial design"]),

    # --- R&D environment (weight 2) ---
    ("r_and_d",       2, ["r&d", "research and development", "research scientist",
                          "r&d scientist", "innovation"]),
    ("lab",           2, ["laboratory", "lab ", "lab.", "bench", "experimental"]),
    ("patents",       2, ["patent", "patents", "ip "]),
    ("sap",           1, ["sap "]), 

    # --- Data science role signals (weight 2) ---
    ("data_scientist", 2, ["data scientist", "data science"]),
    ("data_analyst",   2, ["data analyst", "data analysis"]),
    ("ml_engineer",    2, ["machine learning engineer", "ml engineer",
                           "mlops"]),
    ("digital_rnd",    2, ["digital r&d", "digital transformation",
                           "lab informatics", "lims"]),

    # --- Soft signals (weight 1) ---
    ("scientific_writing", 1, ["publication", "publications", "scientific writing",
                               "technical writing"]),
    ("cross_functional",   1, ["cross-functional", "cross functional",
                               "collaboration", "stakeholder"]),

    # --- Anti-signals (negative weight) ---
    ("finance",       -3, ["banking", "bank ", "insurance", "verzekering",
                           "asset management", "wealth management",
                           "financial services"]),
    ("clinical",      -3, ["clinical trial", "clinical research", "patient",
                           "clinical "]),
    ("pharma_drug",   -2, ["drug discovery", "drug development",
                           "therapeutic", "pharmaceutical development"]),
    ("semiconductor", -3, ["semiconductor", "wafer", "chip design", "asic",
                           "fpga", "cmos"]),
]

def _build_term_index():
    index = []
    for family, weight, terms in KEYWORD_FAMILIES:
        compiled = []
        for t in terms:
            t = t.strip().lower()
            if not t:
                continue
            if " " in t or "-" in t or "&" in t:
                compiled.append(("substring", t))
            else:
                compiled.append(("word", re.compile(r"\b" + re.escape(t) + r"\b")))
        index.append((family, weight, compiled))
    return index

_TERM_INDEX = _build_term_index()

def score_text(text: str) -> dict:
    lower = text.lower()
    positive_weight_matched = 0
    positive_hits = []
    negative_hits = []

    total_positive_weight = sum(w for _, w, _ in KEYWORD_FAMILIES if w > 0)

    for family, weight, compiled in _TERM_INDEX:
        matched = False
        for kind, matcher in compiled:
            if kind == "substring":
                if matcher in lower:
                    matched = True
                    break
            else:
                if matcher.search(lower):
                    matched = True
                    break
        if not matched:
            continue
        if weight > 0:
            positive_weight_matched += weight
            positive_hits.append(family)
        else:
            negative_hits.append(family)

    coverage = positive_weight_matched / total_positive_weight if total_positive_weight else 0.0
    score = int(round(coverage * 100))

    for _ in negative_hits:
        score -= 5
    score = max(0, min(100, score))

    return {
        "score": score,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
    }

def load_job_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_meta_score(job_path: Path, kw: dict) -> None:
    stem = job_path.stem
    meta_path = OUTPUTS_DIR / f"{stem}.meta.json"
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return
    meta["keyword_score"] = kw["score"]
    meta["keyword_hits"] = kw["positive_hits"]
    meta["keyword_negatives"] = kw["negative_hits"]
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Deterministic keyword scoring.")
    parser.add_argument("--job", default=None, help="Score a single file")
    parser.add_argument("--top", type=int, default=None, help="Show top N")
    parser.add_argument("--update-meta", action="store_true", help="Write to .meta.json")
    parser.add_argument("--show-hits", action="store_true", help="Show matched families")
    args = parser.parse_args()

    if args.job:
        p = Path(args.job)
        if not p.exists():
            print(f"[ERROR] file not found: {p}")
            return
        kw = score_text(load_job_text(p))
        print(f"{p.name}")
        print(f"  keyword score: {kw['score']}/100")
        print(f"  positive: {', '.join(kw['positive_hits']) or '(none)'}")
        print(f"  negative: {', '.join(kw['negative_hits']) or '(none)'}")
        if args.update_meta:
            write_meta_score(p, kw)
        return

    if not JOBS_DIR.exists():
        print(f"[ERROR] jobs directory not found: {JOBS_DIR}")
        return

    job_files = sorted(JOBS_DIR.glob("*.txt"))
    if not job_files:
        print("[INFO] no job files found in jobs/")
        return

    results = []
    for p in job_files:
        kw = score_text(load_job_text(p))
        results.append((p, kw))
        if args.update_meta:
            write_meta_score(p, kw)

    results.sort(key=lambda x: -x[1]["score"])
    if args.top:
        results = results[:args.top]

    print(f"Keyword scores for {len(results)} job(s):\n")
    for p, kw in results:
        print(f"{kw['score']:>5}  {p.name[:79]}")
        if args.show_hits:
            print(f"         + {', '.join(kw['positive_hits']) or '(none)'}")
            print(f"         - {', '.join(kw['negative_hits']) or '(none)'}")

if __name__ == "__main__":
    main()