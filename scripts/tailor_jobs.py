"""
tailor_jobs.py

Purpose: the LLM reasoning step. For every job in jobs_found.json:
  1. FIT CHECK (cheap, fast model) - "does this job make sense for this
     candidate?" Returns a score 1-10 and a one-sentence reason. This is
     where a title like "Vendor Operations Coordinator" gets correctly
     recognized as a fit even though no keyword rule would catch it.
  2. TAILORING (stronger model, only for jobs that pass the fit check) -
     generates a tailored resume summary + bullet selection + cover letter
     draft, saved as a Markdown file you can copy from.

PROVIDER SUPPORT: this script works with either Google Gemini (free,
recommended for running this without cost) or Anthropic Claude (paid,
higher quality). Set LLM_PROVIDER below or via environment variable.
Building it this way - one script, swappable backend - is itself a solid
thing to show in a portfolio: it demonstrates API abstraction rather than
hardcoding a single vendor.

Concepts touched on:
  - calling an external API with a structured prompt
  - asking a model to return JSON, then parsing it safely
  - two-tier processing (cheap filter -> expensive step) to control cost
  - try/except per-item so one bad response doesn't kill the whole run
  - writing files with dynamic names built from data
  - a small provider-abstraction layer (one function, two backends)

Setup before running - pick ONE:

  Option A (FREE - recommended for testing/demoing):
    pip install google-genai
    Get a free API key at aistudio.google.com/apikey (no credit card)
    $env:GEMINI_API_KEY="your_key_here"          (PowerShell)
    $env:LLM_PROVIDER="gemini"

  Option B (paid, higher quality):
    pip install anthropic
    Get a key at console.anthropic.com (billed per use)
    $env:ANTHROPIC_API_KEY="your_key_here"       (PowerShell)
    $env:LLM_PROVIDER="claude"

Run it with:
    python scripts/tailor_jobs.py
"""

import json
import os
import re
import time
from pathlib import Path

# Jobs scoring at or above this out of 10 get full tailoring generated.
# Lower this to generate more applications, raise it to be pickier.
FIT_THRESHOLD = 6

# Which backend to use - "gemini" (free) or "claude" (paid). Can be
# overridden with the LLM_PROVIDER environment variable.
PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()

# Model names per provider. Gemini's free tier is rate-limited (a handful
# of requests per minute), so we pause longer between calls for it.
MODELS = {
    "gemini": {"triage": "gemini-3.5-flash-lite", "tailor": "gemini-3.5-flash"},
    "claude": {"triage": "claude-haiku-4-5-20251001", "tailor": "claude-sonnet-5"},
}
SLEEP_SECONDS = {"gemini": 4.5, "claude": 0.3}


def call_llm(prompt: str, max_tokens: int, model_tier: str) -> str:
    """
    Provider-agnostic call: send a prompt, get back text. This is the one
    function that knows about vendor-specific SDKs - everything else in
    this file just calls call_llm() and doesn't care which provider is
    behind it.
    """
    model = MODELS[PROVIDER][model_tier]

    if PROVIDER == "gemini":
        from google import genai
        client = genai.Client()  # reads GEMINI_API_KEY from environment
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text

    elif PROVIDER == "claude":
        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {PROVIDER!r} - use 'gemini' or 'claude'")


def load_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_json(text: str) -> dict:
    """
    Models sometimes wrap JSON in explanation text or code fences even when
    asked not to. This pulls out just the {...} block so json.loads() doesn't
    choke on surrounding text.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(match.group(0))


def fit_check(profile: dict, job: dict) -> dict:
    """
    Ask the model whether this job is worth pursuing given the profile.
    Kept short and cheap - low max_tokens, no need for the model to write
    prose here, just a score and a one-line reason.
    """
    prompt = f"""You are screening job postings for a candidate. Given the candidate's
background and a job posting, judge whether this is worth them applying to -
even if the job title doesn't obviously match their most recent role, look
for transferable experience (e.g. someone with investigation/case-management
experience could fit an operations or coordinator role, not just "analyst"
titles).

CANDIDATE SUMMARY:
{profile.get('summary', '')}

CANDIDATE SKILLS: {', '.join(profile.get('skills', {}).get('other', []) + profile.get('skills', {}).get('languages', []) + profile.get('skills', {}).get('frameworks_tools', []))}

CANDIDATE RECENT EXPERIENCE:
{chr(10).join(f"- {e.get('title')} at {e.get('organization')}" for e in profile.get('experience', [])[:4])}

JOB POSTING:
Title: {job.get('title')}
Company: {job.get('company')}
Description: {job.get('description', '')[:1500]}

Respond with ONLY a JSON object, no other text:
{{"score": <1-10 integer>, "reason": "<one sentence>"}}"""

    text = call_llm(prompt, max_tokens=150, model_tier="triage")
    return extract_json(text)


def tailor_application(profile: dict, job: dict) -> dict:
    """
    For a job that passed the fit check: generate a tailored resume summary,
    a selection of the most relevant achievements, and a cover letter draft.
    """
    prompt = f"""You are helping a candidate tailor their application to a specific job.
Use ONLY real information from their profile below - do not invent
experience, skills, or achievements they don't have. Select and rephrase
what's genuinely relevant; don't fabricate a fit that isn't there.

CANDIDATE PROFILE (full):
{json.dumps(profile, indent=2, ensure_ascii=False)}

JOB POSTING:
Title: {job.get('title')}
Company: {job.get('company')}
Description: {job.get('description', '')[:3000]}

Produce a JSON object with:
- "tailored_summary": a 2-3 sentence professional summary rewritten for THIS job
- "relevant_achievements": an array of 4-6 bullet points pulled/rephrased from
  the candidate's real experience/projects, prioritized by relevance to this job
- "cover_letter": a full cover letter draft (3-4 short paragraphs), professional
  but not generic - reference something specific from the job posting

Respond with ONLY the JSON object, no other text, no markdown code fences."""

    text = call_llm(prompt, max_tokens=1500, model_tier="tailor")
    return extract_json(text)


def safe_filename(text: str) -> str:
    """Turn a job title/company into a filesystem-safe filename."""
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s]+", "_", text).strip("_")[:60]


def save_application(job: dict, fit: dict, tailored: dict, output_dir: Path) -> Path:
    filename = f"{safe_filename(job.get('company', 'unknown'))}_{safe_filename(job.get('title', 'role'))}.md"
    path = output_dir / filename

    content = f"""# {job.get('title')} @ {job.get('company')}

**Source:** {job.get('source')}
**Location:** {job.get('location')}
**URL:** {job.get('url')}
**Fit score:** {fit.get('score')}/10 - {fit.get('reason')}

## Tailored Summary

{tailored.get('tailored_summary', '')}

## Relevant Achievements to Highlight

{chr(10).join('- ' + a for a in tailored.get('relevant_achievements', []))}

## Cover Letter Draft

{tailored.get('cover_letter', '')}
"""
    path.write_text(content, encoding="utf-8")
    return path


def append_to_log(job: dict, fit: dict, applied: bool, log_path: str = "applications_log.csv") -> None:
    """
    Append one row to the tracking CSV every time a tailored application is
    generated. Creates the file with a header row on first use.
    """
    import csv
    from datetime import date

    log_file = Path(log_path)
    is_new_file = not log_file.exists()

    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow([
                "date_generated", "company", "title", "source", "location",
                "fit_score", "url", "applied", "date_applied", "status", "notes",
            ])
        writer.writerow([
            date.today().isoformat(),
            job.get("company", ""),
            job.get("title", ""),
            job.get("source", ""),
            job.get("location", ""),
            fit.get("score", ""),
            job.get("url", ""),
            "yes" if applied else "no",
            "",  # date_applied - fill in by hand once you actually apply
            "generated",  # status - update by hand: applied / interview / rejected / offer
            "",  # notes - free text for your own use
        ])


def load_already_processed(log_path: str = "applications_log.csv") -> set:
    """
    Read URLs already in the tracking log so re-running this script on a
    fresh jobs_found.json doesn't re-tailor (and re-log, and waste API
    calls on) a job you've already processed in a previous run.
    """
    import csv

    log_file = Path(log_path)
    if not log_file.exists():
        return set()

    with open(log_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["url"] for row in reader if row.get("url")}


def main():
    jobs = load_json("jobs_found.json")
    profile = load_json("profile/master_profile.json")

    already_processed = load_already_processed()
    if already_processed:
        print(f"Skipping {len(already_processed)} already-processed job(s) from previous runs.\n")

    output_dir = Path("applications")
    output_dir.mkdir(exist_ok=True)

    sleep_time = SLEEP_SECONDS.get(PROVIDER, 1.0)
    print(f"Using provider: {PROVIDER} (triage: {MODELS[PROVIDER]['triage']}, tailor: {MODELS[PROVIDER]['tailor']})")
    print(f"Screening {len(jobs)} job(s)...\n")

    generated = 0
    for i, job in enumerate(jobs, 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        if job.get("url") in already_processed:
            print(f"[{i}/{len(jobs)}] {title} @ {company} - already processed, skipping")
            continue

        print(f"[{i}/{len(jobs)}] {title} @ {company}")

        try:
            fit = fit_check(profile, job)
        except Exception as e:
            print(f"  Fit check failed: {e}")
            time.sleep(sleep_time)
            continue

        score = fit.get("score", 0)
        print(f"  Fit score: {score}/10 - {fit.get('reason', '')}")

        if score < FIT_THRESHOLD:
            print("  Skipping (below threshold)")
            time.sleep(sleep_time)
            continue

        try:
            tailored = tailor_application(profile, job)
            path = save_application(job, fit, tailored, output_dir)
            append_to_log(job, fit, applied=False)
            print(f"  Saved tailored application -> {path}")
            print(f"  Logged to applications_log.csv")
            generated += 1
        except Exception as e:
            print(f"  Tailoring failed: {e}")

        time.sleep(sleep_time)  # be polite to the API, respect rate limits

    print(f"\nDone. Generated {generated} tailored application(s) in '{output_dir}/'.")


if __name__ == "__main__":
    main()
