"""Rule-based detectors for Dutch personal data.

Each detector yields ``Match`` objects. Detection is deliberately conservative
where false positives would damage clinical text (names), and aggressive where
the pattern is unambiguous (BSN, e-mail, IBAN).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from importlib import resources

from nl_zorg_pii.bsn import is_valid_bsn


@dataclass(frozen=True)
class Match:
    kind: str  # BSN, EMAIL, TELEFOON, IBAN, POSTCODE, ADRES, GEBOORTEDATUM, NAAM
    start: int
    end: int
    value: str


Detector = Callable[[str], Iterator[Match]]

# --- Unambiguous patterns -----------------------------------------------------

_BSN_RE = re.compile(r"(?<!\d)(?<!\d\.)(\d{4}[ .-]?\d{2}[ .-]?\d{3}|\d{9}|\d{8})(?!\d|\.\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w/.])(?:\+31|0031|0)\s?[1-9](?:[\s-]?\d){8}(?!\d|[./]\d)")
_IBAN_RE = re.compile(r"\bNL\d{2}\s?[A-Z]{4}(?:\s?\d{4}){2}\s?\d{2}\b")
_POSTCODE_RE = re.compile(r"\b[1-9]\d{3}\s?[A-Z]{2}\b")
_STREET_SUFFIX = (
    "straat|laan|weg|plein|singel|kade|dijk|gracht|hof|dreef|pad|steeg|markt|baan|erf|park|"
    "allee|ring|boulevard|burg|wal|haven|plantsoen|hoek"
)
_ADDRESS_RE = re.compile(
    rf"\b(?:(?:[A-Z][a-zà-ÿ'’-]+|van|de|der|den|het|'t)\s){{0,3}}"
    rf"[A-Za-zà-ÿ'’-]*(?:{_STREET_SUFFIX})\s+\d{{1,4}}(?:\s?[a-zA-Z]\b|-\d+)?"
)

_MONTHS = (
    "januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|"
    "jan|feb|mrt|apr|jun|jul|aug|sep|sept|okt|nov|dec"
)
_DATE_NUMERIC_RE = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.](19|20)\d{2}\b")
_DATE_TEXT_RE = re.compile(rf"\b(0?[1-9]|[12]\d|3[01])\s+(?:{_MONTHS})\.?\s+(19|20)\d{{2}}\b", re.I)
_DOB_CONTEXT_RE = re.compile(
    r"(geboren|geboortedatum|geb\.?|gebdatum|date of birth|dob)\s*(?:op|:)?\s*$", re.I
)

# --- Names --------------------------------------------------------------------

_NAME_WORD = r"(?:[A-Z][\w'’-]+|[A-Z]\.|(?:van|der|den|de|het|ten|ter|te|op|'t)\b)"
_TITLE_RE = re.compile(
    r"\b(?i:dhr|mevr|mw|mr|drs|dr|ir|ing|de heer|mevrouw|meneer|mijnheer|patiënt|patiente|"
    r"patiënte|cliënt|cliënte)\.?\s+"
    rf"({_NAME_WORD}(?:\s{_NAME_WORD}){{0,4}})",
)
_INTRO_RE = re.compile(
    r"\b(?i:ik ben|mijn naam is|ik heet|u spreekt met|je spreekt met|dit is|naam:|patiënt:|"
    r"cliënt:)\s+"
    rf"((?:[A-Z][\w'’-]+)(?:\s{_NAME_WORD}){{0,4}})",
)
_PARTICLES = {"van", "de", "der", "den", "het", "te", "ten", "ter", "op", "'t"}


def _load_first_names() -> frozenset[str]:
    text = resources.files("nl_zorg_pii").joinpath("data/voornamen.txt").read_text("utf-8")
    return frozenset(line.strip().lower() for line in text.splitlines() if line.strip())


_FIRST_NAMES = _load_first_names()
_NAME_TOKEN_RE = re.compile(r"\b([A-Z][a-zà-ÿ]{1,}(?:-[A-Z][a-zà-ÿ]+)?)\b")


def detect_bsn(text: str) -> Iterator[Match]:
    for m in _BSN_RE.finditer(text):
        raw = m.group(1)
        if is_valid_bsn(raw):
            yield Match("BSN", m.start(1), m.end(1), raw)


def detect_email(text: str) -> Iterator[Match]:
    for m in _EMAIL_RE.finditer(text):
        yield Match("EMAIL", m.start(), m.end(), m.group())


def detect_phone(text: str) -> Iterator[Match]:
    for m in _PHONE_RE.finditer(text):
        yield Match("TELEFOON", m.start(), m.end(), m.group())


def detect_iban(text: str) -> Iterator[Match]:
    for m in _IBAN_RE.finditer(text):
        yield Match("IBAN", m.start(), m.end(), m.group())


def detect_postcode(text: str) -> Iterator[Match]:
    for m in _POSTCODE_RE.finditer(text):
        yield Match("POSTCODE", m.start(), m.end(), m.group())


def detect_address(text: str) -> Iterator[Match]:
    for m in _ADDRESS_RE.finditer(text):
        yield Match("ADRES", m.start(), m.end(), m.group())


def detect_dob(text: str, *, all_dates: bool = False) -> Iterator[Match]:
    """Dates of birth.

    By default a date counts only when preceded by a birth-date cue
    ("geboren", "geboortedatum", "geb.") so consultation dates stay intact.
    ``all_dates=True`` masks every full date.
    """
    for regex in (_DATE_NUMERIC_RE, _DATE_TEXT_RE):
        for m in regex.finditer(text):
            before = text[max(0, m.start() - 24) : m.start()]
            if all_dates or _DOB_CONTEXT_RE.search(before):
                yield Match("GEBOORTEDATUM", m.start(), m.end(), m.group())


def _trim_particles(value: str) -> str:
    words = value.split()
    while words and words[-1].lower() in _PARTICLES:
        words.pop()
    return " ".join(words)


def detect_names(text: str, extra_names: Iterable[str] = ()) -> Iterator[Match]:
    """Person names, found through three cues:

    1. a title or role before the name (dhr., mevrouw, patiënt ...);
    2. an introduction phrase (ik ben, mijn naam is, u spreekt met ...);
    3. a known first name (built-in list plus ``extra_names``) followed by
       capitalised surname tokens.
    """
    known = _FIRST_NAMES | {n.lower() for n in extra_names}
    seen: set[tuple[int, int]] = set()

    for regex in (_TITLE_RE, _INTRO_RE):
        for m in regex.finditer(text):
            value = _trim_particles(m.group(1))
            if not value or value.lower() in _PARTICLES:
                continue
            span = (m.start(1), m.start(1) + len(value))
            if span not in seen:
                seen.add(span)
                yield Match("NAAM", span[0], span[1], value)

    for m in _NAME_TOKEN_RE.finditer(text):
        if m.group(1).lower() not in known:
            continue
        start, end = m.start(1), m.end(1)
        # extend over surname tokens: particles or capitalised words, max 4
        rest = text[end:]
        ext = re.match(rf"((?:\s{_NAME_WORD}){{0,4}})", rest)
        if ext:
            tail = ext.group(1)
            # drop trailing particles ("Anna van" -> "Anna")
            while tail and tail.split()[-1].lower() in _PARTICLES:
                tail = tail[: tail.rfind(" ")]
            end += len(tail)
        if any(s <= start < e or s < end <= e for s, e in seen):
            continue
        seen.add((start, end))
        yield Match("NAAM", start, end, text[start:end])


def default_detectors(
    *, extra_names: Iterable[str] = (), all_dates: bool = False
) -> list[Detector]:
    """The detectors ``PiiFilter`` runs by default, in priority order."""
    return [
        detect_bsn,
        detect_iban,
        detect_email,
        detect_phone,
        detect_address,
        detect_postcode,
        lambda t: detect_dob(t, all_dates=all_dates),
        lambda t: detect_names(t, extra_names=extra_names),
    ]
