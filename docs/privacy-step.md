# Privacy step: removing personal details before scoring

Status: first version (v0.1). Items marked **[Guess]** are my assumptions and need checking. Items marked **[Decision for Om]** are open choices.

## Why this step exists

The scorer should only see what someone can do, not who they are. If the model never sees a name, a date of birth or a faith society, it cannot score on them, even by accident. This supports three things the tool has to get right:

- **Equality Act 2010.** An employer must not treat candidates less favourably because of a protected characteristic: age, disability, gender reassignment, marriage and civil partnership, pregnancy and maternity, race (which includes colour, nationality and ethnic or national origin), religion or belief, sex, and sexual orientation. Indirect discrimination also counts, which is why proxies matter (see below).
- **UK GDPR data minimisation** (Article 5(1)(c)). Each part of the system should handle only the personal data it needs. The scorer does not need contact details.
- **ICO guidance on AI in recruitment.** The ICO has published recommendations for recruiters and AI providers, including collecting only the data needed and checking tools for bias. **[Guess]** I have not checked the current wording of the ICO pages. Om should link the exact pages from the README.

One point to be clear about in the README: **redacted CVs are still personal data.** The organisation running the tool can link a redacted CV back to the person through the candidate ID, so this is pseudonymisation, not anonymisation. UK GDPR still applies to it. The redaction step lowers the risk, it does not remove the legal duties.

## Where it sits in the pipeline

```
 CV file (PDF/DOCX)
      │
      ▼
 1. Text extraction ──► raw text          (restricted store, short retention)
      │
      ▼
 2. Redaction  ◄── this document
      │
      ├──► redacted text  ──► 3. Skill extraction (LLM) ──► 4. Embeddings ──► 5. Scoring + reasons
      │                                                                              │
      └──► log record (counts only)                                                  ▼
                                                                         6. Recruiter review
                                                                            (sees scores and reasons,
                                                                             then the full CV for the
                                                                             shortlist only)
```

Rules:

1. Redaction runs **before** anything that scores, embeds or sends text to an LLM. Nothing downstream ever reads the raw text.
2. Photos and images are dropped at text extraction. Only text goes forward.
3. Each CV gets a random candidate ID (for example `uuid4()`), not one built from the name or email.
4. The link between candidate ID and the original file lives only in the restricted store. The recruiter uses it after scoring, at the human decision stage.
5. The human makes the final decision. The tool ranks and explains. It does not reject anyone on its own. This matters for UK GDPR rules on solely automated decisions (Article 22). **[Guess]** The Data (Use and Access) Act 2025 changed these rules. The README should check the current position rather than rely on my summary.

## What gets removed

### Direct identifiers

| What | How it is found | Replaced with |
|---|---|---|
| Name | First lines of the CV, then every later use of the same words. Optional spaCy NER for names elsewhere. | `[CANDIDATE]` |
| Email | Regex | `[EMAIL]` |
| Phone (UK formats) | Regex | `[PHONE]` |
| Home address | Any line holding a UK postcode, plus `Address:` lines | `[ADDRESS]` |
| Profile links (LinkedIn, GitHub, personal sites) | Regex | `[URL]` |
| National Insurance number | Regex | `[NI_NUMBER]` |
| Photo | Dropped at text extraction | nothing |
| Referees | Whole "References" / "Referees" section | `[REFEREES REMOVED]` |

Referees are removed because they are other people's personal data and they say nothing about the candidate's skills.

### Protected characteristics stated directly

| What | Example | Replaced with |
|---|---|---|
| Date of birth, age | `Date of birth: 03/04/1998`, `27 years old` | `[DATE_OF_BIRTH]`, `[AGE]` |
| Gender | `Gender: Female`, titles `Mr/Mrs/Ms/Miss/Mx`, pronouns `he/she/his/her` | `[GENDER]`, `[TITLE]`, `[PRONOUN]` |
| Nationality | `Nationality: Indian` | `[NATIONALITY]` |
| Marital status, dependants | `Marital status: Married` | `[MARITAL_STATUS]` |
| Religion | `Religion: ...` | `[RELIGION]` |
| Health, disability | `Health: ...` | `[HEALTH]` |
| Visa or right to work | `Visa status: Tier 2` | `[VISA]` |

Right to work is a real requirement for UK employers, but it is a yes/no check the recruiter does separately. It should not change a skills score.

### Proxies

A proxy is a detail that is not a protected characteristic itself but points strongly to one. The model can learn these patterns even when the obvious fields are gone.

| Proxy | What it can reveal | What v0.1 does |
|---|---|---|
| Graduation and school years | Age | Lone years become `[YEAR]` |
| Job date ranges | Age (indirectly) | `Sep 2021 - present` becomes `[5 years]` |
| Faith schools, faith societies | Religion | Line removed if it contains a term from the proxy list |
| Women's or LGBTQ+ groups | Sex, sexual orientation | Line removed |
| Ethnic or national societies | Race | Line removed |
| Maternity leave, career breaks to care | Pregnancy and maternity, sex | Line removed |
| Disability or health mentions | Disability | Line removed |
| `mature student`, `retired`, `school leaver` | Age | Line removed |

The proxy list is in `PROXY_TERMS` in `src/cv_matcher/privacy/redactor.py`. Terms only match as whole words, so `church` does not hit `Churchill`. I left out `black` because it would remove lines like "black-box testing". That is a known gap.

Years of experience are kept as durations on purpose. Some jobs genuinely need experience, and the scorer needs it. But total experience still correlates with age. If the job advert asks for experience, the scoring should cap it (for example "3+ years" scores the same for 3 or 20 years) and the README should say why. This belongs in the scoring design, so I have only flagged it here.

### Open decisions

- **[Decision for Om] University names.** A university's name can act as a proxy for social background and, through international universities, for nationality. My suggestion: keep degree subject and class (they are relevant), and replace the institution with `[UNIVERSITY]` by default, with a setting to keep it. Not done in v0.1.
- **[Decision for Om] Languages.** "Fluent Polish" may be a job skill, but "native Urdu speaker" points to ethnic origin. My suggestion: keep languages as skills and drop the words "native" and "mother tongue". Not done in v0.1.
- **[Decision for Om] GitHub and portfolio links.** They are evidence of skill, but they identify the person. My suggestion: remove them from the scorer's text and show them to the recruiter at the review stage.
- **Locations of past jobs.** "Data Analyst, Lagos" can point to nationality. v0.1 does not remove place names outside addresses. The optional NER pass could do this.

## Tools

The v0.1 prototype uses **only regex and the Python standard library.** It runs in Colab with no downloads and is easy to test and explain. That makes it a sensible base layer. It will miss things, so the plan is to add layers:

| Layer | Tool | Good at | Weak at | In v0.1? |
|---|---|---|---|---|
| 1 | Regex rules | Emails, phones, postcodes, NI numbers, dates, labelled fields | Names in free text, anything without a fixed shape | Yes |
| 2 | spaCy NER (`en_core_web_sm`, or `en_core_web_trf` for better accuracy) | Person names, places, organisations in free text | Over-redacts some tech names. Needs a model download. | Optional (`use_spacy=True`) |
| 3 | Microsoft Presidio | Combines regex and NER, has a framework for custom recognisers, handles overlaps, and can anonymise as well as detect | Heavier install. Its built-in recognisers are mostly US-focused, so the UK rules from layer 1 would be added as custom recognisers. **[Guess]** Check its current UK recogniser list. | No, planned |
| 4 | LLM check | Catching odd cases that rules miss, such as "I came back to work after my son was born" | Can make things up, costs money, and sending raw CVs to a third-party API means sharing personal data with that provider | No, planned |

For the LLM layer, my suggestion is to run it **only on already-redacted text**, as a second check that flags anything that still looks personal, rather than giving it the raw CV. A local model (for example through Ollama) avoids sending data out at all. If a hosted API is used, the README should say who the provider is and that this is a data sharing decision for the organisation.

**[Guess]** For a portfolio project, layers 1 and 2 are enough to show the idea. Presidio is worth adding if time allows, because recruiters for data roles may recognise it.

## How to test that removal worked

All test data is synthetic. No real CV goes in the repo.

1. **Planted-detail tests (leak tests).** Write fake CVs with known personal details planted in them, then check that none of those exact strings appear in the output. `tests/test_redactor.py` does this for one CV with 24 planted items. Next step: generate a few hundred CVs with [Faker](https://faker.readthedocs.io/) using the `en_GB` locale, so names, phones and postcodes vary.
2. **Over-redaction tests.** Check that job-relevant words survive: `Python`, `SQL`, `Power BI`, `BSc Mathematics` and so on. A redactor that deletes everything would pass the leak tests and be useless.
3. **Counterfactual test.** Take one CV and change only the identity details (name, date of birth, nationality, marital status). The redacted text should be identical. If it is, the scorer cannot tell those candidates apart on those details. This test is in the suite and passes. Later, the same idea applies to the whole pipeline: the final score should not change.
4. **Metrics for the report.** On the larger synthetic set, measure per entity type:
   - *Recall* (leak rate): of the planted details, how many were removed. The target for direct identifiers (name, email, phone, address) should be 100% on the test set, and any miss is a bug.
   - *Precision*: of the things removed, how many were really personal. This shows over-redaction.
5. **Manual review.** Read 20 redacted CVs by eye before trusting the numbers. Regex tests only check what you thought to test.

Run the tests with:

```bash
pip install pytest
python -m pytest
```

## Logging without storing personal data

The rule: **logs hold counts and versions, never CV text or removed values.**

`RedactionResult.log_record` returns only this:

```json
{
  "redactor_version": "0.1.0",
  "removed_counts": {"EMAIL": 1, "NAME": 3, "PHONE": 1, "PROXY": 4},
  "total_removed": 20
}
```

The pipeline adds the candidate ID and a timestamp when it writes the record. Other rules:

- Do not log hashes of names or emails. A hash of an email can be matched back to the email, so it is still personal data.
- Do not keep a table of "placeholder → original value". If the recruiter needs the original, they open the original file at the review stage.
- Do not print raw text in error messages. Log the candidate ID and the error type.
- Raw CV text and files get a retention period (for example deleted 6 months after the role is filled). **[Guess]** The right period depends on the organisation's policy. The README should say it is configurable and give the example as an example.
- The `total_removed` count is useful as a warning sign: a CV with 0 items removed probably means extraction failed or the format is unusual, and it should be checked by a person.

## Known limits of v0.1

- Names are only found reliably in the header. A name that appears only in the body is missed unless `use_spacy=True`.
- Two-word headings that are not in the `NOT_A_NAME` list could be treated as a name. This over-redacts but does not leak.
- Proxy detection is a word list. It will miss proxies phrased in other ways.
- Only UK phone, postcode and NI formats are covered.
- Lone years are all removed, including in project names like "Advent of Code 2023". That is acceptable over-redaction.
- English only.

## Files

- `src/cv_matcher/privacy/redactor.py`: the prototype
- `tests/test_redactor.py`: the tests
- `tests/fixtures/synthetic_cv_01.txt`: a made-up CV with planted details

This document describes the design and is not legal advice. The README should say the same.
