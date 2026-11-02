# Income-tax Act QA

Ask a question about India's Income-tax Act, 1961 in plain English and get an answer drawn only from
the text of the Act. Every point in the answer cites the section, sub-section or clause it rests on,
the document and the PDF page, and the server checks each citation against the Act's text before
showing it.

Live demo: https://taxqa.soniksarungale.com

- [A. Project overview](#a-project-overview)
- [B. Technology stack](#b-technology-stack)
- [C. Architecture and approach](#c-architecture-and-approach)
- [D. Setup and execution](#d-setup-and-execution)
- [E. Testing and limitations](#e-testing-and-limitations)

## Source document and edition

| | |
|---|---|
| Document | Income-tax Act, 1961 [43 of 1961], as amended by the Finance Act, 2026 |
| Publisher | Income Tax Department, Ministry of Finance: <https://www.incometaxindia.gov.in/income-tax-act> (the source named in the assignment brief) |
| File | `Income-tax-Act-1961_2026_2026-06-18_02-47-37_b9326c_en.pdf`, 1,117 pages, 179 MB, created 18 June 2026 |
| SHA-256 | `73d264fd05bc3b19ee003f399aeb50faf7ea36a42f345fa94ebb9b3a2ad0cb93` |

**Applicability.** The Income-tax Act, 2025 replaces the 1961 Act from tax year 2026-27. The 1961 Act
still governs income up to financial year 2025-26 (assessment year 2026-27) and proceedings for those
years. Answers here are only as current as this edition: amendments after the Finance Act, 2026, rules,
notifications, circulars and case law are not covered.

The PDF is not in the repository (GitHub's file limit is 100 MB). Download it from the link above and
check the hash, as described in [setup](#d-setup-and-execution).

## A. Project overview

**What it does.** The PDF is parsed into its statutory structure (chapter, section, sub-section,
clause, sub-clause, proviso, Explanation) with the PDF page of every piece. A question is answered in
four steps:

1. **Retrieve** the relevant provisions with hybrid search: meaning (vector), keywords (full-text) and
   any section the question names.
2. **Assemble context** around each hit: the whole provision if it is short, otherwise the hit plus the
   text it depends on (the clause a proviso qualifies, the sub-section a clause belongs to, and
   sub-sections it refers to).
3. **Answer** with an LLM that may use only those extracts and must return each point as a claim with
   cited extract labels and a word-for-word quote.
4. **Verify** each claim in code: the cited extracts must be ones that were supplied, and the quote must
   appear in the cited extract's own text. Unverified claims are flagged; if none verify, the app says
   the Act text it found does not support an answer.

**Features**

- Citations to section, sub-section, clause, proviso or Explanation, e.g. `Section 24(b), second
  proviso`, with the document name and PDF page; each opens the official PDF at that page.
- Server-side citation verification and a statement-by-reference table, as in the brief's example.
- Refusal for questions the Act does not answer (GST rates, company registration, case law, general
  knowledge), with the reason.
- An answer confidence score computed from evidence, with its breakdown shown.
- Provisions amended by the Finance Acts 2025 and 2026 are tagged.
- Schedules are indexed too and cited as e.g. `First Schedule, rule 2`.
- LLM provider chosen in `.env`: Claude Code CLI (no API key), OpenAI, Anthropic or Gemini.
- An evaluation set with a script that scores retrieval, citation, refusal and verification.

## B. Technology stack

| Part | Choice | Why | Alternatives considered |
|---|---|---|---|
| Language | Python 3.12 | Required backend language; 3.12 has wheels for every dependency | 3.14 also worked, kept 3.12 so reviewers on older setups can install it |
| Web | FastAPI + Uvicorn | Typed request validation, small, serves the static UI too | Flask (no validation built in), Django (more than needed) |
| PDF parsing | PyMuPDF | Gives every text span with font, size, weight and position, which the parser needs: section numbers are bold, footnote markers are small and raised, headings are bold margin text | pdfplumber (slower on 1,117 pages), plain text extraction (loses the bold and size cues) |
| Database | PostgreSQL 17 + pgvector | One store for the structure (provisions, chunks, pages), vectors and full-text search, so hybrid search is one SQL round trip and citations join straight to their provision | A separate vector DB (Chroma, Qdrant) plus a keyword engine: more moving parts for 8,500 chunks |
| Keyword search | Postgres full-text (`tsvector`) weighted by term rarity | Legal questions often hinge on exact words ("tuition fees", "borrowed capital") | BM25 in Elasticsearch/OpenSearch: too heavy for this server |
| Embeddings | `BAAI/bge-small-en-v1.5` via fastembed (ONNX, quantised, 384 dimensions) | Runs locally on CPU without PyTorch, no API key, about 290 MB for the whole app process | Hosted embedding APIs (need a key and send the Act out on every ingest); bge-base (better, but about twice the memory on a 2 GB server) |
| LLM | Pluggable; default is the Claude Code CLI (Sonnet) | Strong at following "use only these extracts" and returning strict JSON. The CLI uses the server's existing login, so no key is stored | OpenAI, Anthropic and Gemini HTTP APIs are implemented and selected in `.env` |
| Frontend | Plain HTML, CSS and JavaScript | The brief asks for a simple interface; no build step | React (adds a toolchain for one page) |
| Deployment | Docker (Postgres), pm2 (app), nginx + Let's Encrypt | Matches the other services on the host | |

Trade-offs worth stating:

- **Exact vector search, no ANN index.** An HNSW index at default settings returned only 16 of the true
  40 nearest chunks for one test question; an exact scan of 8,500 vectors takes about 40 ms. An index
  would be needed at a much larger scale.
- **Small embedding model.** Chosen for memory. Its weaknesses are offset by the keyword search, the
  section lookup, and a short glossary that maps everyday words to the Act's wording (see C).
- **One LLM call at a time** with the CLI provider (each CLI process takes about 220 MB). Up to eight
  questions queue; beyond that the API returns "busy".

## C. Architecture and approach

```mermaid
flowchart LR
  subgraph Ingest["Ingest (once): python -m taxqa.ingest"]
    PDF[Official PDF] --> P[parser.py<br/>structure + pages]
    P --> C[chunks with refs, pages,<br/>context, amendment tags]
    C --> E[embed.py<br/>bge-small, local]
    E --> DB[(Postgres<br/>provisions, chunks,<br/>vectors, tsvector)]
  end
  subgraph Ask["Per question: POST /api/ask"]
    Q[Question] --> S[search.py<br/>vector + keyword + section ref<br/>fused with RRF]
    DB --> S
    S --> X[expand<br/>whole provision or hit + parents<br/>+ referenced sub-sections]
    X --> L[llm.py<br/>JSON claims with<br/>labels + quotes]
    L --> V[answer.py<br/>verify every citation]
    V --> K[confidence.py]
    K --> UI[Web UI<br/>answer, references,<br/>links to PDF page]
  end
```

### PDF extraction and processing (`taxqa/parser.py`)

The PDF has no table of contents, no printed page numbers and no outline, so structure comes from the
typography:

- **Lines are rebuilt from span baselines** (3 pt tolerance). PyMuPDF's own line grouping splits labels
  such as `(ca)`, which sit 1-2 pt lower than the text after them.
- **The running header** ("Income Tax Department / Ministry of Finance") is removed by position. Font
  could not be used: pages 1-6 set clause labels in the header's font.
- **A section starts at a bold number** at the start of a line ("24."). Its bold marginal heading is on
  the line before. Footnotes use the same font and size as the body and also start with a number
  ("76. Sub. by the Act No. 15 of 2024..."), but are not bold.
- **Footnotes are not indexed.** They sit after the section text and quote the wording a provision had
  before it was substituted ("Prior to its substitution, ... read as under"), which would produce wrong
  answers. Footnote markers (spans under 8 pt, raised above the line) are removed from the text and used
  to tag the provisions amended by the Finance Acts 2025 and 2026.
- **Nesting** is decided by a list-continuation rule: a label continues an open list of its kind (next
  in sequence, including inserted labels such as `(1A)`, `(ba)`, `(iia)`), or opens a nested list only
  if it is a first label (`(1)`, `(a)`, `(i)`, `(A)`). Anything else is a cross-reference in the
  sentence. This is what tells `(i)` the roman numeral from `(i)` the letter after `(h)`.
- **Provisos and Explanations** become their own nodes ("first proviso", "Explanation 2"). Words after
  a list ("...shall be allowed") return to the provision the list belongs to.
- `[***]` is shown as `(omitted)`; compounds split across lines ("sub-" / "section") are rejoined.
- **Source order is kept**, with one exception: section 139 is printed only on pages 1-6, before
  Chapter I. It is moved back into Chapter XIV for structure but keeps its real pages for citation.

Result: 920 sections (98 of them omitted, kept so that a question about one gets an honest answer) and
143 schedule rows, in 8,500 chunks.

### Chunking and indexing

- **One chunk per structural unit**: a sub-section, clause, proviso or Explanation. Sub-clauses stay
  with their clause unless the clause is long. No chunk exceeds 1,800 characters (longer units are split
  at line boundaries), which keeps them within the embedding model's window.
- Each chunk stores its **citation reference** (`Section 80C(2)(xvii)`), its structural path, its first
  and last PDF page, and a **context** line: section number and heading, chapter title and the opening
  words of the unit above it. Without that, `(a) a sum equal to thirty per cent of the annual value`
  does not say what it is deducted from.
- The embedding is computed over reference + context + text. The `tsvector` (English stemming) covers
  context + text and is a generated column, so it can never fall out of sync.
- Ingest stores the text first and fills embeddings in batches of 64. It is resumable, idempotent (the
  PDF's SHA-256 identifies the edition) and took about 25 minutes on the 2 GB server.

### Retrieval (`taxqa/search.py`)

Three ranked lists, fused with reciprocal rank fusion (k = 60):

1. **Vector**: cosine similarity between the question (with the bge query instruction) and every chunk.
2. **Keyword**: each chunk scores the sum of the inverse document frequencies of the question terms it
   contains. Postgres's built-in ranking ignores how rare a word is, so "paid" counted as much as
   "tuition"; terms found in more than a fifth of all chunks ("section", "income", "tax") are ignored.
3. **Section reference**: "section 24(b)", "u/s 80C", "s. 139(1)" or a bare "80CCD(1B)" in the
   question fetches that provision directly.

Before searching, common shorthand is spelled out as the Act words it (TDS → tax deducted at source,
HRA, LTCG, HUF, ITR and others), and a few everyday words get the Act's term (gift → received without
consideration, home loan → borrowed capital, rented out → let, mistake → omission or wrong statement).

At most four chunks per section enter the 16 results, unless the section was named. Without this cap a
home-loan question returned twelve chunks of section 80EE and none of sections 23 and 24.

**Context expansion.** Provisos and Explanations change the rule they follow, so the model sees more
than the hits. For each section hit, in rank order: the whole provision if it is under 6,000 characters
(about 90% of provisions) or named in the question; otherwise the hits, every unit above them, and any
sub-section of the same section their text refers to ("persons specified in sub-section (4)"). The
total is capped at 24,000 characters. This is what brings in section 24(b)'s second proviso (the two
lakh limit) and section 80C(4)(c) ("any two children") for the tuition fees question.

### Answer generation and citation verification (`taxqa/answer.py`)

The extracts are numbered `[S1]`, `[S2]`..., grouped under their section heading, each with its
reference and page. The system prompt requires a JSON object:

```json
{
  "answerable": true,
  "claims": [
    {"statement": "Yes, Section 24(a) allows a deduction of thirty per cent of the annual value ...",
     "sources": ["S23"],
     "quote": "a sum equal to thirty per cent of the annual value"}
  ],
  "not_covered": "what the extracts do not answer"
}
```

The first claim gives the direct answer applied to the user's facts. No knowledge from outside the
extracts is allowed (no amounts, dates, rules, circulars or case law that are not in them).

**Citations are generated by the server, not the model.** The model only names extract labels. The
section reference, document name and page shown to the user come from the database record of that
extract, so the model cannot invent a section number or a page.

Each claim is then checked:

| Check | Fails when |
|---|---|
| Sources given | the claim cites nothing |
| Sources real | it cites a label that was not supplied |
| Quote present | its quote (at least three words; quotes, dashes, brackets and whitespace normalised; `...` splits it into passages that must each be present) is not in the cited extract's own text |

Context lines do not count for the quote check: a quote from the clause a proviso hangs on belongs to
that clause, not the proviso. The outcome:

- **answered**: every claim verified;
- **partial**: some verified, some flagged "Not verified" in the UI with the reason;
- **refused**: the model said the extracts do not answer, or no claim verified. The reason is shown;
  no answer is presented as fact;
- **error**: the model was unavailable or its reply was not valid JSON twice.

### Reducing hallucination, summarised

- Retrieval decides which provisions are considered; the model never picks sections from memory.
- The prompt forbids outside knowledge and asks for gaps to be stated rather than filled.
- Every claim must quote the Act word for word, and the quote is checked in code.
- Citation details come from the database, not from the model's text.
- Temperature 0 on the HTTP providers.
- The question is treated as data: the prompt says instructions inside it are not to be followed.

### Confidence score (`taxqa/confidence.py`)

Language models are poor judges of their own accuracy, so the score is computed from evidence the
server can measure:

| Component | Weight | Measures |
|---|---|---|
| Verified | 0.40 | share of the answer's claims whose citation and quote checked out |
| Retrieval | 0.30 | for each cited provision, the best cosine similarity of a retrieved chunk to the question, scaled from 0.60 (0%) to 0.80 (100%), averaged |
| Agreement | 0.15 | share of cited provisions found by at least two of the three searches |
| Completeness | 0.15 | 1 if the model reported nothing left unanswered, 0.5 if it did |

**High** is 0.75 or more, **medium** 0.50 or more, otherwise **low**. Low-confidence answers carry a
warning to read the cited provisions before relying on them. Refusals and errors get no score.

The 0.60-0.80 range comes from measurement: on this index, questions the Act answers had top
similarities of 0.66-0.80 and unrelated questions 0.50-0.67. Because those ranges overlap, similarity
alone cannot decide whether to answer. Refusal is decided by citation verification, and the score
grades only answers that passed it.

### Project layout

```
taxqa/
  parser.py      PDF -> provisions and chunks
  ingest.py      parse, store, embed (python -m taxqa.ingest)
  embed.py       local embedding model
  schema.sql     tables, full-text column and indexes
  search.py      hybrid retrieval and context expansion
  llm.py         LLM providers
  answer.py      prompt, claim parsing and citation verification
  confidence.py  confidence score
  app.py         HTTP API and static UI
  eval.py        evaluation runner (python -m taxqa.eval)
  static/        web interface
eval/            questions and latest results
tests/           unit tests and tests against the real PDF and index
deploy/          pm2 and nginx configuration
```

## D. Setup and execution

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker with Compose (for Postgres + pgvector)
- About 1 GB of free RAM for ingest and 300 MB for the running app (plus about 220 MB per answer
  while the Claude CLI runs)
- One LLM provider:
  - `claude-cli`: the Claude Code CLI installed and
    logged in on the machine (no key needed), or
  - an API key for OpenAI, Anthropic or Gemini

### Steps

```bash
git clone https://github.com/soniksarungale/income-tax-act-qa.git
cd income-tax-act-qa

# 1. The Act PDF (see "Source document and edition"); put it in data/ and check the hash
mkdir -p data
cp /path/to/Income-tax-Act-1961_2026_2026-06-18_02-47-37_b9326c_en.pdf data/Income-tax-Act-1961_2026.pdf
sha256sum data/Income-tax-Act-1961_2026.pdf   # 73d264fd...0cb93

# 2. Configuration
cp .env.example .env          # then edit: see the table below

# 3. Postgres with pgvector, on 127.0.0.1:5433
docker compose up -d

# 4. Dependencies (creates .venv)
uv sync

# 5. Parse, index and embed the Act (about 20 s to parse, then embedding:
#    ~25 min on a 2-core server, a few minutes on a laptop). Safe to rerun; resumes if interrupted.
uv run python -m taxqa.ingest

# 6. Run the app on http://127.0.0.1:4700
uv run uvicorn taxqa.app:app --port 4700
```

### Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://taxqa:taxqa@127.0.0.1:5433/taxqa` | Postgres from `docker-compose.yml` |
| `ACT_PDF_PATH` | `data/Income-tax-Act-1961_2026.pdf` | the Act PDF; also served at `/act.pdf` for the page links |
| `LLM_PROVIDER` | `claude-cli` | `claude-cli`, `openai`, `anthropic` or `gemini` |
| `LLM_MODEL` | `sonnet` for claude-cli, `claude-sonnet-5-5` for anthropic | required for openai and gemini |
| `LLM_API_KEY` | | required for openai, anthropic and gemini |
| `CLAUDE_BIN` | `claude` | path to the Claude Code CLI; give the full path when running under pm2 or systemd |
| `POSTGRES_PASSWORD` | `taxqa` | used by `docker-compose.yml`; change it together with `DATABASE_URL` |

`.env` is git-ignored; no keys are committed.

### API

- `POST /api/ask` with `{"question": "..."}` (3-1000 characters) returns the status, claims with
  citations, what is not covered, the confidence score and its components, the cited extracts and
  timings. Limited to 10 questions per client address per 10 minutes.
- `GET /api/info`: document, edition and LLM provider.
- `GET /act.pdf`: the Act PDF, with range requests, so `act.pdf#page=92` opens quickly.

### Deployment (as run on the demo server)

```bash
pm2 start deploy/ecosystem.config.cjs && pm2 save      # app on 127.0.0.1:4700
sudo cp deploy/nginx-taxqa.conf /etc/nginx/sites-available/taxqa
sudo ln -sf /etc/nginx/sites-available/taxqa /etc/nginx/sites-enabled/taxqa
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d taxqa.soniksarungale.com
```

## E. Testing and limitations

### Sample questions and answers

Four questions asked once on the live site, with full outputs in [docs/samples.md](docs/samples.md):

| Question | Status | Sections cited | Claims verified |
|---|---|---|---|
| Rented house: 30% deduction and loan interest (the brief's example) | partial | 22, 23(1)(b), 24, 24(a), 24(b), 24(b) Explanation | 4/5 |
| Is tuition fees paid for children deductible? | answered | 80C(1), 80C(2)(xvii), 80C(4)(c) | 4/4 |
| What is the penalty for not deducting TDS? | answered | 271C(1)(a), 271C(1)(b), 271C(2) and proviso, 271H(1), 271H(2) | 4/4 |
| What is the GST rate on restaurant services? | refused | - | - |

In the first answer one point was flagged because its quote came from the extract's context line
rather than the cited text; [docs/samples.md](docs/samples.md) explains it.

![Answer to the brief's example question](docs/screenshots/house-property.png)

More screenshots in [docs/screenshots](docs/screenshots): the refusal, the other two answers and the
page on a phone.

### Automated tests

```bash
uv run pytest
```

- **Parser unit tests** on synthetic lines: section starts versus footnotes, nesting, provisos, closing
  words, cross-references on wrapped lines, amendment tags, omitted sections, rejoined compounds.
- **Parser tests on the real PDF** (skipped if it is absent): edition, page count, section 24's
  heading, chapter, part and page; section 139's placement; no pre-amendment footnote text indexed;
  80C(2) clauses; schedules; chunk sizes.
- **Retrieval tests on the real index** (skipped if it is not loaded): the expected sections for seven
  questions, including the brief's example; named-section lookup; context expansion.
- **Answer and verification tests** with a stubbed model: verified, flagged and refused claims, fenced
  JSON, retry on a bad reply, provider errors.
- **Provider tests** with stubbed subprocess and HTTP calls: CLI flags, one call at a time, queue
  limit, request formats, error messages, keys never in URLs.
- **Confidence and API tests**: score components, response shape, validation, rate limit.

### Evaluation

`uv run python -m taxqa.eval --out eval/results.md` runs every question in
[eval/questions.json](eval/questions.json) through the whole pipeline: 18 questions the Act answers,
each with the section a correct answer must cite, and 4 it does not (GST, company registration, a court
case, general knowledge). Latest run ([eval/results.md](eval/results.md)), claude-cli with Sonnet:

| Measure | Result |
|---|---|
| Required section among the extracts | 18/18 |
| Required section cited by a verified claim | 18/18 |
| Refused exactly when it should have been | 22/22 |
| Claims that passed verification | 97/98 |

The one failed claim was accurate, but its quote silently left out words from the middle of section
80G(5)(ii) ("does not, [or the rules ... do not,] contain"), so it was shown as not verified; the report
lists each failed claim with its reason. Runs vary slightly because the CLI provider has no temperature
setting: two earlier runs on the same questions verified 104/104 (with a slightly earlier prompt) and
94/96.

These questions were also used to tune retrieval (the per-section cap, the result count and the
glossary came from failures in the first run: 16/18 cited, 20/22 refusals correct), so they measure the
system as built, not as it would do on unseen questions. A held-out set written by a tax practitioner
would be the honest next test.

### Known limitations

- **Errors in the source PDF are reproduced as printed**, so quotes match the official text:
  section 23(1) refers to "section 242" (it should read section 22; section 242 is about refund claims),
  and section 23(4) refers to "sub-section (21)", which does not exist.
- Sections 92A, 92B, 92C, 158BB and 234-I have no heading in the PDF, so none is shown. Section 186 is
  not in the PDF at all.
- Section 139 appears only on pages 1-6 of the PDF, before Chapter I; its citations give those pages.
- PDF page numbers are cited because the PDF prints none of its own.
- The Act often defers to the Income-tax Rules ("as may be prescribed"), which are not indexed; answers
  then say the detail is not in the Act. Circulars, notifications and case law are not covered either.
- Verification proves that each quote is in the Act and in the cited provision. It does not prove the
  statement draws the right conclusion from the quote; that still needs a reader, which is why every
  citation links to the page.
- A question that needs many long provisions at once can exceed the 24,000-character context, in which
  case lower-ranked provisions are left out.
- With the CLI provider, questions are answered one at a time (about 7-12 s each).

### Possible improvements

- A cross-encoder reranker on the fused candidates, and a larger embedding model on a machine with more
  memory.
- Index the Income-tax Rules and link "prescribed" to the rule that prescribes it.
- Index the Income-tax Act, 2025 and route questions by tax year.
- Follow cross-references to other sections ("referred to in section 80CCD") during context expansion.
- A larger, independently written evaluation set, including adversarial questions.
- Accept a quote from the opening words of the sub-section a cited clause belongs to (as in sample 1,
  "The provisions of sub-section (2) shall not apply if" for clause 23(3)(a)), since those words are
  part of the clause's sentence; provisos would still be checked against their own text.
