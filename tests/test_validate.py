from buglens.onboard.validate import citation_valid, validate_sentences

FILE_LINES = {"shop/core.py": 15, "shop/models.py": 17}
ALLOWED = {"shop/core.py": [(6, 8)], "shop/models.py": [(11, 12)]}


def test_missing_file_rejected():
    assert not citation_valid("nope.py", 1, FILE_LINES, ALLOWED)


def test_out_of_range_lines_rejected():
    assert not citation_valid("shop/core.py", 0, FILE_LINES, ALLOWED, strict=False)
    assert not citation_valid("shop/core.py", 16, FILE_LINES, ALLOWED, strict=False)
    assert citation_valid("shop/core.py", 15, FILE_LINES, ALLOWED, strict=False)


def test_line_outside_provided_symbols_rejected_in_strict_mode():
    assert not citation_valid("shop/core.py", 3, FILE_LINES, ALLOWED, strict=True)
    assert citation_valid("shop/core.py", 7, FILE_LINES, ALLOWED, strict=True)
    assert citation_valid("shop/core.py", 3, FILE_LINES, ALLOWED, strict=False)


def test_sentence_without_valid_citation_dropped():
    raw = [
        {"text": "helper doubles values.", "citations": [{"path": "shop/core.py", "line": 7}]},
        {"text": "Invented claim.", "citations": [{"path": "shop/fake.py", "line": 2}]},
        {"text": "No citations at all.", "citations": []},
        {"text": "Mixed.", "citations": [{"path": "shop/models.py", "line": 12},
                                         {"path": "shop/models.py", "line": 99}]},
        "not a dict",
    ]
    kept, stats = validate_sentences(raw, FILE_LINES, ALLOWED)
    assert [s.text for s in kept] == ["helper doubles values.", "Mixed."]
    assert all(s.valid for s in kept)
    assert [(c.path, c.line) for c in kept[1].citations] == [("shop/models.py", 12)]
    assert stats["kept"] == 2 and stats["dropped"] == 3
    assert stats["citations"] == 4 and stats["valid_citations"] == 2


def test_bad_types_rejected():
    assert not citation_valid("shop/core.py", "7", FILE_LINES, ALLOWED)
    assert not citation_valid("shop/core.py", True, FILE_LINES, ALLOWED)
    kept, _ = validate_sentences([{"text": "x", "citations": [{"path": "shop/core.py",
                                                                "line": "7"}]}],
                                 FILE_LINES, ALLOWED)
    assert len(kept) == 1  # numeric strings are coerced
