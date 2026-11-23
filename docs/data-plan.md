# Data plan (version 1)

This document says what data the CV matcher uses, where it comes from, what we are allowed to publish, and how we build a labelled test set to measure the ranking.

Status: first draft, 23 November 2026. Items marked **[check]** still need confirming. Items marked **[question for Om]** need a decision.

## 1. The rule that drives everything

This repository is public. Anything committed here can be copied by anyone, forever, even if it is deleted later. So the plan follows one rule:

> Only commit data that we created ourselves, or data whose licence clearly allows redistribution and that contains no real person's personal data.

Everything else is downloaded by a script onto the user's own machine (or Colab) and kept out of Git by `.gitignore`.

This also matters for the legal story in the README. Under UK GDPR, even "anonymised" CVs scraped from the web can still identify someone (a rare job history plus a town is often enough). Using synthetic CVs for anything we publish avoids that question.

## 2. What data we need

| Need | Used for | Must be public in the repo? |
|---|---|---|
| CVs | Skill extraction, ranking | A small demo set, yes |
| Job adverts | The thing CVs are ranked against | A small demo set, yes |
| Skills taxonomy | A fixed list of skill names so "Python 3" and "python programming" count as the same skill | No, downloaded by script |
| Relevance labels (CV, job, score) | Evaluating the ranking | Yes, for the synthetic set |
| Fake personal details inside CVs | Testing that the anonymiser removes them | Yes, because they are invented |

## 3. Candidate datasets

I checked each of these on 23 November 2026. "Real people?" means whether the records come from real people's CVs.

### 3.1 CVs

| Dataset | What it is | Licence | Real people? | Verdict |
|---|---|---|---|---|
| [CareerCorpus](https://data.mendeley.com/datasets/wzzwn37gmd/1) (Mendeley Data, Dec 2025) | 302 annotated resumes in 6 job families (Teacher, Finance, Apparel, Accountant, Banking, Research Assistant), one .xlsx | CC BY 4.0 | Yes. Taken from LiveCareer resumes on Kaggle and public LinkedIn profiles. Names, emails and phones replaced with placeholders | Good for **local** experiments and for reporting results. Do not commit the file: the licence allows it, but the text still comes from real people, some via LinkedIn |
| Kaggle "Resume Dataset" (snehaanbhawal), mirrored on [Hugging Face](https://huggingface.co/datasets/Divyaamith/Kaggle-Resume) | About 2,484 resumes from livecareer.com, 24 categories, text and HTML | **None stated** on the mirror. **[check]** the Kaggle page itself | Unclear. They look like resume examples from a template site | Local use only, if at all. Widely used in student projects, so recruiters will recognise it, but the licence is unknown |
| [resume-job-description-fit](https://huggingface.co/datasets/cnamuangtoun/resume-job-description-fit) (Hugging Face) | About 8,000 resume and job description pairs labelled with fit classes ("No Fit" and others) | **None stated**, no dataset card | Probably scraped: real employer names appear | Useful idea for labels, but no licence. Do not commit. Local evaluation only, and say so in the README |
| [OpenResume](https://zenodo.org/records/14726170) (Zenodo, IEEE BigData 2024) | Anonymised real resumes plus a synthetic set, job titles mapped to ESCO | Listed as CC BY 4.0, but files are restricted: research use only, institutional email needed, no sharing, "not intended for commercial, real-world applications" | Derived from real people, anonymised with differential privacy | This is the "ask with uni email" route. Do not commit. Only use if we want a real-data check later |
| [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes) (Hugging Face) | 1K to 10K resumes, tagged both "Synthetic" and "real-world" | MIT | Unknown mix. An open question on the page asks the ratio and has no answer | Skip unless the authors clarify |

**Conclusion for CVs:** no open dataset I found is both clearly licensed for redistribution and free of real people's data. So the published demo set will be **synthetic** (section 4), and CareerCorpus is the best open real-world set for local testing.

### 3.2 Job adverts

| Source | What it is | Licence | Verdict |
|---|---|---|---|
| [DWP Find a Job API](https://www.api.gov.uk/dwp/find-a-job/) | Live UK job adverts, including public sector | Not stated on the API page. **[check]** terms on findajob.dwp.gov.uk | Good for a "live demo" feature later. Do not commit adverts until the terms are clear |
| Civil Service Jobs, NHS Jobs | UK public sector adverts | Website terms, no open data licence found | Read for inspiration on structure (essential and desirable criteria, Success Profiles). Do not copy text |
| Our own synthetic adverts | Written in the style of UK public sector adverts | Ours (same licence as the repo) | **Main source for the repo** |

UK public sector adverts have a useful, regular shape: job title, grade (for example HEO, SEO), essential criteria, desirable criteria and behaviours. Our synthetic adverts will follow that shape so the demo feels real to public sector recruiters.

### 3.3 Skills taxonomy

| Taxonomy | Licence | Verdict |
|---|---|---|
| [ESCO](https://esco.ec.europa.eu/en/use-esco/download) (European Commission), v1.2.1 | Free to download as CSV or JSON. The download page asks for an email. I could not read the exact licence wording on the site. EU Commission content is normally reusable with attribution under Decision 2011/833/EU. **[check]** the FAQ answer before release | **First choice.** About 13,900 skills with alternative labels, which is what we need for matching. European, so closer to UK job language than O*NET |
| [O*NET](https://www.onetcenter.org/license_db.html) (US Dept of Labor), v31.0 | CC BY 4.0. Credit "O*NET 31.0 Database" and USDOL/ETA, link the licence, say what changed | Backup, and useful for its "Technology Skills" list (named tools like Python, Tableau). US job titles though |

Plan: map extracted skills to ESCO skill IDs. Optionally add O*NET technology names as extra synonyms. Neither taxonomy is committed. `scripts/download_taxonomies.py` fetches them, and the README credits both.

## 4. Synthetic data (the published set)

We generate our own CVs and adverts with an LLM, then check them by hand.

**Size for v1:** 10 job adverts and 200 CVs (20 per advert). This is enough for a meaningful evaluation and small enough to check by hand. **[guess]** we can grow later.

**How CVs are generated:**

1. For each advert, pick a target relevance level for each CV: strong (3), partial (2), weak (1), unrelated (0). Aim for roughly 5 of each per advert.
2. Pick ESCO skills for the CV to match that level (for example a "strong" CV gets most essential skills, a "partial" CV gets half, and so on).
3. Ask the LLM to write a realistic UK CV that uses those skills in natural wording, not copied labels.
4. Insert **fake** personal details: name, email, phone, address, date of birth, nationality, photo note, gender pronouns, university and graduation year. These come from a fixed list we write, not from any real person.
5. Save the "ground truth" alongside each CV: which skills it was given, which personal details were planted, and the target relevance.

Step 4 matters twice. It lets us test the anonymiser (did it remove every planted detail?), and it lets us run a fairness check (section 6).

**Things to avoid:** the LLM must not be asked to imitate real people or companies. Employer names in CVs come from an invented list.

**Seed and model:** the generation script stores the random seed and model name in `data/synthetic/README.md`, so the set can be rebuilt.

## 5. Labelled CV-to-job pairs for evaluation

Every (advert, CV) pair needs a relevance score from 0 to 3. We get it in two ways:

1. **Built-in label:** the target level from generation (section 4, step 1).
2. **Human label:** Om reads a sample and scores it without seeing the built-in label. Start with 60 pairs (6 per advert). **[question for Om]** could a classmate also label the same 60, so we can report agreement between two people (Cohen's kappa)? That makes the evaluation much more convincing to an employer.

If human and built-in labels disagree, the human label wins and we note it.

For local tests on real data, CareerCorpus has job family labels. A CV in the same family as the advert counts as "relevant". This is rough, but gives a second check that the system works on real writing, not only on LLM-written text.

**Metrics (detail goes in the evaluation plan):** nDCG@5 and precision@5 for ranking, skill extraction precision and recall against the planted skills, and anonymiser recall against the planted personal details (target: 100% of names, emails and phones).

## 6. Fairness test data

For each of 20 CVs, make copies that differ **only** in a protected characteristic signal: name (suggesting different ethnicities or genders), age signals (graduation year), a career gap, or a disability mention. The skills stay identical.

If the system is working, every copy gets the same score, because the anonymiser removes these signals before scoring. We report the largest score difference found. This links directly to the Equality Act 2010 section of the README.

## 7. Folder layout and formats

```
data/
  README.md              what each folder is, and its licence
  synthetic/             committed: our own generated data
    jobs.jsonl           one advert per line
    cvs.jsonl            one CV per line, with planted details
    labels.csv           job_id, cv_id, relevance, labeller
    fairness_pairs.jsonl CV copies for the fairness test
    README.md            seed, model, how it was made
  external/              NOT committed (in .gitignore)
    careercorpus/
    esco/
    onet/
  processed/             NOT committed: anonymised text, embeddings
scripts/
  download_taxonomies.py
  download_careercorpus.py
  generate_synthetic.py
```

**Formats:**

- `.jsonl` (one JSON record per line) for CVs and adverts. Easy to read in pandas with `pd.read_json(path, lines=True)` and easy to diff in Git.
- `.csv` for labels, so they can be edited in a spreadsheet.
- Embeddings saved as `.npy` or `.parquet` in `processed/`, never committed.

**Example CV record:**

```json
{
  "cv_id": "cv_0007",
  "job_id": "job_03",
  "text": "Full CV text with planted personal details...",
  "planted_pii": {"name": "Priya Lawson", "email": "p.lawson@example.com", "phone": "07700 900123"},
  "planted_skills": ["esco:...", "esco:..."],
  "target_relevance": 2,
  "source": "synthetic-v1"
}
```

The phone number uses Ofcom's 07700 900xxx range, which is reserved for fiction, and emails use `example.com`, which is reserved for examples. So nothing planted can reach a real person.

## 8. Backup: data from the university

If we later want results on real CVs, Om can ask the university (for example the careers service or a supervisor) for access. Before asking, have answers ready for: what data, why, how it is stored, who sees it, and that nothing will be published. That data would live only in `data/external/`, and the README would report summary numbers only. **[question for Om]** do we need this at all for v1? My suggestion is no: synthetic plus CareerCorpus is enough for a portfolio project.

## 9. Open questions

1. **[question for Om]** Which job families should the 10 adverts cover? Suggestion: 4 data or digital roles (Data Analyst, Data Scientist, Software Developer, Digital Product Manager), 4 UK public sector roles (Policy Adviser, Operational Delivery Officer, Finance Business Partner, HR Adviser), and 2 others (Teacher, Nurse) to test that the system is not only good at tech CVs.
2. **[question for Om]** Which LLM for generation? Options: a free local model in Colab, or an API model. API quality is better, but it costs a little money.
3. **[check]** Exact ESCO licence wording, and the licence on the Kaggle page for the resume dataset.
4. **[check]** DWP Find a Job API terms, before any live job adverts feature.
