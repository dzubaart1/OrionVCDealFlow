#!/usr/bin/env python3
"""
Daily ETL: GitHub ➜ Google Sheets
Finds early-stage AI-startup repos and overwrites one sheet tab.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from typing import List, Dict

import pandas as pd
import requests
from dateutil import tz
from sheets_writer import write_dataframe_to_sheet

GH_TOKEN = os.getenv("GH_TOKEN")
GS_CREDS_JSON = os.getenv("GS_CREDS_JSON")          # raw JSON string
GSHEET_ID = os.getenv("GSHEET_ID")                  # spreadsheet id
GSHEET_TAB = os.getenv("GSHEET_TAB", "AI-radar")    # tab (worksheet) name

if not all([GH_TOKEN, GS_CREDS_JSON, GSHEET_ID]):
    sys.exit("❌ Missing one or more required secrets")

HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

TOPICS = "topic:ai topic:machine-learning topic:deep-learning topic:generative-ai"
KEYWORDS = [
    '"pre-seed"', '"seed round"', "MVP", '"early stage"', '"YC W"',
]
MAX_STARS = 200
MAX_FORKS = 50
MAX_CONTRIB = 20
YEARS_BACK = 1
RESULT_TARGET = 30
SEARCH_PER_PAGE = 100           # maximum allowed

SINCE_DATE = (dt.datetime.utcnow() - dt.timedelta(days=365)).strftime("%Y-%m-%d")

def github_search(keyword: str) -> List[Dict]:
    """Return raw items from GitHub search for one keyword."""
    # Search qualifiers
    q = (
        f'{TOPICS} {keyword} in:readme,description '
        f'created:>={SINCE_DATE} '
        f'stars:<{MAX_STARS} forks:<{MAX_FORKS} '
        'fork:false archived:false'
    )
    url = "https://api.github.com/search/repositories"
    params = {
        "q": q,
        "sort": "stars",
        "order": "asc",
        "per_page": SEARCH_PER_PAGE,
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("items", [])

LINK_LAST_RE = re.compile(r'[&?]page=(\d+)>; rel="last"')

def contributors_count(repo: Dict) -> int:
    """Cheaply estimate contributor count using Link header pagination."""
    url = repo["contributors_url"]
    resp = requests.get(
        url, headers=HEADERS, params={"per_page": 1, "anon": "true"}, timeout=30
    )
    if resp.status_code != 200:
        return 0
    link = resp.headers.get("Link", "")
    match = LINK_LAST_RE.search(link)
    if match:
        return int(match.group(1))
    # No `last` page → 0 or 1 contributor
    return len(resp.json())

def calc_score(repo: Dict, age_days: int) -> int:
    """
    Relevance score:
        + younger repo  → higher
        + fewer stars   → higher
        + sponsors on   → bonus
    """
    score = (MAX_STARS - repo["stargazers_count"]) + (365 - age_days)
    if repo.get("has_sponsors"):
        score += 50
    return max(score, 0)

def collect_candidates() -> pd.DataFrame:
    """Search GitHub, filter, score, return DataFrame of best repos."""
    seen = {}
    for kw in KEYWORDS:
        try:
            items = github_search(kw)
        except requests.HTTPError as e:
            print(f"⚠️  GitHub search failed for {kw}: {e}")
            continue
        for repo in items:
            full_name = repo["full_name"]
            if full_name in seen:
                continue
            age_days = (dt.datetime.utcnow() - dt.datetime.strptime(
                repo["created_at"], "%Y-%m-%dT%H:%M:%SZ"
            )).days
            if age_days > 365:
                continue
            # contributors filter
            contribs = contributors_count(repo, )
            if contribs >= MAX_CONTRIB:
                continue
            score = calc_score(repo, age_days)
            seen[full_name] = {
                "name": full_name,
                "url": repo["html_url"],
                "created": repo["created_at"][:10],
                "stars": repo["stargazers_count"],
                "score": score,
                "description": repo["description"] or "",
            }
            # API courtesy sleep to stay within search + additional calls
            time.sleep(0.2)

    df = pd.DataFrame(seen.values())
    if df.empty:
        raise RuntimeError("No repositories found – loosen filters?")
    df.sort_values("score", ascending=False, inplace=True)
    return df.head(RESULT_TARGET)

def main() -> None:
    df = collect_candidates()
    write_dataframe_to_sheet(
        df,
        creds_json=json.loads(GS_CREDS_JSON),
        spreadsheet_id=GSHEET_ID,
        worksheet_name=GSHEET_TAB,
    )
    print(f"✅  Pushed {len(df)} rows to Google Sheets tab “{GSHEET_TAB}”")

if __name__ == "__main__":
    main()
