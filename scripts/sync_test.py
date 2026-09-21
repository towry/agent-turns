#!/usr/bin/env python3
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sync import apply_day, empty_week, merge_days, rebuild_month, rebuild_year, write_json


def day(date_s, turns, model="xai/grok-4.6"):
    return {
        "date": date_s,
        "turns": turns,
        "toolCallCount": turns * 2,
        "models": [{"id": model, "kind": "model", "turns": turns}] if turns else [],
    }


class MergeTest(unittest.TestCase):
    def test_overwrite_today(self):
        week = empty_week(date(2026, 9, 21), False)
        apply_day(week, {"date": "2026-09-21", "turns": 3, "toolCallCount": 8, "models": [{"id": "high", "kind": "mode", "turns": 3}]})
        apply_day(week, {"date": "2026-09-21", "turns": 18, "toolCallCount": 41, "models": [{"id": "xai/grok-4.6", "kind": "model", "turns": 11}, {"id": "high", "kind": "mode", "turns": 7}]})
        slot = week["days"][0]
        self.assertEqual(slot["turns"], 18)
        self.assertEqual(week["models"][0]["id"], "xai/grok-4.6")

    def test_rolls_week_and_writes_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            current = empty_week(date(2026, 9, 14), False)
            current["days"][0]["turns"] = 10
            (root / "data" / "current.json").write_text(json.dumps(current), encoding="utf-8")
            today = date(2026, 9, 21)
            merge_days(
                root,
                [
                    {"date": "2026-09-20", "turns": 12, "toolCallCount": 27, "models": []},
                    {"date": "2026-09-21", "turns": 18, "toolCallCount": 41, "models": [{"id": "high", "kind": "mode", "turns": 18}]},
                ],
                today,
            )
            archived = json.loads((root / "data" / "weeks" / "2026-W38.json").read_text())
            self.assertTrue(archived["complete"])
            self.assertEqual(archived["days"][6]["turns"], 12)
            now = json.loads((root / "data" / "current.json").read_text())
            self.assertEqual(now["id"], "2026-W39")
            self.assertFalse(now["complete"])
            self.assertEqual(now["days"][0]["turns"], 18)
            index = json.loads((root / "data" / "index.json").read_text())
            self.assertEqual(index["weeks"], ["2026-W38"])

    def test_month_split_on_week_that_crosses_august(self):
        """2026-W36 is Mon 08-31 .. Sun 09-06. August only gets 08-31."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            week = empty_week(date(2026, 8, 31), True)
            apply_day(week, day("2026-08-31", 10))
            apply_day(week, day("2026-09-01", 40))
            apply_day(week, day("2026-09-06", 7))
            write_json(root / "data" / "weeks" / "2026-W36.json", week)
            rebuild_month(root, 2026, 8)
            rebuild_month(root, 2026, 9)
            aug = json.loads((root / "data" / "months" / "2026-08.json").read_text())
            sep = json.loads((root / "data" / "months" / "2026-09.json").read_text())
            self.assertEqual(aug["bars"][0]["turns"], 10)
            self.assertEqual(sep["bars"][0]["turns"], 47)
            self.assertEqual(aug["models"][0]["turns"], 10)
            self.assertEqual(sep["models"][0]["turns"], 47)

    def test_year_split_on_iso_week_one(self):
        """2026-W01 is Mon 2025-12-29 .. Sun 2026-01-04."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            week = empty_week(date(2025, 12, 29), True)
            apply_day(week, day("2025-12-29", 5))
            apply_day(week, day("2025-12-31", 8))
            apply_day(week, day("2026-01-01", 20))
            apply_day(week, day("2026-01-04", 3))
            write_json(root / "data" / "weeks" / "2026-W01.json", week)
            rebuild_year(root, 2025)
            rebuild_year(root, 2026)
            dec = json.loads((root / "data" / "months" / "2025-12.json").read_text())
            jan = json.loads((root / "data" / "months" / "2026-01.json").read_text())
            y2025 = json.loads((root / "data" / "years" / "2025.json").read_text())
            y2026 = json.loads((root / "data" / "years" / "2026.json").read_text())
            self.assertEqual(dec["bars"][0]["turns"], 13)
            self.assertEqual(jan["bars"][0]["turns"], 23)
            self.assertEqual(y2025["bars"][0]["turns"], 13)
            self.assertEqual(y2026["bars"][0]["turns"], 23)

    def test_january_first_archives_previous_month_from_current_week(self):
        """On 2026-01-01, Dec days still sitting in current.json must land in 2025-12."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            current = empty_week(date(2025, 12, 29), False)
            apply_day(current, day("2025-12-29", 4))
            apply_day(current, day("2025-12-31", 6))
            write_json(root / "data" / "current.json", current)
            merge_days(
                root,
                [
                    day("2025-12-31", 6),
                    day("2026-01-01", 9),
                ],
                date(2026, 1, 1),
            )
            self.assertTrue((root / "data" / "months" / "2025-12.json").exists())
            self.assertTrue((root / "data" / "years" / "2025.json").exists())
            dec = json.loads((root / "data" / "months" / "2025-12.json").read_text())
            self.assertEqual(dec["bars"][0]["turns"], 10)
            now = json.loads((root / "data" / "current.json").read_text())
            self.assertEqual(now["id"], "2026-W01")
            self.assertEqual(now["days"][3]["date"], "2026-01-01")
            self.assertEqual(now["days"][3]["turns"], 9)


if __name__ == "__main__":
    unittest.main()
