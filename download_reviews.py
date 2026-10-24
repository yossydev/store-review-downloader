#!/usr/bin/env python3
"""Download the past 6 months of public App Store written reviews.

Apple's customer-reviews RSS returns at most 10 pages of 50 reviews for each
sort. Star-only ratings and developer replies are not in this feed. The full
history, including replies, needs the App Store Connect API.

The app comes from PROJECT, APP_NAME, and IOS_APP_ID. See .env.example.
"""

from __future__ import annotations

import calendar
import csv
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from project_env import load_project

PROJECT = load_project()
APP_ID = PROJECT.ios_app_id
APP_NAME = PROJECT.name
COUNTRY = "jp"
SORTS = ("mostrecent", "mosthelpful")
MAX_PAGE = 10
MONTHS = 6
OUTPUT_DIR = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
USER_AGENT = "store-review-downloader/1.0"


def fetch_page(sort: str, page: int) -> list[dict]:
    url = (
        "https://itunes.apple.com/"
        f"{COUNTRY}/rss/customerreviews/page={page}/id={APP_ID}/sortby={sort}/json"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 400:
            return []
        raise

    entries = payload.get("feed", {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    return [entry for entry in entries if "im:rating" in entry]


def label(entry: dict, key: str) -> str:
    value = entry.get(key, {})
    if isinstance(value, dict):
        return str(value.get("label", ""))
    return ""


def months_ago(moment: datetime, months: int) -> datetime:
    month_index = moment.month - months
    year = moment.year
    while month_index <= 0:
        month_index += 12
        year -= 1
    day = min(moment.day, calendar.monthrange(year, month_index)[1])
    return moment.replace(year=year, month=month_index, day=day)


def to_record(entry: dict, sort: str) -> dict:
    updated_raw = label(entry, "updated")
    updated = datetime.fromisoformat(updated_raw)
    return {
        "review_id": label(entry, "id"),
        "rating": int(label(entry, "im:rating")),
        "title": label(entry, "title"),
        "body": label(entry, "content"),
        "author": entry.get("author", {}).get("name", {}).get("label", ""),
        "version": label(entry, "im:version"),
        "updated_at": updated_raw,
        "updated_at_jst": updated.astimezone(JST).isoformat(timespec="seconds"),
        "vote_sum": int(label(entry, "im:voteSum") or "0"),
        "vote_count": int(label(entry, "im:voteCount") or "0"),
        "sort_seen": sort,
    }


def remember(by_id: dict[str, dict], record: dict, sort: str) -> None:
    existing = by_id.get(record["review_id"])
    if existing is None:
        by_id[record["review_id"]] = record
        return
    if sort not in existing["sort_seen"].split(","):
        existing["sort_seen"] += f",{sort}"


def download(cutoff: datetime) -> list[dict]:
    by_id: dict[str, dict] = {}
    for sort in SORTS:
        for page in range(1, MAX_PAGE + 1):
            entries = fetch_page(sort, page)
            print(f"{sort} page {page}: {len(entries)}")
            if not entries:
                break
            in_window = 0
            for entry in entries:
                record = to_record(entry, sort)
                updated = datetime.fromisoformat(record["updated_at"])
                if updated < cutoff:
                    continue
                remember(by_id, record, sort)
                in_window += 1
            print(f"  kept {in_window}")
            # mostrecent is newest-first, so the rest of the feed is older.
            if sort == "mostrecent" and in_window < len(entries):
                break
            time.sleep(0.2)
    records = list(by_id.values())
    records.sort(key=lambda record: record["updated_at"], reverse=True)
    return records


def write_outputs(records: list[dict], cutoff: datetime) -> tuple[Path, Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"{PROJECT.slug}-ios-reviews-past-6-months.csv"
    json_path = OUTPUT_DIR / f"{PROJECT.slug}-ios-reviews-past-6-months.json"
    summary_path = OUTPUT_DIR / "summary.json"

    fieldnames = [
        "review_id",
        "rating",
        "title",
        "body",
        "author",
        "version",
        "updated_at",
        "updated_at_jst",
        "vote_sum",
        "vote_count",
        "sort_seen",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    by_rating = Counter(record["rating"] for record in records)
    by_year = Counter(record["updated_at_jst"][:4] for record in records)
    by_month = Counter(record["updated_at_jst"][:7] for record in records)
    summary = {
        "app_id": APP_ID,
        "app_name": APP_NAME,
        "country": COUNTRY,
        "source": "itunes customer reviews RSS",
        "app_url": f"https://apps.apple.com/{COUNTRY}/app/id{APP_ID}?see-all=reviews",
        "window_months": MONTHS,
        "cutoff_jst": cutoff.isoformat(timespec="seconds"),
        "review_count": len(records),
        "newest": records[0]["updated_at_jst"] if records else None,
        "oldest": records[-1]["updated_at_jst"] if records else None,
        "by_rating": {str(star): by_rating.get(star, 0) for star in range(1, 6)},
        "by_year": dict(sorted(by_year.items())),
        "by_month": dict(sorted(by_month.items())),
        "average_rating": round(
            sum(record["rating"] for record in records) / len(records), 3
        )
        if records
        else None,
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return csv_path, json_path, summary_path


def main() -> None:
    cutoff = months_ago(datetime.now(JST), MONTHS)
    print(f"{APP_NAME} [{PROJECT.slug}] ios {APP_ID}")
    print(f"cutoff {cutoff.isoformat(timespec='seconds')}")
    records = download(cutoff)
    csv_path, json_path, summary_path = write_outputs(records, cutoff)
    print(f"wrote {len(records)} reviews")
    print(csv_path)
    print(json_path)
    print(summary_path)


if __name__ == "__main__":
    main()
