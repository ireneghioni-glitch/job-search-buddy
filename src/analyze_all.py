# src/analyze_all.py
"""
analyze_all.py
==============
Batch analyzer for all job postings in jobs/.

Iterates over every .txt file in jobs/, analyzes each against the candidate
profile using the local Ollama model, saves individual reports in outputs/,
and generates a single summary report sorted by fit score.

Supports:
- Resume: skips jobs already analyzed (unless --reset).
- Quick mode: shorter prompt, only fit score + recommendation + reason.
- Strict mode: heuristic pre-filter that skips or caps scores for obvious
  mismatches (senior titles, 5+ years, wrong degree, specialized skills).
- Summary-only: regenerate the summary from existing analyses.
- Extra profile files: include additional profile files in the prompt.

Usage:
    python src/analyze_all.py --quick              # triage all jobs quickly
    python src/analyze_all.py --quick --strict     # triage with pre-filter (recommended)
    python src/analyze_all.py --limit 5            # test on 5 jobs
    python src/analyze_all.py --filter capgemini   # only matching filenames
    python src/analyze_all.py --summary-only       # regenerate summary
    python src/analyze_all.py --reset              # re-analyze everything
    python src/analyze_all.py --extra-files 03_education_skills.md 04_projects.md
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from ollama_client import generate
from profile_loader import load_profile

ROOT_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT_DIR / "jobs"
OUTPUTS_DIR = ROOT_DIR / "outputs"

MODEL = "qwen3:8b"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_FULL = """You are an experienced job search assistant specialized in scientific and data-driven roles (chemistry, materials science, data science, R&D).

Your job: evaluate how well the candidate fits the job posting.

Rules:
- Use ONLY information present in the candidate profile. Do not invent experiences.
- Be honest about gaps. Sugar-coating does not help the candidate.
- Cite specifics (skills, projects, numbers) from both the profile and the job posting.
- Be concise. No filler.
"""

USER_TEMPLATE_FULL = """CANDIDATE PROFILE:
{profile}

---

JOB POSTING:
{job}

---

Produce an analysis with EXACTLY this structure:

## Fit score
A score from 0 to 100. One sentence explaining it.

## Top 5 matching points
List the 5 strongest overlaps. Cite specifics from both.

## Gaps and risks
List 3-5 main gaps or risks. Be honest.

## Red flags in the posting
Anything suspicious: unrealistic requirements, vague responsibilities, mismatched seniority, etc. If nothing, say "None".

## Recommendation
One of: STRONG FIT / GOOD FIT / WORTH APPLYING WITH TAILORING / WEAK FIT / SKIP.
One paragraph of justification.
"""

SYSTEM_PROMPT_QUICK = """You are a critical job search assistant. Score how well the candidate fits the job posting.

Before scoring, check these RED FLAGS:
1. Seniority mismatch: does the title say Staff, Principal, Senior, Lead, Director, Head?
   The candidate has 3+ years of R&D experience and is currently transitioning into data roles.
2. Experience years: does it require 5+ years of hands-on experience? The candidate has
   3+ years in chemistry R&D, not in software engineering or AI infrastructure.
3. Degree field: does it require a degree in Computer Science or Electrical Engineering?
   The candidate has a Master in Industrial Chemistry.
4. Domain mismatch: does it require specialized engineering skills such as semiconductor,
   GPU computing, OpenCL, Vulkan, CUDA, TensorRT, OpenVINO, MLIR, or ONNXRuntime?
   The candidate does not have these.

If ANY red flag applies, the score MUST be below 50 and the recommendation MUST be
WEAK FIT or SKIP.

Reply ONLY in this exact format, nothing else, no preamble:
SCORE: <integer 0-100>
RECOMMENDATION: <STRONG FIT | GOOD FIT | WORTH APPLYING WITH TAILORING | WEAK FIT | SKIP>
REASON: <one sentence, max 30 words>
"""

USER_TEMPLATE_QUICK = """CANDIDATE PROFILE:
{profile}

---

JOB POSTING:
{job}

---

Score the fit. Check the red flags first. Reply in the exact format specified, nothing else.
"""

# ---------------------------------------------------------------------------
# Heuristic pre-filter (used in --strict mode)
# ---------------------------------------------------------------------------

def _extract_min_years(text: str) -> int | None:
    """Extract the minimum years of experience mentioned in the posting, if any."""
    patterns = [
        r"(?:minimum|min\.?|at least)\s+(?:of\s+)?(\d+)\s*\+?\s*years",
        r"(\d+)\s*\+\s*years",
        r"typically\s+(\d+)\s*\+?\s*years",
        r"(\d+)\s+years\s+(?:of\s+)?(?:hands-on\s+|professional\s+)?experience",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                found.append(int(m.group(1)))
            except (ValueError, IndexError):
                pass
    return max(found) if found else None


def _score_to_rec(score: int) -> str:
    if score < 30:
        return "SKIP"
    if score < 50:
        return "WEAK FIT"
    if score < 75:                          # era 65
        return "WORTH APPLYING WITH TAILORING"
    if score < 90:                          # era 80
        return "GOOD FIT"
    return "STRONG FIT"


def prefilter_job(job_text: str, job_title: str) -> tuple:
    """
    Heuristic pre-filter for obvious mismatches.

    Returns:
        (skip, max_score, reasons)
        - skip (bool): if True, the LLM should not be called at all.
        - max_score (int): cap to apply to the LLM's score (0-100).
        - reasons (list[str]): human-readable reasons for the cap/skip.
    """
    reasons = []
    max_score = 100
    title_lower = job_title.lower()
    text_lower = job_text.lower()

    # --- 1. Seniority in title ---
    seniority_rules = [
        (["staff engineer", "staff software", "staff scientist", "staff data", "staff "], 15, "staff-level title"),
        (["principal"], 15, "principal-level title"),
        (["director", "head of", "vp of", "vice president"], 10, "director/head-level title"),
        (["tech lead", "team lead", "engineering lead", "lead "], 30, "lead-level title"),
        (["senior ", "sr. ", "sr "], 45, "senior-level title"),
        (["manager"], 40, "manager-level title"),
    ]
    for keywords, cap, label in seniority_rules:
        if any(k in title_lower for k in keywords):
            max_score = min(max_score, cap)
            reasons.append(f"Title indicates {label}")
            break

    # --- 2. Years of experience ---
    min_years = _extract_min_years(job_text)
    if min_years is not None:
        if min_years >= 8:
            max_score = min(max_score, 20)
            reasons.append(f"Requires {min_years}+ years of experience")
        elif min_years >= 6:
            max_score = min(max_score, 40)
            reasons.append(f"Requires {min_years}+ years of experience")
        elif min_years >= 5:
            max_score = min(max_score, 50)
            reasons.append(f"Requires {min_years}+ years of experience")

    # --- 3. Degree field ---
    degree_rules = [
        (["phd in computer science", "ph.d. in computer science",
          "phd in cs", "ph.d. in cs", "doctorate in computer science"], 20,
         "PhD in Computer Science required"),
        (["ms in computer science", "m.s. in computer science",
          "master in computer science", "bs in computer science",
          "b.s. in computer science", "bachelor in computer science"], 40,
         "CS degree required"),
        (["ms in electrical engineering", "bs in electrical engineering",
          "m.s. in electrical engineering", "b.s. in electrical engineering",
          "degree in electrical engineering"], 40,
         "EE degree required"),
    ]
    for phrases, cap, label in degree_rules:
        if any(p in text_lower for p in phrases):
            max_score = min(max_score, cap)
            reasons.append(label)
            break

    # --- 4. Specialized skills ---
    hard_skills = [
        "openvino", "tensorrt", "mlir", "onnxruntime", "tvm",
        "opencl", "vulkan", "cuda programming",
        "verilog", "vhdl", "fpga design",
        "quantization, compression and pruning",
    ]
    matched = [s for s in hard_skills if s in text_lower]
    if len(matched) >= 2:
        max_score = min(max_score, 25)
        reasons.append(f"Requires specialized skills: {', '.join(matched[:3])}")
    elif len(matched) == 1:
        max_score = min(max_score, 40)
        reasons.append(f"Requires specialized skill: {matched[0]}")

    # --- 5. Languages ---
    language_rules = [
    # Dutch requirements — many phrasings
    (["vloeiend nederlands", "fluent dutch", "native dutch",
        "nederlands als moedertaal", "uitgebreide kennis van nederlands",
        "goede kennis van het nederlands", "kennis van het nederlands",
        "nederlands en frans", "nederlands of frans", "nl/fr", "nl en fr",
        "dutch (native", "dutch and french", "dutch or french",
        "nederlandstalig", "nederlandstalige"],
        25, "Requires Dutch (candidate has A1)"),
    # French requirements
    (["vloeiend frans", "fluent french", "native french", "français courant",
        "maîtrise du français", "excellent niveau en français",
        "connaissance du français", "français et néerlandais",
        "français ou néerlandais", "french (native",
        "french and dutch", "french or dutch", "francophone"],
        30, "Requires French (not in candidate profile)"),
    # German
    (["vloeiend duits", "fluent german", "deutschkenntnisse",
        "german (native", "sehr gute deutschkenntnisse"],
        35, "Requires German"),
    ]
    for phrases, cap, label in language_rules:
        if any(p in text_lower for p in phrases):
            max_score = min(max_score, cap)
            reasons.append(label)

    # --- 6. Specific degree titles that don't match ---
    specific_degrees = [
        (["ingénieur civil", "ingenieur burgerlijk", "burgerlijk ingenieur"],
         35, "Requires 'ingénieur civil' / 'burgerlijk ingenieur' degree"),
        (["école royale militaire", "koninklijke militaire school"],
         25, "Requires military academy background"),
        (["phd in chemistry", "doctorat en chimie", "doctoraat in de chemie"],
         40, "Requires PhD in Chemistry (candidate has MSc)"),
    ]
    for phrases, cap, label in specific_degrees:
        if any(p in text_lower for p in phrases):
            max_score = min(max_score, cap)
            reasons.append(label)

    # --- 7. Domain mismatch: finance/banking without chemistry link ---
    finance_keywords = [
        "banking", "bank ", "banque", "banken", "insurance", "verzekering",
        "assurance", "credit institution", "financial sector",
        "secteur financier", "financial services", "asset management",
        "investment management", "wealth management", "trading",
        "fintech", "payment services", "retail banking",
    ]
    chemistry_keywords = [
        "chemistry", "chemical", "materials", "polymer", "formulation",
        "coating", "ink", "photoinitiator", "catalysis", "catalyst",
        "specialty chemicals", "materials science", "rheology",
    ]
    finance_matches = [s for s in finance_keywords if s in text_lower]
    has_chemistry = any(c in text_lower for c in chemistry_keywords)
    if len(finance_matches) >= 1 and not has_chemistry:
        max_score = min(max_score, 30)
        reasons.append("Finance/banking/insurance domain without chemistry link")

    # --- 8. PhD / doctoral positions: accept if in target domain, reject otherwise ---
    phd_markers = ["phd position", "phd researcher", "phd vacancy",
                   "phd student", "doctoral position", "doctoral researcher",
                   "doctoraat", "promotion", "thèse de doctorat"]
    
    # Domains where a PhD is a great fit for the candidate
    phd_target_domains = [
        "materials science", "materials informatics", "computational chemistry",
        "cheminformatics", "chemical engineering", "process systems engineering",
        "formulation", "polymer", "catalysis", "rheology",
        "machine learning for chemistry", "ai for science", "data-driven chemistry"
    ]
    
    is_phd = any(m in title_lower or m in text_lower[:500] for m in phd_markers)
    if is_phd:
        # Check if it's in a target domain
        in_target_domain = any(d in text_lower for d in phd_target_domains)
        if not in_target_domain:
            max_score = min(max_score, 20)
            reasons.append("PhD/doctoral position outside target domain")
        else:
            reasons.append("PhD/doctoral position in target domain (eligible)")

    skip = max_score <= 20
    return skip, max_score, reasons


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_job_header(text: str) -> dict:
    """Extract Title/Company/URL/Location from the header of a saved job file."""
    meta = {}
    labels = {"Title:": "title", "Company:": "company",
              "URL:": "url", "Location:": "location"}
    for line in text.splitlines()[:12]:
        for label, key in labels.items():
            if line.startswith(label):
                meta[key] = line[len(label):].strip()
    return meta


def parse_quick_response(text: str) -> dict:
    """Parse SCORE / RECOMMENDATION / REASON lines from the quick-mode output."""
    score, rec, reason = None, None, ""
    m = re.search(r"SCORE:\s*(\d+)", text)
    if m:
        score = int(m.group(1))
    m = re.search(r"RECOMMENDATION:\s*([A-Za-z ]+)", text)
    if m:
        rec = m.group(1).strip().upper()
    m = re.search(r"REASON:\s*(.+)", text)
    if m:
        reason = m.group(1).strip()
    return {"score": score, "recommendation": rec, "reason": reason}


def parse_full_response(text: str) -> dict:
    """Parse fit score and recommendation from the full-mode output."""
    score, rec = None, None
    m = re.search(r"##\s*Fit score\s*\n+\s*(\d+)", text)
    if m:
        score = int(m.group(1))
    m = re.search(r"##\s*Recommendation\s*\n+\s*([A-Z ]+)", text)
    if m:
        rec = m.group(1).strip().upper()
    return {"score": score, "recommendation": rec}


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_one(job_path: Path, profile: str, quick: bool,
                extra_files: list = None, strict: bool = False) -> dict:
    """Analyze a single job file and write its report + metadata file.

    Args:
        job_path: Path to the job posting .txt file.
        profile: The candidate profile text (already loaded).
        quick: If True, use the quick triage prompt.
        extra_files: List of extra profile filenames that were included in
            the profile (for traceability in the metadata).
        strict: If True, run the heuristic pre-filter. Jobs with obvious
            mismatches (senior title, 5+ years, wrong degree, etc.) are either
            skipped entirely or have their score capped.
    """
    job_text = job_path.read_text(encoding="utf-8")
    header = parse_job_header(job_text)
    job_title = header.get("title", "")

    prefilter_info = {"applied": False, "skip": False, "cap": None, "reasons": []}

    if strict:
        skip, cap, reasons = prefilter_job(job_text, job_title)
        prefilter_info = {
            "applied": True,
            "skip": skip,
            "cap": cap if cap < 100 else None,
            "reasons": reasons,
        }

    # --- Branch A: pre-filter decided to skip entirely ---
    if strict and prefilter_info["skip"]:
        response = (
            "[PREFILTERED] This job was skipped without an LLM call due to "
            "obvious mismatches.\n\nReasons:\n"
            + "\n".join(f"- {r}" for r in prefilter_info["reasons"])
        )
        parsed = {
            "score": 0,
            "recommendation": "SKIP",
            "reason": "; ".join(prefilter_info["reasons"]),
        }
    else:
        # --- Branch B: normal LLM path ---
        if quick:
            prompt = USER_TEMPLATE_QUICK.format(profile=profile, job=job_text)
            system = SYSTEM_PROMPT_QUICK
        else:
            prompt = USER_TEMPLATE_FULL.format(profile=profile, job=job_text)
            system = SYSTEM_PROMPT_FULL

        response = generate(MODEL, prompt, system=system, num_ctx=8192)
        parsed = parse_quick_response(response) if quick else parse_full_response(response)
        
        # Recompute the label from the score — the LLM's label is often inconsistent
        if parsed.get("score") is not None:
            parsed["recommendation"] = _score_to_rec(parsed["score"])

        # Apply the cap if strict mode set one
        if prefilter_info["cap"] is not None:
            current_score = parsed.get("score")
            if current_score is not None and current_score > prefilter_info["cap"]:
                parsed["score"] = prefilter_info["cap"]
                parsed["recommendation"] = _score_to_rec(prefilter_info["cap"])
                cap_note = "CAPPED: " + "; ".join(prefilter_info["reasons"])
                old_reason = parsed.get("reason", "") or ""
                parsed["reason"] = (old_reason + " | " + cap_note).strip(" |")[:300]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = job_path.stem
    report_path = OUTPUTS_DIR / f"{stem}.md"
    meta_path = OUTPUTS_DIR / f"{stem}.meta.json"

    report_path.write_text(
        f"# Analysis: {job_path.name}\n\n"
        f"**Source file:** `{job_path.name}`  \n"
        f"**Analyzed at:** {timestamp}  \n"
        f"**Mode:** {'quick' if quick else 'full'}"
        f"{' + strict' if strict else ''}\n\n"
        + response,
        encoding="utf-8",
    )

    meta = {
        "job_file": job_path.name,
        "title": header.get("title", "N/A"),
        "company": header.get("company", "N/A"),
        "url": header.get("url", "N/A"),
        "location": header.get("location", "N/A"),
        "score": parsed.get("score"),
        "recommendation": parsed.get("recommendation", "N/A"),
        "reason": parsed.get("reason", ""),
        "analyzed_at": timestamp,
        "mode": "quick" if quick else "full",
        "strict": strict,
        "extra_files": extra_files or [],
        "prefilter": prefilter_info,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def should_skip(meta_path: Path, current_mode: str, strict: bool) -> bool:
    """True if this job was already analyzed in the same mode and strict setting."""
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if meta.get("mode") != current_mode:
        return False
    # In strict mode, re-analyze jobs that were previously analyzed without strict
    if strict and not meta.get("strict", False):
        return False
    return True


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def build_summary() -> Path:
    """Read all *.meta.json and produce a single ranked summary report."""
    metas = []
    for p in sorted(OUTPUTS_DIR.glob("*.meta.json")):
        try:
            metas.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[WARN] could not read {p.name}: {e}")

    metas.sort(key=lambda m: (m.get("score") is None, -(m.get("score") or 0)))

    lines = [
        "# Job search summary",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Total jobs analyzed: {len(metas)}",
        "",
        "| Score | Rec | Company | Title | Prefilter | File |",
        "|------:|-----|---------|-------|-----------|------|",
    ]
    for m in metas:
        score = m.get("score")
        score_s = str(score) if score is not None else "?"
        rec = (m.get("recommendation") or "N/A")
        company = (m.get("company") or "N/A").replace("|", "-")
        title = (m.get("title") or "N/A").replace("|", "-")
        pre = m.get("prefilter", {})
        if pre.get("skip"):
            pre_s = "SKIP"
        elif pre.get("cap"):
            pre_s = f"cap {pre['cap']}"
        elif pre.get("reasons"):
            pre_s = "flag"
        else:
            pre_s = "-"
        fname = m.get("job_file", "N/A")
        lines.append(f"| {score_s} | {rec} | {company} | {title} | {pre_s} | `{fname}` |")

    lines += [
        "",
        "## How to read this",
        "",
        "- **STRONG FIT**: apply immediately, tailor CV.",
        "- **GOOD FIT**: apply, tailor CV.",
        "- **WORTH APPLYING WITH TAILORING**: apply only if genuinely interested.",
        "- **WEAK FIT**: probably skip.",
        "- **SKIP**: do not apply.",
        "",
        "**Prefilter column**:",
        "- `-`: no pre-filter applied (strict mode off).",
        "- `flag`: a red flag was detected but score was not capped (borderline).",
        "- `cap N`: score was capped at N by the pre-filter.",
        "- `SKIP`: job was skipped without an LLM call (obvious mismatch).",
        "",
    ]

    out = OUTPUTS_DIR / "_summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batch-analyze all jobs in jobs/.")
    parser.add_argument("--quick", action="store_true",
                        help="Quick triage mode: only score, recommendation, reason.")
    parser.add_argument("--strict", action="store_true",
                        help="Enable heuristic pre-filter: skip or cap scores for "
                             "obvious mismatches (senior titles, 5+ years, wrong degree, "
                             "specialized skills). Recommended.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Analyze at most N jobs (for testing).")
    parser.add_argument("--filter", default=None,
                        help="Only analyze jobs whose filename contains this substring.")
    parser.add_argument("--reset", action="store_true",
                        help="Re-analyze jobs even if a report already exists.")
    parser.add_argument("--summary-only", action="store_true",
                        help="Skip analysis, just regenerate the summary.")
    parser.add_argument("--extra-files", nargs="*", default=[],
                        help="Additional profile files to include in the prompt "
                             "(e.g. 03_education_skills.md 04_projects.md).")
    args = parser.parse_args()

    OUTPUTS_DIR.mkdir(exist_ok=True)

    if args.summary_only:
        path = build_summary()
        print(f"[DONE] summary written to {path}")
        return

    if not JOBS_DIR.exists():
        print(f"[ERROR] jobs directory not found: {JOBS_DIR}")
        return

    job_files = sorted(JOBS_DIR.glob("*.txt"))
    if args.filter:
        job_files = [p for p in job_files if args.filter.lower() in p.name.lower()]
    if args.limit:
        job_files = job_files[:args.limit]

    if not job_files:
        print("[INFO] no job files to analyze.")
        return

    mode = "quick" if args.quick else "full"
    print(f"[INFO] {len(job_files)} job files found.")
    print(f"[INFO] mode: {mode}{' + strict' if args.strict else ''}")
    if args.extra_files:
        print(f"[INFO] extra profile files: {', '.join(args.extra_files)}")
    if args.quick:
        print("[INFO] estimated time: ~30-60s per job on CPU.")
    else:
        print("[INFO] estimated time: ~1-3 min per job on CPU.")
    print("[INFO] use Ctrl+C to interrupt. Progress is saved per job.\n")

    if args.extra_files:
        profile_files = ["01_profile.md", "02_experiences.md", "06_cv_master.md"] + args.extra_files
    else:
        profile_files = None
    profile = load_profile(files=profile_files)

    n_done, n_skipped, n_failed, n_prefiltered = 0, 0, 0, 0
    for i, job_path in enumerate(job_files, start=1):
        meta_path = OUTPUTS_DIR / f"{job_path.stem}.meta.json"
        if not args.reset and should_skip(meta_path, mode, args.strict):
            print(f"[{i}/{len(job_files)}] [SKIP] {job_path.name}")
            n_skipped += 1
            continue

        print(f"[{i}/{len(job_files)}] [RUN ] {job_path.name}")
        try:
            meta = analyze_one(job_path, profile, quick=args.quick,
                               extra_files=args.extra_files, strict=args.strict)
            note = ""
            pre = meta.get("prefilter", {})
            if pre.get("skip"):
                note = " [PREFILTERED]"
                n_prefiltered += 1
            elif pre.get("cap"):
                note = f" [capped at {pre['cap']}]"
            print(f"           -> score={meta.get('score')} rec={meta.get('recommendation')}{note}")
            n_done += 1
        except KeyboardInterrupt:
            print("\n[INFO] interrupted by user.")
            break
        except Exception as e:
            print(f"           [WARN] failed: {e}")
            n_failed += 1

    print(f"\n[DONE] analyzed={n_done}, skipped={n_skipped}, "
          f"prefiltered={n_prefiltered}, failed={n_failed}")

    summary_path = build_summary()
    print(f"[DONE] summary written to {summary_path}")


if __name__ == "__main__":
    main()