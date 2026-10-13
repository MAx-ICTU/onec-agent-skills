"""Finite relational model, not a 1C query interpreter or compiler.

The static check recognizes only the exact supplied and proposed query forms.
The model then checks their WHERE/ON placement under the task's cardinality.
None represents the join's NULL, never an empty reference or empty string.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "input"
ARTIFACTS = ROOT / "artifacts"
data = json.loads((INPUT / "data.json").read_text(encoding="utf-8-sig"))
before = (INPUT / "before.query").read_text(encoding="utf-8-sig")
proposed = (ARTIFACTS / "proposed.query").read_text(encoding="utf-8-sig")

def compact(text):
    return " ".join(text.split())

condition = "Разрешения.Активна = ИСТИНА"
old = compact(before)
new = compact(proposed)
assert old.endswith(" ГДЕ " + condition)
assert new == old.removesuffix(" ГДЕ " + condition) + " И " + condition
print("STATIC: proposed query moves only the active condition from WHERE to ON")

def validate(items, permissions):
    assert len(set(items)) == len(items)
    assert len({row[0] for row in permissions}) == len(permissions)
    assert all(item in items and active in (0, 1) and isinstance(comment, str)
               for item, active, comment in permissions)

def relation(items, permissions, variant):
    validate(items, permissions)
    result = []
    for item in items:
        matches = [row for row in permissions
                   if row[0] == item and (variant != "fixed" or row[1] == 1)]
        right_rows = matches or [None]
        for row in right_rows:
            is_active = row is not None and row[1] == 1
            if variant == "before" and not is_active:
                continue
            if variant == "where_or_null" and not (is_active or row is None):
                continue
            result.append((item, row[2] if row is not None else None))
    return result

def contract(items, permissions):
    # Independent lookup specification: exactly one output for each item.
    active_comments = {item: comment for item, active, comment in permissions if active == 1}
    return [(item, active_comments.get(item)) for item in items]

def show(rows):
    return json.dumps(rows, ensure_ascii=True)

items, permissions = data["items"], data["permissions"]
old_rows = relation(items, permissions, "before")
fixed_rows = relation(items, permissions, "fixed")
expected = contract(items, permissions)
assert Counter(old_rows) != Counter(expected)
assert Counter(fixed_rows) == Counter(expected)
print("DATA before:", show(old_rows))
print("DATA fixed:", show(fixed_rows))
print("DATA contract:", show(expected))
print("DATA where_or_null:", show(relation(items, permissions, "where_or_null")))
assert Counter(relation(items, permissions, "where_or_null")) != Counter(expected)

cases = [
    ("empty", [], []),
    ("no_permissions", ["A", "B"], []),
    ("one_active", ["A"], [["A", 1, "yes"]]),
    ("one_inactive", ["A"], [["A", 0, "no"]]),
    ("active_empty_comment", ["A"], [["A", 1, ""]]),
    ("inactive_empty_comment", ["A"], [["A", 0, ""]]),
    ("multiple_active_distinct_items", ["A", "B", "C"],
     [["A", 1, "same"], ["B", 1, "same"]]),
]
for name, test_items, test_permissions in cases:
    actual = relation(test_items, test_permissions, "fixed")
    target = contract(test_items, test_permissions)
    assert Counter(actual) == Counter(target), name
    assert len(actual) == len(test_items), name
    assert Counter(row[0] for row in actual) == Counter(test_items), name
    print("CASE", name + ":", show(actual), "PASS")

# Exhaust all absent / inactive / active assignments for three distinct items.
# Both empty and nonempty comments are included without inventing extra keys.
states = [None, (0, ""), (0, "comment"), (1, ""), (1, "comment")]
count = 0
for a in states:
    for b in states:
        for c in states:
            test_permissions = [[item, state[0], state[1]]
                                for item, state in zip(["A", "B", "C"], [a, b, c])
                                if state is not None]
            actual = relation(["A", "B", "C"], test_permissions, "fixed")
            assert Counter(actual) == Counter(contract(["A", "B", "C"], test_permissions))
            assert len(actual) == 3
            count += 1
print("EXHAUSTIVE finite states:", count, "PASS")
print("LIMIT: no 1C compilation/execution, platform NULL check, DB plan or timing performed")
