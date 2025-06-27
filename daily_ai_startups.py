#!/usr/bin/env python3
"""
Daily ETL: GitHub ➜ Google Sheets
Ищет ранние AI-стартапы (pre-seed / seed) и перезаписывает вкладку в Google Sheets.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from typing import Dict, List

import pandas as pd
import requests
from dateutil import tz

from sheets_writer import write_dataframe_to_sheet

# ------------------------------ конфигурация ------------------------------ #

GH_TOKEN = os.getenv("GH_TOKEN")
GS_CREDS_JSON = os.getenv("GS_CREDS_JSON")          # JSON-строка service-account
GSHEET_ID = os.getenv("GSHEET_ID")                  # ID таблицы
GSHEET_TAB = os.getenv("GSHEET_TAB", "AI-radar")    # имя вкладки

if not all([GH_TOKEN, GS_CREDS_JSON, GSHEET_ID]):
    sys.exit("❌ Отсутствуют обязательные секреты (GH_TOKEN / GS_CREDS_JSON / GSHEET_ID)")

HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

TOPICS = ["ai", "machine-learning", "deep-learning", "generative-ai"]
KEYWORDS = [
    '"pre-seed"',
    '"seed round"',
    "MVP",
    '"early stage"',
    '"YC W"',
]

MAX_STARS = 200
MAX_FORKS = 50
MAX_CONTRIB = 20
RESULT_TARGET = 30
SEARCH_PER_PAGE = 100  # максимум, который даёт GitHub

SINCE_DATE = (dt.datetime.utcnow() - dt.timedelta(days=365)).strftime("%Y-%m-%d")

# ------------------------------ helpers ------------------------------ #

def github_search(topic: str, keyword: str) -> List[Dict]:
    """
    Один поисковый запрос в GitHub API.
    Используем ИЛИ-логику по topic'ам — каждый запрос ограничивается одним topic и одним keyword.
    """
    q = (
        f"topic:{topic} {keyword} in:readme,description "
        f"created:>={SINCE_DATE} "
        f"stars:<{MAX_STARS} forks:<{MAX_FORKS} "
        "fork:false archived:false"
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


# Быстрый способ узнать количество контрибьюторов: берём первую страницу
# и смотрим Link-заголовок (`…page=N>; rel="last"`).
LINK_LAST_RE = re.compile(r'[&?]page=(\d+)>; rel="last"')

def contributors_count(repo: Dict) -> int:
    url = repo["contributors_url"]
    resp = requests.get(
        url,
        headers=HEADERS,
        params={"per_page": 1, "anon": "true"},
        timeout=30,
    )
    if resp.status_code != 200:
        return 0
    link = resp.headers.get("Link", "")
    match = LINK_LAST_RE.search(link)
    if match:
        return int(match.group(1))
    # если Link нет – значит 0 или 1 контрибьютор; считаем по факту
    return len(resp.json())


def calc_score(repo: Dict, age_days: int) -> int:
    """
    Relevance-score: чем моложе и «менее звёздный» репо, тем выше.
    Если включены GitHub Sponsors — получаем бонус.
    """
    score = (MAX_STARS - repo["stargazers_count"]) + (365 - age_days)
    if repo.get("has_sponsors"):
        score += 50
    return max(score, 0)


# ------------------------------ основной ETL ------------------------------ #

def collect_candidates() -> pd.DataFrame:
    """
    Перебираем все комбинации topic × keyword, фильтруем,
    считаем score и возвращаем TOP N как DataFrame.
    """
    seen: Dict[str, Dict] = {}

    for topic in TOPICS:
        for kw in KEYWORDS:
            try:
                items = github_search(topic, kw)
            except requests.HTTPError as e:
                print(f"⚠️  GitHub search failed [{topic} / {kw}]: {e}")
                continue

            for repo in items:
                full_name = repo["full_name"]
                if full_name in seen:
                    continue

                # возраст
                created_dt = dt.datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ")
                age_days = (dt.datetime.utcnow() - created_dt).days
                if age_days > 365:
                    continue

                # контрибьюторы
                contribs = contributors_count(repo)
                if contribs >= MAX_CONTRIB:
                    continue

                # окончательно добавляем
                score = calc_score(repo, age_days)
                seen[full_name] = {
                    "name": full_name,
                    "url": repo["html_url"],
                    "created": repo["created_at"][:10],
                    "stars": repo["stargazers_count"],
                    "score": score,
                    "description": repo["description"] or "",
                }

                # courtesy-sleep, чтобы не упереться в rate-limit на доп-запросы
                time.sleep(0.2)

    df = pd.DataFrame(seen.values()).sort_values("score", ascending=False)
    return df.head(RESULT_TARGET)  # если строк < 30 – отдаём, что нашли


def main() -> None:
    df = collect_candidates()
    if df.empty:
        print("⚠️  Warning: no repositories found — возможно, фильтры слишком жёсткие.")
    write_dataframe_to_sheet(
        df,
        creds_json=json.loads(GS_CREDS_JSON),
        spreadsheet_id=GSHEET_ID,
        worksheet_name=GSHEET_TAB,
    )
    print(f"✅  Pushed {len(df)} rows to Google Sheets tab “{GSHEET_TAB}”")


if __name__ == "__main__":
    main()
