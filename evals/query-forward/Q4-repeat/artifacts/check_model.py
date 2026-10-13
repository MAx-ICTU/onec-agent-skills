"""Executed Python models; does not compile or execute BSL or 1C queries."""
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "input" / "data.json"


def exact(a, b):
    return a == b


def illustrative_ascii_equal(a, b):
    # An explicit toy predicate, NOT a validated implementation of 1C comparison.
    assert a.isascii() and b.isascii()
    return a.rstrip(" ").lower() == b.rstrip(" ").lower()


def initial_rows(pairs):
    return [dict(id=i, item=item, price=777 + pos, exists=bool(pos % 2))
            for pos, (i, item) in enumerate(pairs)]


def original(rows, prices, equal):
    result = [dict(row) for row in rows]
    for row in result:
        matches = [price for item, price in prices if equal(row["item"], item)]
        assert len(matches) <= 1, "Fixture violates unique matching price contract"
        row["exists"] = bool(matches)
        row["price"] = matches[0] if matches else 0
    return result


def batched(rows, prices, equal):
    result = [dict(row) for row in rows]
    by_id = {row["id"]: row for row in result}
    assert len(by_id) == len(result)
    joined = []
    for source in rows:
        matches = [(item, price) for item, price in prices
                   if equal(source["item"], item)]
        assert len(matches) <= 1, "Fixture violates unique matching price contract"
        if matches:
            joined.append((source["id"], matches[0][1], True))
        else:
            joined.append((source["id"], 0, False))
    # Deliberately arbitrary query order: source table must retain its order.
    for identifier, price, exists in reversed(joined):
        by_id[identifier]["price"] = price
        by_id[identifier]["exists"] = exists
    return result


def packed(rows):
    return [[r["id"], r["item"], r["price"], r["exists"]] for r in rows]


def compare(pairs, prices, equal=exact):
    rows = initial_rows(pairs)
    baseline = original(rows, prices, equal)
    proposed = batched(rows, prices, equal)
    assert proposed == baseline
    assert [(r["id"], r["item"]) for r in proposed] == list(pairs)
    return proposed


def main():
    data = json.loads(DATA.read_text(encoding="utf-8-sig"))
    sample = compare([tuple(row) for row in data["rows"]], data["prices"])
    expected = [[1, "A", 10, True], [2, "B", 20, True],
                [3, "A", 10, True], [4, "C", 0, False], [5, "Z", 0, True]]
    assert packed(sample) == expected
    print("MODEL: exact Python equality; no 1C runtime")
    print("sample result:", json.dumps(packed(sample), ensure_ascii=False))
    print("Analytical BSL invocation count for sample: original=5; proposed=1 packet (2 statements); not measured in 1C")

    cases = [
        ("empty", [], [["A", 10]]),
        ("one-present", [(90, "A")], [["A", 10]]),
        ("one-missing", [(90, "C")], [["A", 10]]),
        ("one-zero", [(90, "Z")], [["Z", 0]]),
        ("all-missing", [(31, "A"), (2, "B")], []),
        ("repeats-and-order", [(31, "A"), (2, "B"), (9, "A")],
         [["B", 20], ["A", 10]]),
        ("empty-string-key", [(7, ""), (4, "C")], [["", 0]]),
    ]
    for name, pairs, prices in cases:
        print("PASS", name, json.dumps(packed(compare(pairs, prices)), ensure_ascii=False))

    count = 0
    keys = ("A", "B", "C")
    identifiers = (93, 4, 28, 7)
    for size in range(5):
        for items in itertools.product(keys, repeat=size):
            for states in itertools.product((None, 0, 10), repeat=len(keys)):
                prices = [(k, p) for k, p in zip(keys, states) if p is not None]
                compare(list(zip(identifiers, items)), prices)
                count += 1
    assert count == 3267
    print("PASS exhaustive exact-equality finite model datasets:", count)

    aliases = [(41, "a"), (2, "A "), (11, "A"), (8, "b "), (19, "missing")]
    alias_prices = [("A", 10), ("B", 0)]
    alias_result = compare(aliases, alias_prices, illustrative_ascii_equal)
    assert packed(alias_result) == [[41, "a", 10, True], [2, "A ", 10, True],
                                    [11, "A", 10, True], [8, "b ", 0, True],
                                    [19, "missing", 0, False]]
    print("PASS illustrative ASCII equality predicate:", json.dumps(packed(alias_result)))
    naive = dict(alias_prices)
    assert naive.get("a") is None and naive.get("A ") is None
    print("COUNTEREXAMPLE toy query equality vs exact string dictionary: 'a' and 'A ' miss")
    print("BOUNDARY: ASCII predicate does not validate 1C collation or Unicode rules")

    selected = [(k, p) for k, p in data["prices"]
                if any(exact(item, k) for _, item in data["rows"])]
    assert len(selected) == 3 and len(sample) == 5
    print("COUNTEREXAMPLE returning price rows only: 3 returned vs 5 required source results")

    code = (ROOT / "proposed.bsl").read_text(encoding="utf-8-sig")
    assert code.count("Запрос.ВыполнитьПакет()") == 1
    assert "ЛЕВОЕ СОЕДИНЕНИЕ" in code and "Цены.Товар ЕСТЬ NULL" in code
    assert "ПОМЕСТИТЬ ВТИсходныеСтроки" in code
    assert "РезультатыПакета[1].Выбрать()" in code
    assert "СтрокиПоИдентификатору.Получить(" in code
    assert "СтрокаДанных.Цена = Выборка.Цена;" in code
    assert "СтрокаДанных.ЕстьЦена = Выборка.ЕстьЦена;" in code
    assert "Строки.Количество() = 0" in code
    print("PASS static text checks (not a BSL parser/compiler)")
    print("ALL MODEL CHECKS PASSED")


if __name__ == "__main__":
    main()
