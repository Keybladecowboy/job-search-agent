# Job Search Automation Agent

A Python pipeline that discovers relevant job postings from multiple free
sources, uses an LLM to judge fit against a candidate profile (not just
keyword matching), and generates tailored resume/cover letter drafts for
the roles worth applying to - with all results tracked in a running log.

## Why this exists

Job searching at volume means the same repetitive work for every posting:
find it, judge whether it's actually a fit, rewrite your resume summary to
match, draft a cover letter, keep track of what you've sent. This project
automates that pipeline end to end while keeping a human in the loop for
the final decision.

## How it works

```
fetch_jobs.py                    tailor_jobs.py
┌─────────────────┐              ┌──────────────────────────┐
│ RemoteOK API     │              │ 1. Fit check (cheap LLM  │
│ Arbeitnow API    │──jobs_found──▶   call per job, scores   │
│ Adzuna API       │   .json      │   1-10 against profile)  │
└─────────────────┘              │ 2. Full tailoring (only   │
                                  │   for jobs that pass the  │
                                  │   threshold)               │
                                  └───────────┬───────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                                       ▼
                 applications/*.md                    applications_log.csv
                 (tailored resume +                   (company, role, fit
                  cover letter per job)                 score, status)
```

**Fetching** pulls from three free, no-signup-required job APIs, using a
deliberately broad keyword net (single words like "risk," "operations,"
"data") rather than narrow phrase matching - the filtering precision is
handled by the LLM step, not brittle keyword rules.

**Triage** uses a cheap, fast model to screen every job against the
candidate's real profile before spending anything on full generation. This
is where the design gets its cost efficiency: a 50-job batch might only
generate 5-8 full tailored applications, because most postings get
correctly filtered out at the cheap-screening stage.

**Tailoring** generates a resume summary, a prioritized selection of real
achievements, and a full cover letter draft - grounded strictly in the
candidate's actual profile data (the prompt explicitly forbids inventing
experience).

**Tracking** logs every generated application to a CSV, with deduplication
so re-running the pipeline on an overlapping job set doesn't waste API
calls or create duplicate log entries.

## Design decisions worth noting

- **Provider-agnostic LLM layer** - `tailor_jobs.py` supports both Google
  Gemini (free tier, default) and Anthropic Claude (paid, higher quality)
  through a single `call_llm()` function. Switching providers is one
  environment variable, not a code change.
- **Two-tier LLM calls** - a cheap/fast model handles the high-volume
  screening step; a stronger model is reserved for the low-volume,
  higher-value generation step. This keeps a broad discovery net
  affordable.
- **Idempotent runs** - the pipeline can be re-run repeatedly on fresh job
  batches without reprocessing or duplicating anything already logged.

## Tech stack

Python · `requests` · Google Gemini API (`google-genai`) · Anthropic API
(`anthropic`) · JSON · CSV

## Setup

1. Clone the repo and fill in your own profile:
   ```
   cp profile/master_profile.template.json profile/master_profile.json
   ```
   (This file is gitignored - your personal data never leaves your machine.)
2. Install dependencies:
   ```
   pip install requests google-genai
   ```
3. Get a free API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   and set it:
   ```
   $env:GEMINI_API_KEY="your_key_here"
   ```
4. Run the pipeline:
   ```
   python scripts/fetch_jobs.py
   python scripts/tailor_jobs.py
   ```

See `target_companies.md` for notes on job sources that don't offer public
APIs (large enterprise career sites, niche industry boards) and how to
extend coverage to them manually.

## What's not automated (by design)

Applying is intentionally left to the candidate - this generates drafts
for review, not auto-submitted applications. Some job sources (enterprise
ATS platforms without public APIs, local/regional job boards) require
manual checking; see `target_companies.md`.

## Status

Actively used for a real job search, not a demo project. Built while
returning to Python after time away - the codebase is deliberately
readable and commented throughout.
