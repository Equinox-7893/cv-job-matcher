"""Remove personal details from CV text before it is scored.

This is version 1 of the privacy step described in docs/privacy-step.md.
It uses only the Python standard library, so it runs anywhere (including
Google Colab) without downloading models. An optional spaCy pass can be
switched on to catch person names the rules miss.

Usage:
    from cv_matcher.privacy import redact
    result = redact(cv_text)
    result.text        # redacted text, safe to send to the scorer
    result.log_record  # counts only, safe to write to logs
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

REDACTOR_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
)
YEAR = r"(?:19[5-9]\d|20[0-4]\d)"
MONTH_YEAR = rf"(?:{MONTHS}\.?\s+)?(?P<{{g}}>{YEAR})"
RANGE_END = r"(?:present|current|now|today|ongoing)"

# "Sep 2019 - Jun 2022", "2020 to present". Turned into a duration.
DATE_RANGE = re.compile(
    rf"\b{MONTH_YEAR.format(g='start')}\s*(?:-|–|—|to|until)\s*"
    rf"(?:{MONTH_YEAR.format(g='end')}|(?P<open>{RANGE_END}))\b",
    re.IGNORECASE,
)

# Lines like "Date of birth: 03/04/1998" or "Nationality: Indian".
# The whole value after the colon is removed.
SENSITIVE_FIELDS = {
    "DATE_OF_BIRTH": r"date\s+of\s+birth|d\.?o\.?b\.?|born",
    "AGE": r"age",
    "GENDER": r"gender|sex",
    "NATIONALITY": r"nationality|citizenship",
    "MARITAL_STATUS": r"marital\s+status|relationship\s+status",
    "RELIGION": r"religion|faith|beliefs?",
    "HEALTH": r"health|disability|disabilities|medical\s+conditions?",
    "DEPENDANTS": r"dependants|dependents|children",
    "ADDRESS": r"(?:home\s+)?address",
    "NAME": r"(?:full\s+)?name",
    "VISA": r"visa(?:\s+status)?|right\s+to\s+work|immigration\s+status",
}
FIELD_LINE = re.compile(
    r"^[ \t]*(?P<label>"
    + "|".join(f"(?P<{k}>{v})" for k, v in SENSITIVE_FIELDS.items())
    + r")[ \t]*[:\-–][ \t]*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)

POSTCODE_RE = r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"

SIMPLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    (
        "URL",
        re.compile(
            r"\b(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com|"
            r"gitlab\.com|twitter\.com|x\.com)/\S+",
            re.IGNORECASE,
        ),
    ),
    # UK phone numbers: +44 7700 900123, 07700 900123, (020) 7946 0958
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+44\s?\(?0?\)?\s?|\(?0)\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}\b"
        ),
    ),
    # UK National Insurance number, e.g. QQ 12 34 56 C
    (
        "NI_NUMBER",
        re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.I),
    ),
    # UK postcode, e.g. SW1A 1AA, M1 1AE
    (
        "POSTCODE",
        re.compile(POSTCODE_RE),
    ),
    # Full dates: 03/04/1998, 3-4-98, 3 April 1998
    (
        "DATE",
        re.compile(
            rf"\b\d{{1,2}}[/.-]\d{{1,2}}[/.-](?:\d{{4}}|\d{{2}})\b|"
            rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\s+{YEAR}\b",
            re.IGNORECASE,
        ),
    ),
    # "aged 34", "34 years old", "age 34"
    (
        "AGE",
        re.compile(
            r"\b(?:aged?\s+\d{2}|\d{2}\s*(?:years?|yrs?)[\s-]*old)\b", re.IGNORECASE
        ),
    ),
    # Titles that show gender
    ("TITLE", re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Sir|Dame)\b\.?")),
    # Gendered pronouns (mostly in references or personal statements)
    (
        "PRONOUN",
        re.compile(r"\b(?:he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE),
    ),
    # Lone years left after date ranges are handled, e.g. "Graduated 2015"
    ("YEAR", re.compile(rf"\b{YEAR}\b")),
]

# Words that point to a protected characteristic when they appear in
# societies, clubs, schools or volunteering. This list is a starting point,
# not a complete one. See docs/privacy-step.md, section "Proxies".
PROXY_TERMS = [
    # religion or belief
    "islamic", "muslim", "christian", "catholic", "jewish", "hindu", "sikh",
    "buddhist", "church", "mosque", "synagogue", "temple", "gurdwara",
    "chaplaincy", "c of e",
    # sex, gender reassignment, sexual orientation
    "women in", "women's", "womens", "girls'", "boys'", "ladies", "men's",
    "lgbt", "lgbtq", "lgbtq+", "pride society", "gay", "lesbian", "transgender", "non-binary",
    # race, ethnicity, nationality
    "african", "caribbean", "asian", "indian", "pakistani", "bangladeshi",
    "chinese", "polish", "nigerian", "afro-caribbean",
    # pregnancy, maternity, family
    "maternity", "paternity", "parental leave", "career break to care",
    # disability and health
    "disabled", "disability", "dyslexia", "dyslexic", "autism", "autistic",
    "adhd", "wheelchair", "mental health condition",
    # age
    "retired", "school leaver", "mature student",
]
PROXY_LINE = re.compile(
    # (?<!\w) and (?!\w) stop "church" matching inside "Churchill".
    r"^.*(?<!\w)(?:" + "|".join(re.escape(t) for t in PROXY_TERMS) + r")(?!\w).*$",
    re.IGNORECASE | re.MULTILINE,
)

# A UK postcode anywhere on a line. The whole line is treated as an address,
# so street names and towns go too.
ADDRESS_LINE = re.compile(rf"^.*{POSTCODE_RE}.*$", re.MULTILINE)

# Referees are other people's personal data and say nothing about skills.
# The heading and everything up to the next blank line is removed.
REFEREES_BLOCK = re.compile(
    r"^[ \t]*(?:referees?|references?)[ \t]*:?[ \t]*\n(?:[ \t]*\S.*(?:\n|$))*",
    re.IGNORECASE | re.MULTILINE,
)

# Languages. Om's decision: the scorer sees how many languages a person
# knows, not which ones, because the names can point to ethnic or national
# origin. Works for "Languages: English, Tamil" and for a "Languages"
# heading followed by one language per line.
LANGUAGES_LINE = re.compile(
    r"^[ \t]*languages?(?:[ \t]+spoken)?[ \t]*:[ \t]*(?P<value>\S.*)$",
    re.IGNORECASE | re.MULTILINE,
)
LANGUAGES_BLOCK = re.compile(
    r"^[ \t]*languages?(?:[ \t]+spoken)?[ \t]*\n(?P<value>(?:[ \t]*\S.*(?:\n|$))+)",
    re.IGNORECASE | re.MULTILINE,
)
LANGUAGE_LEVEL_WORDS = re.compile(
    r"\s*[(\[]?\b(?:native(?:\s+speaker)?|mother\s+tongue|first\s+language|"
    r"bilingual)\b[)\]]?",
    re.IGNORECASE,
)

# A header line that looks like a person's name: 2 to 4 capitalised words,
# no digits, nothing else on the line.
NAME_LINE = re.compile(
    r"^[ \t]*(?P<name>[A-Z][a-zA-Z'’-]+(?:[ \t]+[A-Z][a-zA-Z'’-]+){1,3})[ \t]*$"
)

# Section headings that look like names but are not.
NOT_A_NAME = {
    "curriculum vitae", "personal statement", "work experience", "key skills",
    "technical skills", "professional summary", "contact details",
    "interests and hobbies", "education and training", "career history",
    "further information", "personal profile",
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Span:
    start: int
    end: int
    label: str
    replacement: str


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)
    version: str = REDACTOR_VERSION
    # Profile and portfolio links taken out of the scorer's text. The
    # recruiter sees them at the review stage. Never logged.
    recruiter_only_links: list[str] = field(default_factory=list)

    @property
    def log_record(self) -> dict:
        """What may be written to logs. Counts and version only.

        Never put the original text, the removed values, or hashes of
        them in here. See docs/privacy-step.md, section "Logging".
        """
        return {
            "redactor_version": self.version,
            "removed_counts": dict(sorted(self.counts.items())),
            "total_removed": sum(self.counts.values()),
        }


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def redact(
    text: str,
    *,
    today: date | None = None,
    remove_proxy_lines: bool = True,
    use_spacy: bool = False,
    keep_language_names: bool = False,
) -> RedactionResult:
    """Return CV text with personal details replaced by placeholders.

    today: used to work out "2020 - present" durations. Defaults to now.
    remove_proxy_lines: drop whole lines that mention a protected
        characteristic (for example a faith society or "maternity leave").
    use_spacy: also run spaCy's named entity recogniser for PERSON names.
        Needs `pip install spacy` and `python -m spacy download en_core_web_sm`.
    keep_language_names: keep which languages a person speaks (only words
        like "native" are dropped). Use this only when the job advert needs a
        specific language, for example a Welsh-speaking post.
    """
    today = today or date.today()
    spans: list[Span] = []

    # 1. Whole "Label: value" lines for sensitive fields.
    for m in FIELD_LINE.finditer(text):
        label = next(k for k in SENSITIVE_FIELDS if m.group(k))
        spans.append(Span(m.start("value"), m.end("value"), label, f"[{label}]"))

    # 1b. Address lines and the referees section.
    for m in ADDRESS_LINE.finditer(text):
        spans.append(Span(m.start(), m.end(), "ADDRESS", "[ADDRESS]"))
    for m in REFEREES_BLOCK.finditer(text):
        spans.append(
            Span(m.start(), m.end(), "REFEREES", "[REFEREES REMOVED]\n")
        )
    # Start positions of "Label: value" lines, so the proxy rule below
    # leaves them to the more specific field label.
    field_lines = {
        text.rfind("\n", 0, sp.start) + 1
        for sp in spans
        if sp.label in SENSITIVE_FIELDS
    }

    # 1c. Languages become a count (or keep names, without "native").
    for pattern in (LANGUAGES_BLOCK, LANGUAGES_LINE):
        for m in pattern.finditer(text):
            value = m.group("value")
            trailing_nl = "\n" if value.endswith("\n") else ""
            if keep_language_names:
                new = LANGUAGE_LEVEL_WORDS.sub("", value)
            else:
                new = f"[{_count_languages(value)} languages]{trailing_nl}"
            spans.append(Span(m.start("value"), m.end("value"), "LANGUAGES", new))

    # 2. Name in the header, then every later mention of the same words.
    name_tokens = _find_header_name(text)
    if use_spacy:
        name_tokens |= _spacy_person_tokens(text)
    for token in name_tokens:
        for m in re.finditer(rf"\b{re.escape(token)}\b", text):
            spans.append(Span(m.start(), m.end(), "NAME", "[CANDIDATE]"))

    # 3. Lines that act as proxies for protected characteristics.
    if remove_proxy_lines:
        for m in PROXY_LINE.finditer(text):
            if m.group().strip() and m.start() not in field_lines:
                spans.append(Span(m.start(), m.end(), "PROXY", "[REMOVED: PROXY]"))

    # 4. Date ranges become durations so experience still counts.
    for m in DATE_RANGE.finditer(text):
        start_y = int(m.group("start"))
        end_y = today.year if m.group("open") else int(m.group("end"))
        years = max(end_y - start_y, 0)
        dur = "under 1 year" if years == 0 else f"{years} year{'s' * (years != 1)}"
        spans.append(Span(m.start(), m.end(), "DATE_RANGE", f"[{dur}]"))

    # 5. Simple patterns.
    for label, pattern in SIMPLE_PATTERNS:
        for m in pattern.finditer(text):
            spans.append(Span(m.start(), m.end(), label, f"[{label}]"))

    kept = _resolve_overlaps(spans)
    links = [text[s.start : s.end] for s in kept if s.label == "URL"]
    return RedactionResult(
        text=_apply(text, kept), counts=_count(kept), recruiter_only_links=links
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_header_name(text: str, max_lines: int = 5) -> set[str]:
    """Guess the candidate's name from the first few non-empty lines."""
    lines = [ln for ln in text.splitlines() if ln.strip()][:max_lines]
    for line in lines:
        m = NAME_LINE.match(line)
        if m and m.group("name").lower() not in NOT_A_NAME:
            # Each word on its own, so "Priya" alone is caught later on.
            return {w for w in m.group("name").split() if len(w) > 1}
    return set()


def _count_languages(value: str) -> int:
    """Count items in "English (fluent), Tamil; French" or a bullet list."""
    items = re.split(r"[,;/\n]|\band\b", value)
    names = set()
    for item in items:
        item = re.sub(r"[(\[].*?[)\]]", "", item)      # drop "(fluent)"
        item = re.sub(r"^[\s\-*•–]+", "", item).strip()  # drop bullets
        item = re.split(r"\s*[-–:]\s*", item)[0]        # "French - basic"
        if item:
            names.add(item.split()[0].lower())
    return len(names)


def _spacy_person_tokens(text: str) -> set[str]:
    try:
        import spacy  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "use_spacy=True needs spaCy: pip install spacy && "
            "python -m spacy download en_core_web_sm"
        ) from exc
    nlp = spacy.load("en_core_web_sm")
    tokens: set[str] = set()
    for ent in nlp(text).ents:
        if ent.label_ == "PERSON":
            tokens |= {w for w in ent.text.split() if len(w) > 1 and w[0].isupper()}
    return tokens


def _resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Keep the longest span where spans overlap. Earlier rules win ties."""
    order = sorted(
        enumerate(spans), key=lambda p: (-(p[1].end - p[1].start), p[0])
    )
    kept: list[Span] = []
    for _, s in order:
        if all(s.end <= k.start or s.start >= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)


def _apply(text: str, spans: list[Span]) -> str:
    out, pos = [], 0
    for s in spans:
        out.append(text[pos : s.start])
        out.append(s.replacement)
        pos = s.end
    out.append(text[pos:])
    return "".join(out)


def _count(spans: list[Span]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in spans:
        counts[s.label] = counts.get(s.label, 0) + 1
    return counts


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m cv_matcher.privacy.redactor <cv.txt>")
    with open(sys.argv[1], encoding="utf-8") as f:
        result = redact(f.read())
    print(result.text)
    print(json.dumps(result.log_record, indent=2), file=sys.stderr)
