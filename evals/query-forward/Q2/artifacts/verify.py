"""Finite relational model only; does not parse or execute the 1C queries.

All sales belong to the selected document, as specified in the input contract.
Totals below are mathematical totals (empty sum = 0), not claims about 1C NULL.
"""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "input" / "data.json"


def amount(value):
    return Decimal(str(value))


def total(rows):
    return sum((amount(row[2]) for row in rows), Decimal(0))


def contract_rows(sales, tags):
    # Direct reading of "at least one active tag" for each original sales row.
    return [row for row in sales
            if any(tag[0] == row[1] and tag[2] == 1 for tag in tags)]


def membership_rows(sales, tags):
    # Model of the proposed IN predicate: multiplicity inside IN has no effect.
    active_products = {tag[0] for tag in tags if tag[2] == 1}
    return [row for row in sales if row[1] in active_products]


def original_rows(sales, tags):
    # Model of the original inner join followed by the active-tag predicate.
    return [row for row in sales for tag in tags
            if row[1] == tag[0] and tag[2] == 1]


def check_case(name, sales, tags, expected_ids, expected_total):
    assert len({row[0] for row in sales}) == len(sales), name
    assert len({(tag[0], tag[1]) for tag in tags}) == len(tags), name
    expected = contract_rows(sales, tags)
    actual = membership_rows(sales, tags)
    assert Counter(tuple(row) for row in expected) == Counter(tuple(row) for row in actual), name
    assert Counter(row[0] for row in actual) == Counter(expected_ids), name
    assert total(actual) == amount(expected_total), name
    print(json.dumps({"case": name, "status": "PASS",
                      "qualifying_row_ids": [row[0] for row in actual],
                      "mathematical_total": str(total(actual))}, ensure_ascii=True))


with INPUT.open(encoding="utf-8-sig") as handle:
    fixture = json.load(handle)
sales, tags = fixture["sales"], fixture["tags"]
check_case("provided_fixture", sales, tags, [1, 2], 200)
joined = original_rows(sales, tags)
assert Counter(row[0] for row in joined) == Counter({1: 2, 2: 2})
assert total(joined) == Decimal(400)
wrong_distinct_amount = sum({amount(row[2]) for row in joined}, Decimal(0))
wrong_distinct_projection = sum(
    (value for _, value in {(row[1], amount(row[2])) for row in joined}), Decimal(0))
assert wrong_distinct_amount == Decimal(100)
assert wrong_distinct_projection == Decimal(100)
print(json.dumps({"fixture_original_join_row_ids": [row[0] for row in joined],
                  "fixture_original_total": str(total(joined)),
                  "wrong_distinct_amount_total": str(wrong_distinct_amount),
                  "wrong_distinct_product_amount_total": str(wrong_distinct_projection)}))

cases = [
    ("no_sales", [], [["A", "T1", 1]], [], 0),
    ("no_tags", [[1, "A", 100]], [], [], 0),
    ("inactive_only", [[1, "A", 100]], [["A", "T1", 0]], [], 0),
    ("one_active", [[1, "A", 100]], [["A", "T1", 1]], [1], 100),
    ("multiple_active", [[1, "A", 100]], [["A", "T1", 1], ["A", "T2", 1]], [1], 100),
    ("mixed_active_inactive", [[1, "A", 100]], [["A", "T1", 0], ["A", "T2", 1]], [1], 100),
    ("real_equal_repeats", [[1, "A", 100], [2, "A", 100]], [["A", "T1", 1]], [1, 2], 200),
    ("equal_amount_different_products", [[1, "A", 100], [2, "B", 100]],
     [["A", "T1", 1], ["B", "T2", 1]], [1, 2], 200),
    ("absent_inactive_active", [[1, "A", 100], [2, "B", 50], [3, "C", 25]],
     [["A", "T1", 1], ["A", "T2", 1], ["B", "T3", 0]], [1], 100),
    ("decimal_zero_negative", [[1, "A", "100.10"], [2, "A", "-0.10"], [3, "A", 0]],
     [["A", "T1", 1], ["A", "T2", 1]], [1, 2, 3], 100),
]
for args in cases:
    check_case(*args)
print("PASS: 11 cases; row multisets, source row IDs and mathematical totals checked.")
print("NOT RUN: 1C parsing, execution, empty-set aggregate semantics, query plans or timings.")
