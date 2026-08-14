"""Programmatic verification layer.

The model is never trusted on its own say-so. Every field it returns must come
with a verbatim quote from the source document; we then check that quote really
is in the document, and that the value it claims is actually supported by that
quote. Self-reported confidence is not used as a score -- it is well documented
that LLM verbalised confidence is poorly calibrated. Confidence here is
*computed* from three signals we can measure:

    g  grounding  -- does the evidence quote exist in the source document?
    d  presence   -- does the claimed VALUE itself appear in the source document?
    v  support    -- does the claimed value appear inside its own evidence?
    a  agreement  -- across k independent samples, how often is the value identical?

`d` is not redundant with `g`. A fabricated value smuggled inside a real-looking
quote ("Patient Name : <wrong name>") scores high on `g`, because the boilerplate
prefix carries the fuzzy match. Checking the value against the document directly
is what actually catches invention.

One asymmetry matters. For NAMED ENTITIES (names, diagnoses, drugs, allergens) a
value absent from the document is fabrication, full stop -- so `d` hard-gates.
For NUMERICS it is not: "37.6 degrees Celsius" correctly extracts as 99.7 F, and
"one hundred and twelve" correctly extracts as 112. Neither literal appears in
the text. Hard-gating numerics would punish the model for doing the conversion we
asked it to do, so there `d` only softens confidence. We recover most of these
anyway by matching spelled-out numbers and Celsius equivalents.

Anything failing the grounding gate is marked UNGROUNDED and withheld from the
summary card regardless of confidence. This is the difference between a demo
that looks right and one a clinician could sign off on.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schema import ExtractedField, FieldStatus

GROUNDING_GATE = 0.60      # below this the quote is treated as fabricated
ABSTAIN_BELOW = 0.70       # below this the field is routed to human review

W_GROUND, W_PRESENT, W_SUPPORT, W_AGREE = 0.30, 0.25, 0.15, 0.30


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def grounding_score(quote: str | None, document: str) -> float:
    """Fuzzy containment of `quote` in `document`, tolerant of OCR corruption."""
    if not quote:
        return 0.0
    q, d = _norm(quote), _norm(document)
    if not q:
        return 0.0
    if q in d:
        return 1.0
    # slide a window the length of the quote across the document and keep the best
    best, step = 0.0, max(1, len(q) // 4)
    for i in range(0, max(1, len(d) - len(q) + 1), step):
        r = SequenceMatcher(None, q, d[i:i + len(q)]).ratio()
        if r > best:
            best = r
            if best > 0.97:
                break
    return best


def support_score(value, quote: str | None) -> float:
    """Does the claimed value actually appear in the quote it cites?"""
    if value is None or not quote:
        return 0.0
    nq = _norm(quote)
    if isinstance(value, (list, tuple)):
        if not value:
            return 1.0  # empty list is supported by a negation quote e.g. "NKDA"
        hits = sum(1 for item in value if _tokens_in(item, nq))
        return hits / len(value)
    return 1.0 if _tokens_in(value, nq) else 0.4  # 0.4: may be a normalised form


def _tokens_in(value, nq: str, thresh: float = 0.6) -> bool:
    """Are the substantive tokens of `value` present in normalised text `nq`?

    `thresh` is deliberately different by caller. Checking a value against its own
    short quote tolerates partial overlap (0.6). Checking a value against the whole
    document does not -- there, anything less than near-total token coverage means
    text was added that the document does not contain.
    """
    if isinstance(value, dict):
        value = value.get("name", "")
    nv = _norm(value)
    if not nv:
        return False
    if nv in nq:
        return True
    toks = [t for t in nv.split() if len(t) > 2]
    return bool(toks) and sum(t in nq for t in toks) / len(toks) >= thresh


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _spell(n: int) -> str:
    n = int(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    rem = n % 100
    return _ONES[n // 100] + " hundred" + (" and " + _spell(rem) if rem else "")


def _numeric_present(value: float, document: str) -> float:
    """Digits, spelled-out words, or the Celsius equivalent of a Fahrenheit value."""
    if re.search(rf"(?<![\d.]){re.escape(f'{value:g}')}(?![\d])", document):
        return 1.0
    nd = _norm(document)
    if float(value).is_integer() and 0 <= value < 1000:
        if _spell(int(value)).replace("-", " ") in nd.replace("-", " "):
            return 1.0
    # temperature recorded in Celsius, extracted (correctly) in Fahrenheit
    if 90 <= value <= 110:
        c = round((value - 32) * 5 / 9, 1)
        if re.search(rf"(?<![\d.]){re.escape(f'{c:g}')}(?![\d])", document):
            return 1.0
    return 0.0


def is_numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def presence_score(value, document: str) -> float:
    """Does the value itself occur in the document, independent of its quote?"""
    if value is None:
        return 0.0
    nd = _norm(document)
    if isinstance(value, (list, tuple)):
        if not value:
            return 1.0
        return sum(1 for item in value if _tokens_in(item, nd, thresh=0.85)) / len(value)
    if is_numeric(value):
        return _numeric_present(value, document)
    return 1.0 if _tokens_in(value, nd, thresh=0.85) else 0.0


def agreement_score(samples: list) -> float:
    """Fraction of samples agreeing with the modal value."""
    if len(samples) <= 1:
        return 1.0
    keys = [_norm(repr(s)) for s in samples]
    return max(keys.count(k) for k in set(keys)) / len(keys)


def adjudicate(value, quote, document, samples=None) -> ExtractedField:
    """Turn a raw model claim into a scored, status-tagged field."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ExtractedField(value=None, evidence=quote, confidence=0.0,
                              status=FieldStatus.NOT_PRESENT)

    # An empty list is an ASSERTION ("no known allergies") only when a quote backs
    # it. With no quote, nothing was claimed -- the section simply is not in this
    # document type. Scoring it would manufacture a false review item.
    if isinstance(value, (list, tuple)) and len(value) == 0 and not quote:
        return ExtractedField(value=[], evidence=None, confidence=0.0,
                              status=FieldStatus.NOT_PRESENT)

    # List fields are filtered per item, not accepted or rejected wholesale. A
    # medication list that is 4/5 correct is not 80% safe -- the phantom fifth
    # entry is the whole risk. Unsupported entries are removed and the field is
    # routed to review, because a list that contained an invention is not a list
    # to trust the remainder of.
    dropped = 0
    if isinstance(value, (list, tuple)) and value:
        nd_all = _norm(document)
        kept = [it for it in value if _tokens_in(it, nd_all, thresh=0.85)]
        dropped = len(value) - len(kept)
        value = kept

    g = grounding_score(quote, document)
    d = presence_score(value, document)
    v = support_score(value, quote)
    a = agreement_score(samples or [value])
    conf = round(W_GROUND * g + W_PRESENT * d + W_SUPPORT * v + W_AGREE * a, 3)

    # Presence hard-gates named entities only; for numerics a legitimate converted
    # value may not appear literally, so a low `d` just costs confidence.
    fabricated = g < GROUNDING_GATE or (d < GROUNDING_GATE and not is_numeric(value))
    if fabricated:
        status = FieldStatus.UNGROUNDED          # the quote or the value is not in the document
    elif dropped:
        status = FieldStatus.ABSTAINED           # invention detected inside the list
    elif conf < ABSTAIN_BELOW:
        status = FieldStatus.ABSTAINED
    else:
        status = FieldStatus.EXTRACTED

    return ExtractedField(value=value, evidence=quote, confidence=conf,
                          status=status, agreement=round(a, 3), dropped_items=dropped)
