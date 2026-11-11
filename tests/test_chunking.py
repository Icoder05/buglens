from buglens.chunking.python_ast import chunk_file, innermost_chunk

SOURCE = '''"""Doc."""
import os

X = 1


@decorator
def top(a):
    return a


class A:
    """Class doc."""
    attr = 2

    @property
    def p(self):
        return 1

    @p.setter
    def p(self, v):
        pass

    class Inner:
        def m(self):
            return os.sep


async def coro():
    await other()
'''


def _by_id(chunks):
    return {c.chunk_id: c for c in chunks}


def test_chunks_and_qualnames():
    chunks, ok = chunk_file("pkg/mod.py", SOURCE)
    assert ok
    ids = set(_by_id(chunks))
    assert ids == {
        "pkg/mod.py::top", "pkg/mod.py::A", "pkg/mod.py::A.p", "pkg/mod.py::A.p#2",
        "pkg/mod.py::A.Inner", "pkg/mod.py::A.Inner.m", "pkg/mod.py::coro",
        "pkg/mod.py::<module>",
    }
    c = _by_id(chunks)
    assert c["pkg/mod.py::top"].kind == "function"
    assert c["pkg/mod.py::A.p"].kind == "method"
    assert c["pkg/mod.py::A"].kind == "class"
    assert c["pkg/mod.py::coro"].kind == "function"
    assert [x.chunk_id for x in chunks] == sorted(x.chunk_id for x in chunks)


def test_spans_start_at_decorator():
    c = _by_id(chunk_file("pkg/mod.py", SOURCE)[0])
    assert (c["pkg/mod.py::top"].start_line, c["pkg/mod.py::top"].end_line) == (7, 9)
    assert c["pkg/mod.py::A.p"].start_line == 16  # the @property line


def test_class_chunk_excludes_method_bodies():
    c = _by_id(chunk_file("pkg/mod.py", SOURCE)[0])
    text = c["pkg/mod.py::A"].text
    assert "attr = 2" in text and "Class doc." in text
    assert "return 1" not in text and "os.sep" not in text


def test_module_chunk_holds_top_level_code():
    c = _by_id(chunk_file("pkg/mod.py", SOURCE)[0])
    text = c["pkg/mod.py::<module>"].text
    assert "import os" in text and "X = 1" in text
    assert "return a" not in text


def test_embed_text_header_and_truncation():
    chunks, _ = chunk_file("pkg/mod.py", SOURCE, max_chars=40)
    c = _by_id(chunks)["pkg/mod.py::top"]
    assert c.text.startswith("pkg/mod.py\ntop\n")
    assert len(c.text) <= 40
    assert c.end_line == 9  # labels keep the full span


def test_innermost_chunk():
    chunks, _ = chunk_file("pkg/mod.py", SOURCE)
    assert innermost_chunk(chunks, 9).chunk_id == "pkg/mod.py::top"
    assert innermost_chunk(chunks, 14).chunk_id == "pkg/mod.py::A"
    assert innermost_chunk(chunks, 26).chunk_id == "pkg/mod.py::A.Inner.m"
    assert innermost_chunk(chunks, 4).chunk_id == "pkg/mod.py::<module>"


def test_syntax_error_falls_back_to_windows():
    src = "print 'python2'\n" + "\n".join(f"x{i} = {i}" for i in range(129))
    chunks, ok = chunk_file("old.py", src)
    assert not ok
    spans = [(c.start_line, c.end_line) for c in chunks]
    assert spans == [(1, 60), (41, 100), (81, 130)]
    assert all(c.kind == "window" for c in chunks)
    assert chunks[0].chunk_id == "old.py::L1-60"
