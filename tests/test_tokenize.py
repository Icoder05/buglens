from buglens.retrieval.tokenize_code import split_identifier, tokenize


def test_dotted_camel_case():
    toks = tokenize("QuerySet.filter")
    assert "queryset" in toks and "query" in toks and "set" in toks and "filter" in toks


def test_acronym_camel_case():
    toks = tokenize("HTTPResponseError")
    assert toks[0] == "httpresponseerror"
    assert {"http", "response", "error"} <= set(toks)


def test_snake_case_keeps_full_identifier():
    toks = tokenize("snake_case_name")
    assert toks == ["snake_case_name", "snake", "case", "name"]


def test_stopwords_and_short_tokens_dropped():
    toks = tokenize("if the x is a None def self")
    assert toks == []


def test_lowercase_and_non_alnum_split():
    assert tokenize("Fix: crash-on-empty list!") == ["fix", "crash", "empty", "list"]


def test_split_identifier():
    assert split_identifier("parseJSON2Dict") == ["parse", "JSON", "2", "Dict"]
