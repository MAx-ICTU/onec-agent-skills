"""Executable standard-library model, not a BSL/1C execution."""
import json
import random
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent
INPUT = BASE.parent / "input"

def before(rows, prices):
    result = []
    for identity, product, stale_price, stale_found in rows:
        matches = [price for key, price in prices if key == product]
        assert len(matches) <= 1
        found = bool(matches)
        result.append((identity, product, matches[0] if found else Decimal(0), found))
    return result, len(rows)

def proposed(rows, prices):
    if not rows:
        return [], 0
    joined = []
    for identity, product, stale_price, stale_found in rows:
        matches = [price for key, price in prices if key == product]
        assert len(matches) <= 1
        joined.append((identity, matches[0] if matches else Decimal(0), bool(matches)))
    # Query output order is deliberately unrelated to source order.
    by_identity = {identity: (price, found) for identity, price, found in reversed(joined)}
    assert len(by_identity) == len(rows)
    return [(identity, product, *by_identity[identity])
            for identity, product, stale_price, stale_found in rows], 1

def check(name, rows, prices):
    old_result, old_calls = before(rows, prices)
    new_result, new_calls = proposed(rows, prices)
    assert new_result == old_result, (name, old_result, new_result)
    assert [r[0] for r in new_result] == [r[0] for r in rows]
    assert old_calls == len(rows)
    assert new_calls == (1 if rows else 0)
    return new_result, old_calls, new_calls

data = json.loads((INPUT / "data.json").read_text(encoding="utf-8-sig"), parse_float=Decimal)
rows = [(identity, product, Decimal("999.99"), True) for identity, product in data["rows"]]
prices = [(product, Decimal(str(price))) for product, price in data["prices"]]
result, old_calls, new_calls = check("provided", rows, prices)
print("MODEL ONLY: Python exact string equality; no 1C, query compilation, DB plan or timings.")
print("provided result (id, product, price, found):")
for identity, product, price, found in result:
    print(f"{identity}, {product}, {price:.2f}, {found}")
print(f"modeled Execute calls: before={old_calls}, proposed={new_calls}")

cases = [
    ("empty", [], prices),
    ("one found resets false", [(7, "A", Decimal("333"), False)], prices),
    ("one absent resets true", [(7, "C", Decimal("333"), True)], prices),
    ("one zero resets false", [(7, "Z", Decimal("333"), False)], prices),
    ("all absent", [(8, "X", Decimal("333"), True), (2, "C", Decimal("444"), True)], prices),
    ("no prices", rows, []),
    ("duplicate zero", [(8, "Z", Decimal("333"), False), (2, "Z", Decimal("444"), True)], prices),
    ("empty key matched", [(9, "", Decimal("333"), False)], [("", Decimal("8.25"))]),
]
for name, case_rows, case_prices in cases:
    check(name, case_rows, case_prices)
    print("PASS " + name)

rng = random.Random(20261013)
keys = ["", "A", "B", "C", "Z", "K1", "K2"]
for case_id in range(300):
    identities = rng.sample(range(1, 10000), rng.randrange(31))
    case_rows = [(identity, rng.choice(keys), Decimal(rng.randrange(-100, 101)) / 100,
                  bool(rng.randrange(2))) for identity in identities]
    case_prices = [(key, Decimal(rng.randrange(-10000, 10001)) / 100)
                   for key in keys if rng.randrange(2)]
    check(f"random {case_id}", case_rows, case_prices)
print("PASS 300 reproducible generated cases (seed=20261013)")
print("PASS total cases=309; row identity/order/multiplicity/value/found and stale-value reset checked")
