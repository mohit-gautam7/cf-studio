"""Codeforces problem-page parser built on html.parser (stdlib only).

Builds a light DOM tree, then extracts title, limits, statement sections,
sample tests, tags and rating from a problemset/contest problem page.
TeX stays in $$$...$$$ delimiters; the frontend renders it with KaTeX.
"""
import re
from html import escape
from html.parser import HTMLParser

VOID = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children = []
        self.parent = parent

    def classes(self):
        return (self.attrs.get("class") or "").split()


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("__root__")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
        # stray end tag: ignore

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def parse_html(html):
    b = _TreeBuilder()
    b.feed(html)
    return b.root


def walk(node):
    yield node
    for c in node.children:
        if isinstance(c, Node):
            yield from walk(c)


def find_all(node, tag=None, cls=None):
    out = []
    for n in walk(node):
        if n is node:
            continue
        if tag and n.tag != tag:
            continue
        if cls and cls not in n.classes():
            continue
        out.append(n)
    return out


def find(node, tag=None, cls=None):
    r = find_all(node, tag, cls)
    return r[0] if r else None


def text_of(node, sep=""):
    parts = []

    def rec(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif c.tag == "br":
                parts.append("\n")
            elif c.tag not in ("script", "style"):
                rec(c)

    rec(node)
    return sep.join(parts) if sep else "".join(parts)


def serialize(node):
    if isinstance(node, str):
        return escape(node, quote=False)
    if node.tag in ("script", "style"):
        return ""
    attrs = "".join(' %s="%s"' % (k, escape(str(v or ""), quote=True)) for k, v in node.attrs.items())
    inner = "".join(serialize(c) for c in node.children)
    if node.tag in VOID:
        return "<%s%s/>" % (node.tag, attrs)
    if node.tag == "__root__":
        return inner
    return "<%s%s>%s</%s>" % (node.tag, attrs, inner, node.tag)


def inner_html(node):
    return _fix_urls("".join(serialize(c) for c in node.children).strip())


def _fix_urls(html):
    return html.replace('src="//', 'src="https://').replace("src='//", "src='https://")


class ParseError(Exception):
    pass


def _pre_text(pre):
    """Extract sample text; newer CF wraps each line in div.test-example-line."""
    line_divs = [c for c in pre.children if isinstance(c, Node) and c.tag == "div"]
    if line_divs and all("test-example-line" in " ".join(d.classes()) for d in line_divs):
        return "\n".join(text_of(d) for d in line_divs).strip("\n")
    return text_of(pre).strip("\n")


def _limit_text(div):
    """Limit divs look like: <div class='time-limit'><div class='property-title'>..</div>2 seconds</div>"""
    parts = [c for c in div.children if isinstance(c, str)]
    tail = "".join(parts).strip()
    if tail:
        return tail
    texts = [text_of(c) for c in div.children if isinstance(c, Node) and "property-title" not in c.classes()]
    return " ".join(t for t in texts if t).strip()


def _strip_section_title(node):
    node.children = [c for c in node.children if not (isinstance(c, Node) and "section-title" in c.classes())]
    return node


def parse_time_limit_ms(s):
    m = re.search(r"([\d.]+)", s or "")
    return int(float(m.group(1)) * 1000) if m else 2000


def parse_memory_limit_mb(s):
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else 256


def parse_problem(html):
    root = parse_html(html)
    ps = find(root, "div", "problem-statement")
    if ps is None:
        raise ParseError("no div.problem-statement found — page layout not recognized")

    header = find(ps, "div", "header")
    title = text_of(find(header, "div", "title") or Node("div")).strip() if header else ""
    title = re.sub(r"^[A-Z][0-9]?\.\s*", "", title)
    tl = _limit_text(find(header, "div", "time-limit")) if header and find(header, "div", "time-limit") else ""
    ml = _limit_text(find(header, "div", "memory-limit")) if header and find(header, "div", "memory-limit") else ""

    input_spec = find(ps, "div", "input-specification")
    output_spec = find(ps, "div", "output-specification")
    sample_tests = find(ps, "div", "sample-tests")
    note = find(ps, "div", "note")

    special = {id(x) for x in (header, input_spec, output_spec, sample_tests, note) if x is not None}
    body_parts = []
    for c in ps.children:
        if isinstance(c, Node) and id(c) not in special:
            body_parts.append(serialize(c))
        elif isinstance(c, str) and c.strip():
            body_parts.append(escape(c, quote=False))
    statement_html = _fix_urls("".join(body_parts).strip())

    samples = []
    if sample_tests is not None:
        inputs = [n for n in find_all(sample_tests, "div", "input")]
        outputs = [n for n in find_all(sample_tests, "div", "output")]
        for i_div, o_div in zip(inputs, outputs):
            i_pre, o_pre = find(i_div, "pre"), find(o_div, "pre")
            if i_pre is not None and o_pre is not None:
                samples.append({"input": _pre_text(i_pre), "output": _pre_text(o_pre)})

    tags, rating = [], None
    for tb in find_all(root, cls="tag-box"):
        t = text_of(tb).strip()
        if t.startswith("*") and t[1:].strip().isdigit():
            rating = int(t[1:].strip())
        elif t:
            tags.append(t)

    return {
        "title": title or "Untitled problem",
        "time_limit_ms": parse_time_limit_ms(tl),
        "memory_limit_mb": parse_memory_limit_mb(ml),
        "statement_html": statement_html,
        "input_spec_html": inner_html(_strip_section_title(input_spec)) if input_spec else "",
        "output_spec_html": inner_html(_strip_section_title(output_spec)) if output_spec else "",
        "note_html": inner_html(_strip_section_title(note)) if note else "",
        "samples": samples,
        "tags": tags,
        "rating": rating,
    }


_URL_RE = re.compile(
    r"codeforces\.com/(?:problemset/problem/(\d+)/([A-Z][0-9]?)|(?:contest|gym)/(\d+)/problem/([A-Z][0-9]?))",
    re.IGNORECASE,
)


def parse_problem_url(url):
    """Return (contest_id, index) or None."""
    m = _URL_RE.search(url or "")
    if not m:
        return None
    if m.group(1):
        return int(m.group(1)), m.group(2).upper()
    return int(m.group(3)), m.group(4).upper()
