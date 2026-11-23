"""Tests for the privacy step. All CV text here is made up.

Run with:  python -m pytest
"""

from datetime import date
from pathlib import Path

import pytest

from cv_matcher.privacy import redact

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 23)


@pytest.fixture
def cv_text() -> str:
    return (FIXTURES / "synthetic_cv_01.txt").read_text(encoding="utf-8")


@pytest.fixture
def redacted(cv_text):
    return redact(cv_text, today=TODAY)


# Every planted personal detail in synthetic_cv_01.txt. If any of these
# strings is still in the output, the test fails and names it.
PLANTED = [
    "Priya", "Raman",                          # name
    "priya.raman.test@example.com",            # email
    "07700 900123", "+44 20 7946 0958",        # phones
    "linkedin.com/in/priya-raman-test",        # profile link
    "priya-raman-test.example.dev",            # portfolio link
    "Tamil", "French", "native",               # language names (origin proxy)
    "12 Example Road", "Leeds", "LS1 4AP",     # address
    "03/04/1998", "27 years old",              # date of birth, age
    "Indian", "Married",                       # nationality, marital status
    "QQ 12 34 56 C",                           # NI number
    "2019", "2016", "2021",                    # years (age proxies)
    "Maternity",                               # pregnancy and maternity
    "Catholic", "Islamic Society",             # religion proxies
    "Women in Data",                           # sex proxy
    "John Smith", "Mr ", " He ",               # referee and gender markers
]


@pytest.mark.parametrize("value", PLANTED)
def test_planted_detail_is_removed(redacted, value):
    assert value not in redacted.text


# Things the scorer needs. Removing these would be over-redaction.
MUST_SURVIVE = [
    "Python", "pandas", "SQL", "PostgreSQL", "Power BI", "Excel", "VBA",
    "Data Analyst", "BSc Mathematics", "dashboards",
]


@pytest.mark.parametrize("value", MUST_SURVIVE)
def test_job_relevant_content_is_kept(redacted, value):
    assert value in redacted.text


def test_date_ranges_become_durations(redacted):
    assert "[5 years]" in redacted.text   # Sep 2021 - present, in 2026
    assert "[2 years]" in redacted.text   # Jun 2019 - Aug 2021


def test_log_record_has_no_personal_data(cv_text, redacted):
    record = str(redacted.log_record)
    for value in PLANTED:
        assert value.strip() not in record
    assert set(redacted.log_record) == {
        "redactor_version", "removed_counts", "total_removed",
    }


def test_same_cv_different_identity_gives_same_output(cv_text):
    """Counterfactual check: change only who the person is.

    If the redacted text is identical, the scorer cannot treat these two
    candidates differently because of name, sex, age or nationality.
    """
    other = (
        cv_text.replace("Priya Raman", "Tomasz Kowalski")
        .replace("Priya", "Tomasz")
        .replace("priya.raman.test", "t.kowalski.test")
        .replace("priya-raman-test", "tomasz-k-test")
        .replace("03/04/1998", "17/11/1971")
        .replace("27 years old", "55 years old")
        .replace("Indian", "Polish")
        .replace("Married", "Single")
    )
    assert other != cv_text
    assert redact(other, today=TODAY).text == redact(cv_text, today=TODAY).text


def test_heading_is_not_mistaken_for_a_name():
    result = redact("Curriculum Vitae\nAlex Morgan\nSkills: Python")
    assert "Curriculum Vitae" in result.text
    assert "Alex" not in result.text and "Morgan" not in result.text


def test_proxy_lines_can_be_kept_when_switched_off(cv_text):
    result = redact(cv_text, today=TODAY, remove_proxy_lines=False)
    assert "Islamic Society" in result.text


@pytest.mark.parametrize(
    "phone",
    ["07700 900123", "07700900123", "+44 7700 900123", "(020) 7946 0958"],
)
def test_uk_phone_formats(phone):
    assert phone not in redact(f"Call me on {phone} any time").text


@pytest.mark.parametrize("postcode", ["SW1A 1AA", "M1 1AE", "B33 8TH", "CR2 6XH"])
def test_uk_postcodes(postcode):
    assert postcode not in redact(f"Flat 2, 5 High Street, {postcode}").text


@pytest.mark.parametrize(
    "line",
    [
        "Studied at Churchill College",          # not "church"
        "Built black-box tests for an API",      # "black" is not in the list
        "Polished the front end in React",       # not "polish"
        "Trained transformers with PyTorch",     # not "trans"
    ],
)
def test_proxy_rule_does_not_hit_ordinary_words(line):
    assert line in redact(line).text


def test_languages_become_a_count(redacted):
    assert "Languages: [3 languages]" in redacted.text


def test_language_count_from_bullet_list():
    text = "Languages\n- Welsh (first language)\n- English\n- Spanish - basic\n"
    assert redact(text).text == "Languages\n[3 languages]\n"


def test_language_names_kept_when_job_needs_them():
    text = "Languages: Welsh (first language), English"
    out = redact(text, keep_language_names=True).text
    assert "Welsh" in out and "English" in out
    assert "first language" not in out


def test_links_go_to_recruiter_not_scorer_or_logs(redacted):
    assert redacted.recruiter_only_links == [
        "linkedin.com/in/priya-raman-test",
        "https://priya-raman-test.example.dev",
    ]
    for link in redacted.recruiter_only_links:
        assert link not in redacted.text
        assert link not in str(redacted.log_record)
