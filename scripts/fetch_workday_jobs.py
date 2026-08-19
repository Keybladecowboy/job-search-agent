"""
fetch_workday_jobs.py

Purpose: pull job postings directly from Workday-powered career sites
(large enterprises like HPE run their hiring on Workday - URLs that look
like {company}.wd5.myworkdayjobs.com).

This is a bit more involved than RemoteOK/Adzuna because Workday's job
search API:
  - requires a POST request with a JSON body (not a simple GET)
  - paginates with limit/offset instead of a page number
  - needs the exact tenant/site/server values read off the real URL -
    there's no way to guess them reliably company to company

Concepts touched on:
  - POST requests with a JSON body (vs. GET with query params)
  - pagination loops (fetching page after page until done)
  - dictionaries as configuration (COMPANIES below)
  - string formatting with f-strings to build URLs

How to find a new company's config (if you want to add one beyond HPE):
  1. Go to their careers page - if the URL contains "myworkdayjobs.com",
     they're on Workday.
  2. The URL shape is: https://{tenant}.{wd_server}.myworkdayjobs.com/{locale}/{site}
     e.g. https://hpe.wd5.myworkdayjobs.com/en-US/Jobsathpe
       -> tenant = "hpe", wd_server = "wd5", site = "Jobsathpe"
  3. Add an entry to COMPANIES below with those three values.

Run it with:
    python scripts/fetch_workday_jobs.py
"""

import json
import time
from pathlib import Path

import requests

TITLE_KEYWORDS = [
    "fraud", "risk analyst", "risk & compliance", "compliance analyst",
    "compliance officer", "kyc", "aml", "anti-money laundering",
    "fraud investigator", "account integrity", "trust & safety",
    "audit", "investigation",
]

# Only keep postings whose location text contains one of these - edit to
# widen. Costa Rica postings usually say "Costa Rica" or a city like "Heredia".
LOCATION_KEYWORDS = ["costa rica", "heredia", "san jose", "remote"]

# Add more companies here as you find their tenant/site/server values.
COMPANIES = {
    "HPE": {"tenant": "hpe", "wd_server": "wd5", "site": "Jobsathpe"},
}

PAGE_SIZE = 20


def fetch_workday_jobs(company_name: str, tenant: str, wd_server: str, site: str) -> list[dict]:
    """
    Paginate through a Workday tenant's job listings, collecting all
    postings. Workday returns a fixed page size (we ask for 20 at a time)
    and a 'total' count telling us when to stop.
    """
    base_url = f"https://{tenant}.{wd_server}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (job-search-agent learning project)",
        "Referer": f"https://{tenant}.{wd_server}.myworkdayjobs.com/en-US/{site}",
    }

    all_postings = []
    offset = 0

    while True:
        payload = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""}
        response = requests.post(base_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()

        postings = data.get("jobPostings", [])
        all_postings.extend(postings)

        total = data.get("total", 0)
        offset += PAGE_SIZE

        # Be polite: pause briefly between requests instead of hammering
        # their server with a rapid-fire loop.
        time.sleep(0.5)

        if offset >= total or not postings:
            break

    return all_postings


def filter_postings(company_name: str, postings: list[dict]) -> list[dict]:
    """Keep only postings matching both a relevant title and a relevant location."""
    matches = []
    for job in postings:
        title = job.get("title", "").lower()
        location = job.get("locationsText", "").lower()

        title_ok = any(keyword in title for keyword in TITLE_KEYWORDS)
        location_ok = any(keyword in location for keyword in LOCATION_KEYWORDS)

        if title_ok and location_ok:
            matches.append({
                "source": f"Workday ({company_name})",
                "title": job.get("title"),
                "company": company_name,
                "location": job.get("locationsText"),
                "posted": job.get("postedOn"),
                # externalPath is relative - build the full clickable URL.
                "url": f"https://{company_name.lower()}.wd5.myworkdayjobs.com{job.get('externalPath', '')}",
            })

    return matches


def save_results(jobs: list[dict], path: str = "workday_jobs_found.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(jobs)} job(s) to {path}")


def main():
    all_matches = []

    for company_name, config in COMPANIES.items():
        print(f"Fetching from {company_name} (Workday)...")
        try:
            postings = fetch_workday_jobs(company_name, **config)
        except requests.exceptions.RequestException as e:
            print(f"  Failed to fetch {company_name}: {e}")
            continue

        print(f"  {len(postings)} total postings found")
        matches = filter_postings(company_name, postings)
        print(f"  {len(matches)} matched your keywords + location")
        all_matches.extend(matches)

    if not all_matches:
        print("\nNo matches. Try widening TITLE_KEYWORDS or LOCATION_KEYWORDS at the top of this file.")
        return

    print(f"\nTotal matches across all companies: {len(all_matches)}")
    for job in all_matches:
        print(f"  {job['title']} @ {job['company']} - {job['location']}")

    save_results(all_matches)


if __name__ == "__main__":
    main()
