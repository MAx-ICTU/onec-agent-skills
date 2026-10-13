#!/usr/bin/env python3
"""Проверка учебных моделей. НЕ интерпретатор BSL или языка запросов 1С."""

import json
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFACTOR = json.loads((ROOT / "examples/refactor/fixtures.json").read_text(encoding="utf-8"))
QUERIES = json.loads((ROOT / "examples/query-review/fixtures.json").read_text(encoding="utf-8"))


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount(case, *, round_base=True):
    base = Decimal(case["quantity"]) * Decimal(case["price"])
    if round_base:
        base = money(base)
    return money(base * (100 - Decimal(case["discount"])) / 100)


def slice_last(records, date, source, *, filter_first):
    """Только независимый регистр с единственным измерением item, без равных периодов."""
    latest = {}
    for row in records:
        if row["period"] > date or (filter_first and row["source"] != source):
            continue
        previous = latest.get(row["item"])
        if previous is None or previous["period"] < row["period"]:
            latest[row["item"]] = row
    return sorted([r["item"], r["price"]] for r in latest.values() if r["source"] == source)


def debug_trace(fail, *, fixed):
    """Модель ветвления и явных действий, не модель транзакций СУБД."""
    events = ["begin"]
    if fail:
        if fixed:
            events += ["rollback", "log", "raise"]
        else:
            events += ["log", "commit", "success"]
    else:
        events += ["step", "commit", "success"]
    return events


def fill_rows(rows, prices):
    mapping = dict(prices)
    return [[key, item, mapping.get(item, 0), item in mapping] for key, item in rows]


class ArithmeticExamples(unittest.TestCase):
    def test_documented_results(self):
        for case in REFACTOR["cases"]:
            with self.subTest(case=case):
                self.assertEqual(amount(case), Decimal(case["expected"]))

    def test_single_rounding_changes_business_result(self):
        case = REFACTOR["cases"][0]
        self.assertEqual(amount(case), Decimal("0.81"))
        self.assertEqual(amount(case, round_base=False), Decimal("0.80"))

    def test_repeated_rows_are_not_collapsed(self):
        case = REFACTOR["cases"][0]
        self.assertEqual([amount(c) for c in [case, case]], [Decimal("0.81")] * 2)
        self.assertEqual([amount(c) for c in []], [])


class ExceptionFlowExamples(unittest.TestCase):
    def test_success_path_unchanged(self):
        self.assertEqual(debug_trace(False, fixed=False), debug_trace(False, fixed=True))

    def test_swallowed_failure_continues(self):
        self.assertEqual(debug_trace(True, fixed=False), ["begin", "log", "commit", "success"])

    def test_fixed_failure_has_no_commit_or_success(self):
        events = debug_trace(True, fixed=True)
        self.assertEqual(events, ["begin", "rollback", "log", "raise"])
        self.assertNotIn("success", events)
        self.assertNotIn("commit", events)


class SliceExamples(unittest.TestCase):
    def setUp(self):
        self.data = QUERIES["slice_last"]

    def test_filter_placement_changes_result(self):
        data = self.data
        self.assertEqual(slice_last(data["records"], data["date"], data["source"], filter_first=False),
                         data["expected_original"])
        self.assertEqual(slice_last(data["records"], data["date"], data["source"], filter_first=True),
                         data["expected_proposed"])

    def test_period_boundary_and_no_records(self):
        rows = self.data["records"]
        self.assertEqual(slice_last(rows, "2025-12-31T23:59:59", "ручной", filter_first=False), [])
        self.assertEqual(slice_last(rows, "2026-01-01T00:00:00", "ручной", filter_first=False),
                         [["A", 10], ["B", 20]])
        self.assertEqual(slice_last(rows, "2026-01-02T00:00:00", "ручной", filter_first=False), [["B", 20]])


class RelationalExamples(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE sales (row_id INTEGER PRIMARY KEY, item TEXT, amount INTEGER);
            CREATE TABLE tags (item TEXT, tag TEXT, active INTEGER, PRIMARY KEY (item, tag));
            CREATE TABLE items (item TEXT PRIMARY KEY);
            CREATE TABLE permissions (item TEXT PRIMARY KEY, active INTEGER, comment TEXT);
        """)
        self.db.executemany("INSERT INTO sales VALUES (?, ?, ?)", QUERIES["joins"]["sales"])
        self.db.executemany("INSERT INTO tags VALUES (?, ?, ?)", QUERIES["joins"]["tags"])
        self.db.executemany("INSERT INTO items VALUES (?)", [(x,) for x in QUERIES["left_join"]["items"]])
        self.db.executemany("INSERT INTO permissions VALUES (?, ?, ?)", QUERIES["left_join"]["permissions"])

    def scalar(self, sql):
        return self.db.execute(sql).fetchone()[0]

    def rows(self, sql):
        return [list(row) for row in self.db.execute(sql)]

    def test_join_multiplication_and_membership_fix(self):
        self.assertEqual(self.scalar("SELECT SUM(s.amount) FROM sales s JOIN tags t ON s.item=t.item WHERE t.active=1"),
                         QUERIES["joins"]["expected_wrong_sum"])
        self.assertEqual(self.scalar("SELECT SUM(amount) FROM sales WHERE item IN (SELECT item FROM tags WHERE active=1)"),
                         QUERIES["joins"]["expected_sum"])

    def test_distinct_amount_is_wrong_fix(self):
        self.assertEqual(self.scalar("SELECT SUM(DISTINCT s.amount) FROM sales s JOIN tags t ON s.item=t.item WHERE t.active=1"), 100)
        self.assertNotEqual(100, QUERIES["joins"]["expected_sum"])

    def test_left_join_preserves_inactive_and_absent_rows(self):
        base = "SELECT i.item, p.comment FROM items i LEFT JOIN permissions p ON i.item=p.item"
        self.assertEqual(self.rows(base + " WHERE p.active=1 ORDER BY i.item"), QUERIES["left_join"]["expected_before"])
        self.assertEqual(self.rows(base + " AND p.active=1 ORDER BY i.item"), QUERIES["left_join"]["expected_after"])

    def test_or_null_is_not_equivalent_to_on_filter(self):
        result = self.rows("SELECT i.item FROM items i LEFT JOIN permissions p ON i.item=p.item WHERE p.active=1 OR p.item IS NULL ORDER BY i.item")
        self.assertEqual(result, [["A"], ["C"]])  # Неактивный B теряется.

    def test_correct_grouping_needs_no_repair(self):
        self.assertEqual(self.rows("SELECT item, SUM(amount) FROM sales GROUP BY item ORDER BY item"),
                         QUERIES["joins"]["expected_correct_grouping"])


class BatchExamples(unittest.TestCase):
    def test_rows_duplicates_missing_and_zero(self):
        data = QUERIES["batch"]
        result = fill_rows(data["rows"], data["prices"])
        self.assertEqual(result, data["expected"])
        self.assertEqual(Counter(r[1] for r in result), Counter(r[1] for r in data["rows"]))
        self.assertEqual([r[0] for r in result], [r[0] for r in data["rows"]])

    def test_empty_and_single_row(self):
        self.assertEqual(fill_rows([], [["A", 10]]), [])
        self.assertEqual(fill_rows([[1, "A"]], [["A", 10]]), [[1, "A", 10, True]])

    def test_deduplicating_input_loses_correspondence(self):
        data = QUERIES["batch"]
        unique = set(r[1] for r in data["rows"])
        self.assertLess(len(unique), len(data["rows"]))
        self.assertNotEqual(len(data["prices"]), len(data["expected"]))


if __name__ == "__main__":
    print("MODEL CHECKS ONLY: Decimal / SQLite / Python; 1C execution is NOT checked.", flush=True)
    unittest.main(verbosity=2)
