"""Turns the Income-tax Act PDF into provisions and citable chunks.

The PDF (as published on the Income Tax Department site, "as amended by Finance Act, 2026") is a
concatenation of per-section renders, so every section starts on a new page and its amendment
footnotes follow it as endnotes. Footnotes often quote the text that was substituted, so nothing
after the first footnote line of a section is ever treated as law.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

BODY_MARGIN = 27.6
CENTERED_X = 150  # chapter, part and schedule headings are centred; body text starts near the margin
MARKER_MAX_SIZE = 8.0  # footnote reference numbers are 7.1pt, body text 8.5pt
BASELINE_TOLERANCE = 3.0  # clause labels sit 1-2pt below the text they introduce
HEADER_BOTTOM = 45.0  # "Income Tax Department / Ministry of Finance" banner on every page

SECTION_NO = re.compile(r"^\[?\s*(\d{1,3}[A-Z]{0,5}(?:-[A-Z]+)?)\.\s*")
FOOTNOTE = re.compile(r"^(\d{1,3}[a-z]?)\.\s+(.*)$")
OMITTED_LINE = re.compile(
    r"^\[?(\d{1,3}[A-Z]{0,5})\.\s*(?:(&|and|to)\s*(\d{1,3}[A-Z]{0,5})\.\s*)?\[?\s*Omitted by", re.I
)
CHAPTER = re.compile(r"^CHAPTER\s+([IVXLC]+(?:-?[A-Z]{1,3})?)$")
SCHEDULE = re.compile(r"^THE\s+([A-Z]+)\s+SCHEDULE$")
EDITION = re.compile(r"\[AS AMENDED BY ([^\]]+)\]")

LABEL = re.compile(r"^\[?\(([0-9]+[A-Z]*|[a-z]{1,7}|[A-Z]{1,2})\)(?=\s|\[|\(|—|$)")
PROVISO = re.compile(r"^\[?\s*Provided\b")
EXPLANATION = re.compile(r"^\[?\s*['\"]?Explanation(?:\s*(\d+[A-Z]?))?\s*\.?\s*[—–-]")

ROMAN = [
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
    "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv",
]
# A wrapped line that begins with "(2) of section 23" follows a line ending in one of these words.
CONTINUES = re.compile(
    r"(?:sub-section|section|clause|sub-clause|item|of|in|under|to|with|by|rule|sub-rule|paragraph)\s*$",
    re.I,
)
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
            "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth"]

MAX_CHUNK_CHARS = 1800  # about 400 tokens; the embedding model truncates at 512
MAX_GAP = 3

# Kinds of list labels, in the usual nesting order: (1) > (a) > (i) > (A).
NUM, ALPHA, ROMAN_T, UPPER = 1, 2, 3, 4
FIRST = {NUM: "1", ALPHA: "a", ROMAN_T: "i", UPPER: "A"}


@dataclass
class Span:
    text: str
    x: float
    bold: bool
    italic: bool


@dataclass
class Line:
    page: int
    y: float
    spans: list[Span]

    @property
    def x(self) -> float:
        return self.spans[0].x

    @property
    def text(self) -> str:
        return clean("".join(s.text for s in self.spans))

    @property
    def all_bold(self) -> bool:
        return all(s.bold for s in self.spans if s.text.strip(" []\xa0"))

    @property
    def all_styled(self) -> bool:
        return all(s.bold or s.italic for s in self.spans if s.text.strip())

    def leading_bold(self) -> str:
        out = ""
        for s in self.spans:
            if not s.text.strip():
                out += s.text
                continue
            if not s.bold:
                break
            out += s.text
        return out.strip()


@dataclass
class Marker:
    page: int
    y: float
    label: str


@dataclass
class Unit:
    """A run of text under one structural position, e.g. Section 24(b) or its first proviso."""
    path: tuple[str, ...]
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return join_lines(self.lines)


@dataclass
class Chunk:
    ref: str
    path: tuple[str, ...]
    page_start: int
    page_end: int
    text: str
    context: str
    amended_by: list[str]


@dataclass
class Provision:
    kind: str  # "section" or "schedule"
    number: str
    heading: str
    chapter: str | None
    chapter_title: str | None
    part: str | None
    seq: int
    omitted: bool = False
    starts_chapter: bool = False
    units: list[Unit] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    note_order: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    omitted_text: str = ""
    omitted_page: int = 0

    @property
    def citation_base(self) -> str:
        return f"Section {self.number}" if self.kind == "section" else self.number

    @property
    def body_lines(self) -> list[Line]:
        return [line for u in self.units for line in u.lines]

    @property
    def page_start(self) -> int:
        lines = self.body_lines
        return lines[0].page if lines else self.omitted_page

    @property
    def page_end(self) -> int:
        lines = self.body_lines
        return lines[-1].page if lines else self.omitted_page

    @property
    def text(self) -> str:
        if self.omitted:
            return self.omitted_text
        return "\n".join(u.text for u in self.units if u.text)


@dataclass
class ParsedAct:
    edition: str
    page_count: int
    provisions: list[Provision]


def clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("[***]", "(omitted)")
    return re.sub(r"\s+", " ", text).strip()


_LINE_BREAK_HYPHEN = re.compile(r"(?<=[A-Za-z])- (?=[a-z])")


def join_lines(lines) -> str:
    """Join visual lines into running text. A compound split at the end of a line ("sub-" / "section")
    is rejoined; the Act hyphenates only compounds, never ordinary words, so the hyphen stays."""
    return _LINE_BREAK_HYPHEN.sub("-", clean(" ".join(line.text for line in lines)))


def read_lines(doc: pymupdf.Document) -> tuple[list[Line], list[Marker]]:
    lines: list[Line] = []
    markers: list[Marker] = []
    for page_index, page in enumerate(doc):
        spans = []
        for block in page.get_text("dict")["blocks"]:
            for raw_line in block.get("lines", []):
                for s in raw_line["spans"]:
                    if s["origin"][1] < HEADER_BOTTOM:
                        continue
                    if not s["text"].strip():
                        continue
                    baseline = s["origin"][1]
                    if s["size"] < MARKER_MAX_SIZE:
                        markers.append(Marker(page_index + 1, baseline, s["text"].strip()))
                        continue
                    spans.append((baseline, Span(s["text"], s["bbox"][0], bool(s["flags"] & 16), bool(s["flags"] & 2))))
        spans.sort(key=lambda t: t[0])
        rows: list[tuple[float, list[Span]]] = []
        for baseline, span in spans:
            if rows and baseline - rows[-1][0] <= BASELINE_TOLERANCE:
                rows[-1][1].append(span)
            else:
                rows.append((baseline, [span]))
        for baseline, row in rows:
            row.sort(key=lambda s: s.x)
            lines.append(Line(page_index + 1, baseline, row))
    return lines, markers


def _roman_index(label: str) -> int:
    return ROMAN.index(label) if label in ROMAN else -1


def _level_of(node: str) -> int:
    if node.startswith("~"):
        return 0  # proviso / Explanation nodes
    return int(node[0])


def _node(kind: int, label: str) -> str:
    return f"{kind}{label}"


def _label(node: str) -> str:
    return node[1:]


def _follows(kind: int, prev: str, label: str) -> bool:
    """True if `label` can be the next item after `prev` in a list of the same kind.

    Inserted items such as (1A), (ba) or (iia) follow their base item. A gap of a few
    positions is allowed because items omitted from the Act are sometimes not printed.
    """
    if label == prev:
        return False
    if kind == NUM:
        a, b = int(re.match(r"\d+", prev).group()), int(re.match(r"\d+", label).group())
        return 0 < b - a <= MAX_GAP or (b == a and label > prev)
    if kind == ROMAN_T:
        base_prev = prev.rstrip("abc") if prev not in ROMAN else prev
        base = label.rstrip("abc") if label not in ROMAN else label
        if base == base_prev:
            return label > prev
        return 0 < _roman_index(base) - _roman_index(base_prev) <= MAX_GAP
    if label[0] == prev[0]:
        return label > prev
    return 0 < ord(label[0]) - ord(prev[0]) <= MAX_GAP and len(label) == 1


def _open_item(path: list[str], kind: int, label: str) -> int | None:
    """Index of the open list item that `label` continues, deepest first."""
    for i in range(len(path) - 1, -1, -1):
        if _level_of(path[i]) == kind and _follows(kind, _label(path[i]), label):
            return i
    return None


def kind_of(label: str, path: list[str]) -> int:
    if label[0].isdigit():
        return NUM
    if label.isupper():
        return UPPER
    if label in ROMAN or (label[:-1] in ROMAN and label[-1] in "abc"):
        if _open_item(path, ROMAN_T, label) is not None:
            return ROMAN_T
        if _open_item(path, ALPHA, label) is not None:
            return ALPHA  # (i) after (h), (v) after (u)
        if label == "i":
            return ROMAN_T
    return ALPHA


def place(path: list[str], label: str) -> list[str] | None:
    """New structural path after `label`, or None when the label is just a cross reference."""
    kind = kind_of(label, path)
    idx = _open_item(path, kind, label)
    if idx is not None:
        return path[:idx] + [_node(kind, label)]
    if label == FIRST[kind]:
        return path + [_node(kind, label)]
    return None


def render_ref(base: str, path: tuple[str, ...]) -> str:
    out = base
    seen_marker = False
    for node in path:
        if node.startswith("~"):
            out += ", " + node[1:]
            seen_marker = True
        else:
            out += (" " if seen_marker and not out.endswith(")") else "") + f"({_label(node)})"
    return out


class _Builder:
    def __init__(self, markers: list[Marker]):
        self.markers = markers
        self.provisions: list[Provision] = []
        self.chapter: str | None = None
        self.chapter_title: str | None = None
        self.part: str | None = None
        self.schedule: str | None = None
        self.pending_heading: list[Line] = []
        self.current: Provision | None = None
        self.path: list[str] = []
        self.in_notes = False
        self.expect_chapter_title = False
        self.chapter_started = False
        self.last_was_part = False
        self.proviso_counts: dict[tuple[str, ...], int] = {}

    def start(self, kind: str, number: str, heading: str) -> Provision:
        p = Provision(kind, number, heading, self.chapter, self.chapter_title, self.part, len(self.provisions))
        p.starts_chapter = self.chapter_started
        self.chapter_started = False
        self.provisions.append(p)
        self.current = p
        self.path = []
        self.in_notes = False
        self.proviso_counts = {}
        p.units.append(Unit(()))
        return p

    def feed(self, line: Line) -> None:
        text = line.text
        if not text:
            return
        was_part, self.last_was_part = self.last_was_part, False

        if (m := CHAPTER.match(text)) and line.all_styled and line.x > CENTERED_X:
            self.chapter, self.chapter_title, self.part, self.schedule = m.group(1), None, None, None
            self.expect_chapter_title = True
            self.chapter_started = True
            self.pending_heading = []
            self.in_notes = True  # anything before the first section of a chapter is preamble
            return
        if (m := SCHEDULE.match(text)) and line.all_styled:
            self.schedule = m.group(1).title() + " Schedule"
            self.chapter, self.chapter_title, self.part = None, None, None
            self.pending_heading = []
            self.start("schedule", self.schedule, "")
            return

        if line.x > CENTERED_X:
            if self.expect_chapter_title and line.all_bold and text.isupper():
                self.chapter_title = text.capitalize()
                self.expect_chapter_title = False
                return
            current = self.current
            if (
                self.schedule and current and current.kind == "schedule" and current.number == self.schedule
                and not current.heading and not text.startswith("[")
            ):
                current.heading = text.capitalize() if text.isupper() else text
                return
            if was_part and text.isupper() and not line.all_styled:
                self.part += " - " + text.capitalize()
                return
            if line.all_styled:
                self.part = text
                self.last_was_part = True
                return

        if line.x < BODY_MARGIN + 1.5 and (m := OMITTED_LINE.match(text)):
            joiner = "to" if m.group(2) == "to" else "and"
            number = m.group(1) if not m.group(3) else f"{m.group(1)} {joiner} {m.group(3)}"
            p = self.start("section", number, "")
            p.omitted = True
            p.omitted_text = text
            p.omitted_page = line.page
            p.units = []
            self.in_notes = True
            return

        lead = line.leading_bold()
        if (m := SECTION_NO.match(lead)) and not PROVISO.match(lead):
            heading = clean(" ".join(h.text for h in self.pending_heading)).strip("[] ")
            self.pending_heading = []
            self.expect_chapter_title = False
            number = m.group(1)
            if self.schedule:
                self.start("schedule", f"{self.schedule}, rule {number}", heading)
            else:
                self.start("section", number, heading)
            rest = self._strip_number(line)
            if rest is not None:
                self.body(rest)
            return

        if line.all_bold and line.x < BODY_MARGIN + 8 and not PROVISO.match(text):
            # Section headings sit just above the section number; footnotes are never bold.
            self.pending_heading.append(line)
            return

        if self.in_notes:
            self.pending_heading = []
            self.note(line)
            return

        if (
            BODY_MARGIN + 1.5 < line.x < BODY_MARGIN + 3.5
            and not line.spans[0].bold
            and (fm := FOOTNOTE.match(text))
            and "Act" in text
        ):
            self.in_notes = True
            self.pending_heading = []
            self.note(line, fm)
            return

        if self.pending_heading:
            for h in self.pending_heading:
                self.body(h)
            self.pending_heading = []
        self.body(line)

    def _strip_number(self, line: Line) -> Line | None:
        remaining = list(line.spans)
        consumed = ""
        while remaining and SECTION_NO.match(consumed + remaining[0].text) is None:
            consumed += remaining.pop(0).text
        if not remaining:
            return None
        first = remaining.pop(0)
        m = SECTION_NO.match(consumed + first.text)
        leftover = (consumed + first.text)[m.end():]
        if leftover.strip():
            remaining.insert(0, Span(leftover, first.x, first.bold, first.italic))
        if not remaining:
            return None
        return Line(line.page, line.y, remaining)

    def note(self, line: Line, match: re.Match | None = None) -> None:
        if self.current is None:
            return
        match = match or (FOOTNOTE.match(line.text) if line.x < BODY_MARGIN + 3.5 else None)
        if match and "Act" in line.text:
            label = match.group(1)
            self.current.notes[label] = match.group(2)
            self.current.note_order.append(label)
        elif self.current.note_order:
            last = self.current.note_order[-1]
            self.current.notes[last] += " " + line.text

    def body(self, line: Line) -> None:
        if self.current is None or self.current.omitted:
            return
        text = line.text
        unit = self.current.units[-1]
        prev_text = unit.lines[-1].text if unit.lines else ""

        if PROVISO.match(text) and any(s.bold for s in line.spans[:2]):
            self._enter_marker("proviso")
            self.current.units[-1].lines.append(line)
            return
        if m := EXPLANATION.match(text):
            self._enter_marker("Explanation" + (f" {m.group(1)}" if m.group(1) else ""))
            self.current.units[-1].lines.append(line)
            return

        labels = []
        rest = text
        while lm := LABEL.match(rest):
            labels.append(lm.group(1))
            rest = rest[lm.end():].lstrip()
        if labels and not CONTINUES.search(prev_text):
            new_path = list(self.path)
            for label in labels:
                placed = place(new_path, label)
                if placed is None:
                    break
                new_path = placed
            if new_path != self.path:
                self.path = new_path
                self.current.units.append(Unit(tuple(self.path), [line]))
                return

        if line.x < BODY_MARGIN + 1.5 and self.path:
            # Closing words of a list belong to whatever introduced the list: the nearest
            # proviso or Explanation if we are inside one, otherwise the sub-section.
            target = self._closing_target()
            if len(self.path) > len(target):
                self.path = target
                self.current.units.append(Unit(tuple(self.path), [line]))
                return

        unit.lines.append(line)

    def _closing_target(self) -> list[str]:
        for i in range(len(self.path) - 1, -1, -1):
            if self.path[i].startswith("~"):
                return self.path[: i + 1]
        if self.path and _level_of(self.path[0]) == 1:
            return self.path[:1]
        return []

    def _enter_marker(self, kind: str) -> None:
        base = list(self.path)
        if any(n.startswith("~") for n in base):
            base = base[: next(i for i, n in enumerate(base) if n.startswith("~"))]
        if kind == "proviso":
            key = tuple(base)
            n = self.proviso_counts.get(key, 0)
            self.proviso_counts[key] = n + 1
            name = f"~{ORDINALS[n] if n < len(ORDINALS) else str(n + 1)} proviso"
        else:
            name = f"~{kind}"
        self.path = base + [name]
        self.current.units.append(Unit(tuple(self.path)))

    def finish(self) -> list[Provision]:
        provisions = [p for p in self.provisions if p.omitted or any(u.lines for u in p.units)]
        provisions = restore_order(provisions)
        for i, p in enumerate(provisions):
            p.seq = i
            p.units = [u for u in p.units if u.lines]
            p.chunks = build_chunks(p, self.markers)
        return provisions


def _base_number(p: Provision) -> int:
    return int(re.match(r"\d+", p.number).group())


def restore_order(provisions: list[Provision]) -> list[Provision]:
    """Put a section that the PDF printed far from its place back where it belongs.

    The 2026 PDF prints section 139 (with the Chapter XIV heading) before Chapter I. Without this,
    sections 139A onwards would inherit the previous chapter and part.
    """
    out = list(provisions)
    sections = [p for p in out if p.kind == "section"]
    for i, p in enumerate(sections[:-1]):
        n = _base_number(p)
        if not (n > _base_number(sections[i + 1]) + 10 and (i == 0 or n > _base_number(sections[i - 1]) + 10)):
            continue
        out.remove(p)
        idx = next(
            (k for k, q in enumerate(out) if q.kind == "section" and (_base_number(q), q.number) > (n, p.number)),
            len(out),
        )
        out.insert(idx, p)
        if p.starts_chapter:
            leaked_part = out[idx - 1].part if idx else None
            for q in out[idx + 1:]:
                if q.starts_chapter or q.kind != "section":
                    break
                q.chapter, q.chapter_title = p.chapter, p.chapter_title
                if q.part == leaked_part:
                    q.part = p.part
    return out


def _anchor(path: tuple[str, ...]) -> tuple[str, ...]:
    out = []
    brackets = 0
    for node in path:
        out.append(node)
        if node.startswith("~"):
            break
        brackets += 1
        if brackets == 2:
            break
    return tuple(out)


def _amendments(lines: list[Line], markers: list[Marker], notes: dict[str, str]) -> list[str]:
    found = []
    for m in markers:
        if m.label not in notes:
            continue
        for line in lines:
            if line.page == m.page and -3 <= line.y - m.y <= 10:
                note = notes[m.label].split(" Prior to ")[0].strip()
                if note not in found:
                    found.append(note)
                break
    return found


def build_chunks(p: Provision, markers: list[Marker]) -> list[Chunk]:
    if p.omitted:
        return [Chunk(p.citation_base, (), p.page_start, p.page_end, p.omitted_text, p.heading or p.citation_base, [])]

    # Units under the same anchor (e.g. Section 80C(2)(xvi) and its items (a), (b)) form one chunk;
    # a chunk that would outgrow the embedding window is split between lines.
    groups: list[tuple[tuple[str, ...], list[Line]]] = []
    prev_anchor = None
    for unit in p.units:
        anchor = _anchor(unit.path)
        starts_group = anchor != prev_anchor or (unit.path == anchor and bool(anchor) and anchor[-1].startswith("~"))
        for i, line in enumerate(unit.lines):
            size = sum(len(x.text) + 1 for x in groups[-1][1]) if groups else 0
            if not groups or (i == 0 and starts_group) or size + len(line.text) > MAX_CHUNK_CHARS:
                groups.append((anchor, [line]))
            else:
                groups[-1][1].append(line)
        prev_anchor = anchor

    leads: dict[tuple[str, ...], str] = {}
    for unit in p.units:
        leads.setdefault(unit.path, unit.text[:200])

    page_markers = [m for m in markers if p.page_start <= m.page <= p.page_end]
    chunks = []
    for anchor, lines in groups:
        parent_lead = leads.get(anchor[:-1], "") if anchor else ""
        context = " ".join(part for part in [p.citation_base, p.heading, p.chapter_title or "", parent_lead] if part)
        chunks.append(
            Chunk(
                ref=render_ref(p.citation_base, anchor),
                path=tuple(n[1:] for n in anchor),
                page_start=lines[0].page,
                page_end=lines[-1].page,
                text=join_lines(lines),
                context=context,
                amended_by=_amendments(lines, page_markers, p.notes),
            )
        )
    return chunks


def parse_pdf(path: Path) -> ParsedAct:
    doc = pymupdf.open(path)
    lines, markers = read_lines(doc)
    edition = ""
    for line in lines[:400]:
        if m := EDITION.search(line.text):
            edition = m.group(1).title()
            break
    builder = _Builder(markers)
    for line in lines:
        builder.feed(line)
    return ParsedAct(edition=edition, page_count=doc.page_count, provisions=builder.finish())
