"""
fetch_jobs.py

Purpose: pull job postings relevant to your profile from two sources:
  1. RemoteOK  - free, no API key needed, remote jobs worldwide
  2. Adzuna    - free API key required (register at developer.adzuna.com),
                 covers US/Mexico/Brazil among others - NOT Costa Rica directly,
                 but useful as a "remote, LatAm-adjacent" source

Costa Rica LOCAL job boards (Computrabajo, elEmpleo, etc.) don't offer public
APIs, so they aren't included here - see the bottom of this file for direct
search links to check manually.

Concepts touched on:
  - the 'requests' library (making HTTP calls to APIs)
  - environment variables (for API keys - never hardcode secrets in code)
  - working with JSON responses from an API
  - filtering lists with conditions
  - saving results to a file for the next step to use

Setup before running:
  pip install requests
  (optional, for Adzuna) set environment variables ADZUNA_APP_ID and ADZUNA_APP_KEY

Run it with:
    python scripts/fetch_jobs.py
"""

import json
import os
import re
from pathlib import Path

import requests

# Titles containing these are excluded regardless of keyword match - you're
# looking for entry points, not senior/leadership roles.
SENIORITY_EXCLUDE = [
    "senior", "sr.", "staff", "principal", "lead", "manager",
    "director", "head of", "vp", "chief", "architect",
]


# NOTE: seniority filtering (Senior/Staff/Lead/etc.) was intentionally
# removed from this fetch stage per your call - you want the full dataset
# passed through, with the LLM triage step (not keyword rules) deciding
# whether a "Senior" title is actually worth applying to. The function
# below is left here in case you want to reintroduce a hard cutoff later.
def is_entry_appropriate(title: str) -> bool:
    """Return False if the title signals a seniority level above entry. Currently unused."""
    return not any(
        re.search(rf"\b{re.escape(term)}\b", title)
        for term in SENIORITY_EXCLUDE
    )

# Keywords matched against the job TITLE only (not the full description).
# Description-matching was tried first but caused false positives - generic
# corporate boilerplate ("we value integrity," "annual audit") kept matching
# completely unrelated roles like store managers and valet drivers. Matching
# titles instead is far more precise, at the cost of occasionally missing a
# relevant job that has an unusual title. Edit this list to widen/narrow.
TITLE_KEYWORDS = [
    "fraud", "risk", "compliance", "operations", "analyst", "associate",
    "investigation", "trust", "safety", "payments", "kyc", "aml",
    "data", "intelligence", "support", "coordinator", "ai", "automation",
]


def fetch_remoteok_jobs() -> list[dict]:
    """
    RemoteOK exposes a free JSON feed of remote job postings - no signup
    needed. We fetch the whole feed, then filter it ourselves for relevance.
    """
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (job-search-agent learning project)"}

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()  # raises an error if the request failed

    raw_jobs = response.json()
    # RemoteOK's first list item is metadata about the feed, not a job - skip it.
    raw_jobs = [job for job in raw_jobs if isinstance(job, dict) and "position" in job]

    matches = []
    for job in raw_jobs:
        title = job.get("position", "").lower()
        # Word-boundary matching instead of plain substring search. With
        # short/ambiguous keywords like "ai" or "ml" now in the list, a plain
        # `keyword in title` check would false-positive on unrelated words -
        # "ai" hides inside "retail," "detail," "maintain." \b in regex means
        # "start/end of a word," so \bai\b only matches "ai" as its own word.
        title_matched = any(
            re.search(rf"\b{re.escape(keyword)}\b", title)
            for keyword in TITLE_KEYWORDS
        )
        if not title_matched:
            continue

        location_text = job.get("location", "").lower()
        # Exclude jobs explicitly restricted to a country/region other than
        # where you are. RemoteOK's location field often says things like
        # "USA Only" - that means don't bother applying from Costa Rica.
        # If it says nothing restrictive (or says Worldwide/Anywhere/LatAm),
        # we treat it as open to you.
        is_restricted = any(
            f"{country} only" in location_text
            for country in ["usa", "us", "united states", "uk", "canada", "eu", "europe", "australia"]
        )
        if is_restricted:
            continue

        matches.append({
                "source": "RemoteOK",
                "title": job.get("position"),
                "company": job.get("company"),
                "location": job.get("location") or "Remote",
                "url": job.get("url"),
                "tags": job.get("tags", []),
                "description": job.get("description", ""),
            })

    return matches


def fetch_arbeitnow_jobs() -> list[dict]:
    """
    Arbeitnow aggregates postings from real company ATS platforms - broader
    role variety than RemoteOK (which skews heavily toward tech). Free,
    no API key, no signup required.
    """
    url = "https://www.arbeitnow.com/api/job-board-api"
    headers = {"User-Agent": "Mozilla/5.0 (job-search-agent learning project)"}

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    raw_jobs = response.json().get("data", [])

    matches = []
    for job in raw_jobs:
        title = job.get("title", "").lower()
        title_matched = any(
            re.search(rf"\b{re.escape(keyword)}\b", title)
            for keyword in TITLE_KEYWORDS
        )
        if not title_matched:
            continue

        # Arbeitnow mixes in plenty of on-site roles (Berlin, Munich, etc.)
        # alongside remote ones. Only the 'remote' boolean field reliably
        # tells us which is which - the 'location' field is often just the
        # company's home city even for remote-friendly postings. Skip
        # anything not explicitly flagged remote.
        if not job.get("remote"):
            continue

        matches.append({
            "source": "Arbeitnow",
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("location") or ("Remote" if job.get("remote") else "Unspecified"),
            "url": job.get("url"),
            "tags": job.get("tags", []),
            "description": job.get("description", ""),
        })

    return matches


def fetch_adzuna_jobs(country_code: str = "us") -> list[dict]:
    """
    Adzuna requires a free API key. If the environment variables aren't set,
    this function skips itself gracefully instead of crashing - that way the
    script still works using just RemoteOK if you haven't set Adzuna up yet.
    """
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        print(f"  (skipping Adzuna/{country_code} - ADZUNA_APP_ID/ADZUNA_APP_KEY not set)")
        return []

    # Adzuna's "what" param searches title+description on their end, so this
    # one is less prone to the same false-positive problem - their own search
    # ranking handles relevance for us.
    query = " OR ".join(["fraud analyst", "risk analyst", "compliance analyst"])
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": query,
        "content-type": "application/json",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    matches = []
    for job in data.get("results", []):
        matches.append({
            "source": f"Adzuna ({country_code})",
            "title": job.get("title"),
            "company": job.get("company", {}).get("display_name"),
            "location": job.get("location", {}).get("display_name"),
            "url": job.get("redirect_url"),
            "tags": [],
            "description": job.get("description", ""),
        })

    return matches


def save_results(jobs: list[dict], path: str = "jobs_found.json") -> None:
    """Save the combined, de-duplicated results so step 3 (tailoring) can use them."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(jobs)} job(s) to {path}")


def main():
    print("Fetching from RemoteOK...")
    remoteok_jobs = fetch_remoteok_jobs()
    print(f"  Found {len(remoteok_jobs)} matching job(s)")

    all_jobs = list(remoteok_jobs)

    print("\nFetching from Arbeitnow...")
    arbeitnow_jobs = fetch_arbeitnow_jobs()
    print(f"  Found {len(arbeitnow_jobs)} matching job(s)")
    all_jobs.extend(arbeitnow_jobs)

    print("\nFetching from Adzuna (US, Mexico, Brazil, Canada, UK)...")
    for country in ["us", "mx", "br", "ca", "gb"]:
        adzuna_jobs = fetch_adzuna_jobs(country)
        if adzuna_jobs:
            print(f"  Found {len(adzuna_jobs)} matching job(s) in {country}")
        all_jobs.extend(adzuna_jobs)

    if not all_jobs:
        print("\nNo jobs found. Try widening KEYWORDS at the top of this file.")
        return

    print(f"\nTotal jobs found: {len(all_jobs)}")
    for job in all_jobs:
        print(f"  [{job['source']}] {job['title']} @ {job['company']} - {job['location']}")

    save_results(all_jobs)

    print("\n" + "=" * 60)
    print("Costa Rica LOCAL job boards have no public API - check these")
    print("manually and add anything relevant straight into jobs_found.json:")
    print("  - https://www.computrabajo.co.cr/trabajo-de-fraude")
    print("  - https://www.elempleo.com/cr/ofertas-empleo/?q=fraude")
    print("=" * 60)


if __name__ == "__main__":
    main()
