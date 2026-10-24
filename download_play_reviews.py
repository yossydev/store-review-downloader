#!/usr/bin/env python3
"""Download the past 6 months of public Google Play written reviews.

Play has no customer-reviews RSS. This uses the same public batchexecute
endpoint the Play Store website uses for the reviews list. Star-only ratings
are not included. Reviews are one global corpus, not a Japan-only feed.
Developer replies are included when the page returns them.

The app comes from PROJECT, APP_NAME, and ANDROID_PACKAGE. See .env.example.
"""

from __future__ import annotations

import calendar
import csv
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from project_env import load_project

PROJECT = load_project()
APP_ID = PROJECT.android_package
APP_NAME = PROJECT.name
LANG = "ja"
COUNTRY = "jp"
SORT_NEWEST = 2
PAGE_SIZE = 200
MONTHS = 6
MAX_PAGES = 40
OUTPUT_DIR = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))
USER_AGENT = "store-review-downloader/1.0"


def months_ago(moment: datetime, months: int) -> datetime:
    month_index = moment.month - months
    year = moment.year
    while month_index <= 0:
        month_index += 12
        year -= 1
    day = min(moment.day, calendar.monthrange(year, month_index)[1])
    return moment.replace(year=year, month=month_index, day=day)


def build_body(token: str | None) -> bytes:
    pagination: list = [PAGE_SIZE, None, token] if token else [PAGE_SIZE]
    filters = [None, None, None, None, None, None, None, None, None]
    inner = [None, [2, SORT_NEWEST, pagination, None, filters], [APP_ID, 7]]
    payload = [[["oCPfdb", json.dumps(inner, separators=(",", ":")), None, "generic"]]]
    raw = json.dumps(payload, separators=(",", ":")) + "\n"
    return ("f.req=" + urllib.parse.quote(raw)).encode()


def fetch_page(token: str | None) -> tuple[list, str | None]:
    url = (
        "https://play.google.com/_/PlayStoreUi/data/batchexecute"
        f"?hl={LANG}&gl={COUNTRY}"
    )
    request = urllib.request.Request(
        url,
        data=build_body(token),
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    text = raw.split("\n", 2)[-1] if raw.startswith(")]}'") else raw
    outer = json.loads(text)
    inner = json.loads(outer[0][2])
    reviews = inner[0] or []
    next_token = None
    try:
        candidate = inner[-2][-1]
    except (IndexError, TypeError):
        candidate = None
    if isinstance(candidate, str) and candidate:
        next_token = candidate
    return reviews, next_token


def text_at(item: list, index: int) -> str:
    if len(item) <= index or item[index] is None:
        return ""
    return str(item[index])


def reply_fields(item: list) -> tuple[str, str]:
    if len(item) <= 7 or not isinstance(item[7], list):
        return "", ""
    reply = item[7]
    body = reply[1] if len(reply) > 1 and isinstance(reply[1], str) else ""
    replied_at = ""
    if len(reply) > 2 and isinstance(reply[2], list) and reply[2] and isinstance(reply[2][0], int):
        replied_at = datetime.fromtimestamp(reply[2][0], JST).isoformat(timespec="seconds")
    return body, replied_at


def to_record(item: list) -> dict:
    moment = datetime.fromtimestamp(item[5][0], timezone.utc)
    reply_body, reply_at_jst = reply_fields(item)
    author = ""
    if isinstance(item[1], list) and item[1]:
        author = str(item[1][0] or "")
    thumbs = item[6] if len(item) > 6 and isinstance(item[6], int) else 0
    return {
        "review_id": item[0],
        "rating": int(item[2]),
        "title": "",
        "body": text_at(item, 4),
        "author": author,
        "version": text_at(item, 10),
        "updated_at": moment.isoformat(timespec="seconds"),
        "updated_at_jst": moment.astimezone(JST).isoformat(timespec="seconds"),
        "thumbs_up": thumbs,
        "reply_body": reply_body,
        "reply_at_jst": reply_at_jst,
    }


def download(cutoff: datetime) -> list[dict]:
    by_id: dict[str, dict] = {}
    token: str | None = None
    for page in range(1, MAX_PAGES + 1):
        reviews, token = fetch_page(token)
        print(f"page {page}: {len(reviews)}")
        if not reviews:
            break
        in_window = 0
        oldest = None
        for item in reviews:
            record = to_record(item)
            updated = datetime.fromisoformat(record["updated_at"])
            oldest = updated
            if updated < cutoff:
                continue
            by_id[record["review_id"]] = record
            in_window += 1
        print(f"  kept {in_window}")
        if oldest is not None and oldest < cutoff:
            break
        if not token:
            break
        time.sleep(0.3)
    records = list(by_id.values())
    records.sort(key=lambda record: record["updated_at"], reverse=True)
    return records


def write_outputs(records: list[dict], cutoff: datetime) -> tuple[Path, Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"{PROJECT.slug}-android-reviews-past-6-months.csv"
    json_path = OUTPUT_DIR / f"{PROJECT.slug}-android-reviews-past-6-months.json"
    summary_path = OUTPUT_DIR / "summary-play.json"

    fieldnames = [
        "review_id",
        "rating",
        "title",
        "body",
        "author",
        "version",
        "updated_at",
        "updated_at_jst",
        "thumbs_up",
        "reply_body",
        "reply_at_jst",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    by_rating = Counter(record["rating"] for record in records)
    by_month = Counter(record["updated_at_jst"][:7] for record in records)
    reply_count = sum(1 for record in records if record["reply_body"])
    summary = {
        "app_id": APP_ID,
        "app_name": APP_NAME,
        "country": COUNTRY,
        "lang": LANG,
        "source": "google play public reviews",
        "app_url": f"https://play.google.com/store/apps/details?id={APP_ID}&hl={LANG}&gl={COUNTRY}",
        "window_months": MONTHS,
        "cutoff_jst": cutoff.astimezone(JST).isoformat(timespec="seconds"),
        "review_count": len(records),
        "reply_count": reply_count,
        "newest": records[0]["updated_at_jst"] if records else None,
        "oldest": records[-1]["updated_at_jst"] if records else None,
        "by_rating": {str(star): by_rating.get(star, 0) for star in range(1, 6)},
        "by_month": dict(sorted(by_month.items())),
        "average_rating": round(
            sum(record["rating"] for record in records) / len(records), 3
        )
        if records
        else None,
        "notes": [
            "Written reviews only. Star-only ratings are not in this feed.",
            "Play reviews are global. gl=jp selects the storefront, not the reviewer country.",
            "Play reviews have no title. The title column is empty.",
        ],
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return csv_path, json_path, summary_path


def main() -> None:
    cutoff = months_ago(datetime.now(JST), MONTHS)
    print(f"{APP_NAME} [{PROJECT.slug}] android {APP_ID}")
    print(f"cutoff {cutoff.isoformat(timespec='seconds')}")
    records = download(cutoff)
    csv_path, json_path, summary_path = write_outputs(records, cutoff)
    print(f"wrote {len(records)} reviews")
    print(csv_path)
    print(json_path)
    print(summary_path)


if __name__ == "__main__":
    main()
