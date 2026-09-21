#!/usr/bin/env python3
"""Fetch yesterday+today turn summaries and merge into data/*.json."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

SH = ZoneInfo("Asia/Shanghai")
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BUILTIN = {"low", "medium", "high", "ultra", "smart", "deep", "rush"}


def today_sh(now: datetime | None = None) -> date:
    return (now or datetime.now(SH)).date()


def iso_week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def empty_week(d: date, complete: bool) -> dict[str, Any]:
    monday, sunday = week_bounds(d)
    days = []
    for i in range(7):
        day = monday + timedelta(days=i)
        days.append(
            {
                "date": day.isoformat(),
                "weekday": WEEKDAYS[i],
                "turns": 0,
                "toolCallCount": 0,
                "models": [],
            }
        )
    return {
        "kind": "week",
        "id": iso_week_id(d),
        "label": "This week" if not complete else (lambda y,w,_: f"Week {w}, {y}")(*d.isocalendar()),
        "start": monday.isoformat(),
        "end": sunday.isoformat(),
        "complete": complete,
        "days": days,
        "models": [],
    }


def model_kind(name: str) -> str:
    return "mode" if name in BUILTIN else "model"


def day_from_api(payload: dict[str, Any]) -> dict[str, Any]:
    models = []
    for row in payload.get("models") or []:
        name = str(row.get("model") or "").strip()
        if not name:
            continue
        models.append(
            {
                "id": name,
                "kind": model_kind(name),
                "turns": int(row.get("turns") or 0),
            }
        )
    models.sort(key=lambda m: (-m["turns"], m["id"]))
    return {
        "date": payload["day"],
        "turns": int(payload.get("turns") or 0),
        "toolCallCount": int(payload.get("tool_calls") or 0),
        "models": models,
    }


def apply_day(week: dict[str, Any], day: dict[str, Any]) -> None:
    for slot in week["days"]:
        if slot["date"] == day["date"]:
            slot["turns"] = day["turns"]
            slot["toolCallCount"] = day["toolCallCount"]
            slot["models"] = day["models"]
            break
    rollup_models(week)


def rollup_models(week: dict[str, Any]) -> None:
    totals: dict[str, dict[str, Any]] = {}
    for slot in week["days"]:
        for m in slot.get("models") or []:
            item = totals.setdefault(
                m["id"], {"id": m["id"], "kind": m.get("kind") or model_kind(m["id"]), "turns": 0}
            )
            item["turns"] += int(m.get("turns") or 0)
    week["models"] = sorted(totals.values(), key=lambda m: (-m["turns"], m["id"]))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def flyagent_get(base: str, token: str, day: date) -> dict[str, Any]:
    url = base.rstrip("/") + "/v1/metrics/turns/days/" + day.isoformat()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "agent-turns-sync",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(f"GET {url} failed: HTTP {err.code} {body}") from err


def week_path(root: Path, week_id: str) -> Path:
    return root / "data" / "weeks" / f"{week_id}.json"


def load_or_empty_week(root: Path, d: date, complete: bool) -> dict[str, Any]:
    path = week_path(root, iso_week_id(d))
    if path.exists():
        return load_json(path)
    return empty_week(d, complete)


def archive_current_if_stale(root: Path, current: dict[str, Any], today: date) -> dict[str, Any]:
    if current.get("id") == iso_week_id(today):
        current["complete"] = False
        current["label"] = "This week"
        return current
    current["complete"] = True
    y, w, _ = date.fromisoformat(current["start"]).isocalendar()
    current["label"] = f"Week {w}, {y}"
    write_json(week_path(root, current["id"]), current)
    return empty_week(today, False)


def rebuild_index(root: Path) -> dict[str, Any]:
    weeks = sorted((p.stem for p in (root / "data" / "weeks").glob("*.json")), reverse=True)
    months = sorted((p.stem for p in (root / "data" / "months").glob("*.json")), reverse=True)
    years = sorted((p.stem for p in (root / "data" / "years").glob("*.json")), reverse=True)
    index = {"current": "current.json", "weeks": weeks, "months": months, "years": years}
    write_json(root / "data" / "index.json", index)
    return index


def iter_week_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    paths = list((root / "data" / "weeks").glob("*.json"))
    current = root / "data" / "current.json"
    if current.exists():
        paths.append(current)
    for path in paths:
        week = load_json(path)
        week_id = str(week.get("id") or path.stem)
        if week_id in seen:
            continue
        seen.add(week_id)
        docs.append(week)
    return docs


def days_in_month(week: dict[str, Any], year: int, month: int) -> list[dict[str, Any]]:
    out = []
    for slot in week.get("days") or []:
        d = date.fromisoformat(slot["date"])
        if d.year == year and d.month == month:
            out.append(slot)
    return out


def add_models(totals: dict[str, dict[str, Any]], slots: list[dict[str, Any]]) -> None:
    for slot in slots:
        for m in slot.get("models") or []:
            item = totals.setdefault(
                m["id"], {"id": m["id"], "kind": m.get("kind") or model_kind(m["id"]), "turns": 0}
            )
            item["turns"] += int(m.get("turns") or 0)


def rebuild_month(root: Path, year: int, month: int) -> None:
    bars = []
    models: dict[str, dict[str, Any]] = {}
    for week in sorted(iter_week_docs(root), key=lambda w: w.get("start") or ""):
        slots = days_in_month(week, year, month)
        if not slots:
            continue
        turns = sum(int(d["turns"]) for d in slots)
        bars.append(
            {
                "id": week["id"],
                "label": str(week["id"]).split("-")[-1],
                "turns": turns,
                "href": f"?week={week['id']}",
            }
        )
        add_models(models, slots)
    if not bars:
        return
    write_json(
        root / "data" / "months" / f"{year}-{month:02d}.json",
        {
            "kind": "month",
            "id": f"{year}-{month:02d}",
            "label": f"{year}-{month:02d}",
            "complete": True,
            "bars": bars,
            "models": sorted(models.values(), key=lambda m: (-m["turns"], m["id"])),
        },
    )


def rebuild_year(root: Path, year: int) -> None:
    for month in range(1, 13):
        rebuild_month(root, year, month)
    bars = []
    models: dict[str, dict[str, Any]] = {}
    for month in range(1, 13):
        path = root / "data" / "months" / f"{year}-{month:02d}.json"
        if not path.exists():
            continue
        doc = load_json(path)
        turns = sum(int(b["turns"]) for b in doc.get("bars") or [])
        bars.append({"id": doc["id"], "label": f"{year}-{month:02d}", "turns": turns, "href": f"?month={doc['id']}"})
        for m in doc.get("models") or []:
            item = models.setdefault(m["id"], {"id": m["id"], "kind": m.get("kind") or model_kind(m["id"]), "turns": 0})
            item["turns"] += int(m.get("turns") or 0)
    if not bars:
        return
    write_json(
        root / "data" / "years" / f"{year}.json",
        {
            "kind": "year",
            "id": str(year),
            "label": str(year),
            "complete": True,
            "bars": bars,
            "models": sorted(models.values(), key=lambda m: (-m["turns"], m["id"])),
        },
    )


def roll_completed(root: Path, today: date) -> None:
    prev_month_last = today.replace(day=1) - timedelta(days=1)
    rebuild_month(root, prev_month_last.year, prev_month_last.month)
    if today.year > prev_month_last.year:
        rebuild_year(root, prev_month_last.year)


def merge_days(root: Path, days: list[dict[str, Any]], today: date) -> None:
    current_path = root / "data" / "current.json"
    current = load_json(current_path) if current_path.exists() else empty_week(today, False)
    current = archive_current_if_stale(root, current, today)
    for day in days:
        d = date.fromisoformat(day["date"])
        if iso_week_id(d) == current["id"]:
            apply_day(current, day)
            continue
        complete = week_bounds(d)[1] < today
        week = load_or_empty_week(root, d, complete)
        apply_day(week, day)
        week["complete"] = complete
        if complete:
            y, w, _ = d.isocalendar()
            week["label"] = f"Week {w}, {y}"
        write_json(week_path(root, week["id"]), week)
    write_json(current_path, current)
    roll_completed(root, today)
    rebuild_index(root)


def sync(root: Path, base: str, token: str, now: datetime | None = None) -> None:
    today = today_sh(now)
    yesterday = today - timedelta(days=1)
    fetched = []
    for d in (yesterday, today):
        fetched.append(day_from_api(flyagent_get(base, token, d)))
    merge_days(root, fetched, today)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    base = (os.environ.get("FLYAGENT_URL") or "").strip()
    token = (os.environ.get("FLYAGENT_TOKEN") or os.environ.get("FLYAGENT_API_KEY") or "").strip()
    if not base or not token:
        raise SystemExit("FLYAGENT_URL and FLYAGENT_TOKEN (or FLYAGENT_API_KEY) are required")
    if "://" not in base:
        base = "https://" + base
    sync(root, base, token)


if __name__ == "__main__":
    main()
