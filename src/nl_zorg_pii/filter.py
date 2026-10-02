"""PiiFilter: mask personal data before an LLM call, restore it afterwards."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from nl_zorg_pii.detectors import Detector, Match, default_detectors

_PLACEHOLDER_RE = re.compile(
    r"\[(BSN|EMAIL|TELEFOON|IBAN|POSTCODE|ADRES|GEBOORTEDATUM|NAAM)_(\d+)\]"
)


@dataclass
class MaskResult:
    """Outcome of ``PiiFilter.mask``.

    ``text`` is safe to send onward. ``mapping`` maps each placeholder back to
    the original value and must stay on your side (never in the prompt).
    """

    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.matches)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for m in self.matches:
            out[m.kind] = out.get(m.kind, 0) + 1
        return dict(sorted(out.items()))


class PiiFilter:
    """Mask and restore Dutch personal data in free text.

    Example::

        f = PiiFilter()
        masked = f.mask("Patiënt Jan de Vries, BSN 111222333, belt over hoofdpijn.")
        masked.text      # 'Patiënt [NAAM_1], BSN [BSN_1], belt over hoofdpijn.'
        reply = llm(masked.text)
        f.restore(reply, masked.mapping)

    The same value always gets the same placeholder within one ``mask`` call,
    so an LLM can refer to ``[NAAM_1]`` consistently and ``restore`` puts the
    real name back wherever it appears in the reply.
    """

    def __init__(
        self,
        detectors: Iterable[Detector] | None = None,
        *,
        extra_names: Iterable[str] = (),
        all_dates: bool = False,
        kinds: Iterable[str] | None = None,
    ) -> None:
        self.detectors = (
            list(detectors)
            if detectors is not None
            else default_detectors(extra_names=extra_names, all_dates=all_dates)
        )
        self.kinds = set(kinds) if kinds else None

    def find(self, text: str) -> list[Match]:
        """All non-overlapping matches, earlier detectors winning on overlap."""
        found: list[Match] = []
        for detector in self.detectors:
            for m in detector(text):
                if self.kinds and m.kind not in self.kinds:
                    continue
                if any(m.start < f.end and f.start < m.end for f in found):
                    continue
                found.append(m)
        return sorted(found, key=lambda m: m.start)

    def mask(self, text: str) -> MaskResult:
        matches = self.find(text)
        mapping: dict[str, str] = {}
        value_to_placeholder: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        pieces: list[str] = []
        cursor = 0
        for m in matches:
            key = (m.kind, _normalise(m.value))
            placeholder = value_to_placeholder.get(key)
            if placeholder is None:
                counters[m.kind] = counters.get(m.kind, 0) + 1
                placeholder = f"[{m.kind}_{counters[m.kind]}]"
                value_to_placeholder[key] = placeholder
                mapping[placeholder] = m.value
            pieces.append(text[cursor : m.start])
            pieces.append(placeholder)
            cursor = m.end
        pieces.append(text[cursor:])
        return MaskResult("".join(pieces), mapping, matches)

    def redact(self, text: str, token: str | None = None) -> str:
        """Irreversibly replace personal data; ``token`` overrides the per-kind label."""
        result = self.mask(text)
        if token is None:
            return _PLACEHOLDER_RE.sub(lambda m: f"[{m.group(1)}]", result.text)
        return _PLACEHOLDER_RE.sub(token, result.text)

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> str:
        """Put original values back for every placeholder present in ``mapping``."""
        return _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def _normalise(value: str) -> str:
    return re.sub(r"[\s.\-]", "", value).lower()
