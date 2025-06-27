#!/usr/bin/env python3
"""
Daily ETL: GitHub ➜ Google Sheets
Ищет проекты по новым критериям и перезаписывает вкладку в Google Sheets.
"""
from future import annotations

import datetime as dt
import json
import os
import sys
import time
from typing import Dict, List, Tuple

import pandas as pd
import requests

from sheets_writer import write_dataframe_to_sheet

GH_TOKEN = os.getenv("GH_TOKEN")
GS_CREDS_JSON = os.getenv("GS_CREDS_JSON")
GSHEET_ID = os.getenv("GSHEET_ID")
GSHEET_TAB = os.getenv("GSHEET_TAB", "AI-radar")

if not all([GH_TOKEN, GS_CREDS_JSON, GSHEET_ID]):
sys.exit("❌ Отсутствуют обязательные секреты (GH_TOKEN / GS_CREDS_JSON / GSHEET_ID)")

HEADERS = {
"Authorization": f"token {GH_TOKEN}",
"Accept": "application/vnd.github+json",
"X-GitHub-Api-Version": "2022-11-28",
}

SEARCH_PER_PAGE = 100
RESULT_TARGET = 30
WINDOW_DAYS = 30
STAR_GROWTH_THRESHOLD = 20
CORE_CONTRIB_MIN = 2
TOP1_SHARE_MAX = 0.7
LICENSES = {"MIT", "Apache-2.0"}

def github_search(page: int) -> List[Dict]:
since = (dt.datetime.utcnow() - dt.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
q = f"pushed:>={since}"
url = "https://api.github.com/search/repositories"
params = {
"q": q,
"sort": "stars",
"order": "desc",
"per_page": SEARCH_PER_PAGE,
"page": page,
}
resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
resp.raise_for_status()
return resp.json().get("items", [])

def last_commit_within(repo: Dict) -> bool:
commits_url = repo["commits_url"].split("{")[0]
resp = requests.get(
commits_url, headers=HEADERS, params={"per_page": 1}, timeout=30
)
if resp.status_code != 200:
return False
date_str = resp.json()[0]["commit"]["committer"]["date"]
commit_dt = dt.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
return (dt.datetime.utcnow() - commit_dt).days <= WINDOW_DAYS

def get_star_growth(repo: Dict) -> int:
url = repo["stargazers_url"]
headers = HEADERS.copy()
headers["Accept"] = "application/vnd.github.v3.star+json"
count = 0
page = 1
cutoff = dt.datetime.utcnow() - dt.timedelta(days=WINDOW_DAYS)
while True:
resp = requests.get(
url, headers=headers, params={"per_page": 100, "page": page}, timeout=30
)
if resp.status_code != 200:
break
stars = resp.json()
if not stars:
break
for entry in stars:
dt_star = dt.datetime.strptime(
entry.get("starred_at", ""), "%Y-%m-%dT%H:%M:%SZ"
)
if dt_star < cutoff:
return count
count += 1
page += 1
time.sleep(0.2)
return count

def get_contributor_stats(repo: Dict) -> Tuple[int, float]:
resp = requests.get(
repo["contributors_url"],
headers=HEADERS,
params={"per_page": 100, "anon": "true"},
timeout=30,
)
if resp.status_code != 200:
return 0, 0.0
contribs = resp.json()
total = sum(c.get("contributions", 0) for c in contribs)
if total == 0:
return 0, 0.0
top = max(c.get("contributions", 0) for c in contribs)
return len(contribs), top / total

def license_valid(repo: Dict) -> bool:
lic = repo.get("license")
return bool(lic and lic.get("spdx_id") in LICENSES)

def dependabot_valid(repo: Dict) -> bool:
# TODO: implement via GraphQL or REST call to ensure critical Dependabot alerts = 0
return True

def collect_candidates() -> pd.DataFrame:
seen: Dict[str, Dict] = {}
page = 1
while len(seen) < RESULT_TARGET:
try:
items = github_search(page)
except requests.HTTPError:
break
if not items:
break
for repo in items:
name = repo["full_name"]
if name in seen:
continue
if not last_commit_within(repo):
continue
if get_star_growth(repo) < STAR_GROWTH_THRESHOLD:
continue
contrib_count, top_share = get_contributor_stats(repo)
if contrib_count < CORE_CONTRIB_MIN or top_share > TOP1_SHARE_MAX:
continue
if not license_valid(repo):
continue
if not dependabot_valid(repo):
continue
seen[name] = {
"name": name,
"url": repo["html_url"],
"last_commit": repo["updated_at"][:10],
"stars": repo["stargazers_count"],
"license": repo.get("license", {}).get("spdx_id", ""),
"contributors": contrib_count,
}
if len(seen) >= RESULT_TARGET:
break
time.sleep(0.2)
page += 1

kotlin
Копировать
Редактировать
return pd.DataFrame(seen.values())
def main() -> None:
df = collect_candidates()
if df.empty:
print("⚠️ Warning: no repositories found")
write_dataframe_to_sheet(
df,
creds_json=json.loads(GS_CREDS_JSON),
spreadsheet_id=GSHEET_ID,
worksheet_name=GSHEET_TAB,
)
print(f"✅ Pushed {len(df)} rows to Google Sheets tab “{GSHEET_TAB}”")

if name == "main":
main()
