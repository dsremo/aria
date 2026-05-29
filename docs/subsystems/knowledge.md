# Doctrine & lessons-learned retrieval — grounding recommendations in cited precedent

The `knowledge` package gives ARIA a searchable corpus of spaceflight history: flight rules, anomaly reports, and standards. When an anomaly fires, the closed-loop replay runner queries the index, selects the most relevant records, and passes them verbatim into the LLM prompt alongside the live telemetry. The language model therefore reasons over cited precedent rather than relying solely on training-data recall.

---

## Where it sits in the architecture

The package sits between the raw corpus files and the cognitive layer. The call path, simplified:

1. `data/doctrine/*.json`, `data/lessons_learned/llis_corpus.json`, and `data/ecss/active_standards.json` are the on-disk corpora.
2. `TfIdfIndex` (in [`../../src/aria/knowledge/retrieval.py`](../../src/aria/knowledge/retrieval.py)) is built at startup by `build_default_lesson_index()`. It indexes the 52 in-memory curated lessons plus 2,126 NASA LLIS records — 2,178 `LessonRecord` objects total.
3. `DoctrineLoader` (in [`../../src/aria/cognitive/doctrine/loader.py`](../../src/aria/cognitive/doctrine/loader.py)) loads `data/doctrine/*.json` into a `DoctrineBundle`. `select_relevant_entries()` scores each `DoctrineEntry` against the anomaly parameter, severity, state tokens, and free text, then `format_doctrine_for_prompt()` serialises the top-k results within a 4,000-character budget.
4. The closed-loop runner (`../../src/aria/replay/closed_loop.py`) calls `_build_doctrine()` and `_build_lessons()` on every anomaly event, concatenates the two blocks, and injects the combined text as the `Doctrine excerpt:` section of the LLM prompt (see `_build_prompt()` in that file).
5. The LLM advisor receives `GET=HH:MM:SS / Anomaly / Severity / Recent state / **Doctrine excerpt**` and must return a JSON object with `proposed_action`, `rationale`, `immediate_steps`, and `confidence`. The doctrine excerpt is the mechanism that grounds the rationale in real mission history.

The Apollo 13 closed-loop demo illustrates this end-to-end. When `O2_TANK_2_PRESSURE` spikes, the retriever surfaces the `apollo-13-cryo-stir` lesson record (Cortright Commission Report, 1970) and the matching flight rule from `data/doctrine/apollo_csm_flight_rules.json`, both of which appear in the prompt the LLM reasons over. See the replay report at [`../../docs/APOLLO13_REPLAY_REPORT.md`](../../docs/APOLLO13_REPLAY_REPORT.md) for a worked example of this flow.

The cognitive engine's broader reasoning loop — tool registry, constitutional checks, hallucination detector — is documented in [`./cognitive.md`](./cognitive.md).

---

## What's in the package

Six files under [`../../src/aria/knowledge/`](../../src/aria/knowledge/):

| File | Role |
|------|------|
| `__init__.py` | Re-exports the public surface: `LessonRecord`, `LessonsLearnedStore`, `TfIdfIndex`, `build_default_lesson_index`, `load_curated_lessons`, `load_default_procedures`, `write_lessons_to_doctrine`. |
| `retrieval.py` | `TfIdfIndex` — the retrieval engine. `_tokenise()` lowercases and strips stopwords. `add()` builds per-document term-frequency counters and a corpus-level document-frequency counter. `search()` scores each document with sublinear TF × smoothed IDF, normalises by document length, and adds a configurable `keyword_boost` (default 1.5×) when a query token matches a record's explicit keyword list. `RetrievalHit` carries the `LessonRecord`, the final score, and the matched terms. |
| `lessons_learned.py` | `LessonRecord` dataclass (record_id, title, summary, keywords, source, citation, parameters, fetched_at_iso). Holds 52 curated in-memory records across three tuples (`_CURATED_LESSONS_CORE`, `_CURATED_LESSONS_EXTENDED`, `_CURATED_LESSONS_PROBES`). Also contains `LessonsLearnedStore` for JSON serialisation, and `NtrsSearchClient` for live queries against the NASA Technical Reports Server. |
| `llis_ingest.py` | `LlisLesson` dataclass and `LlisFetcher` for bulk-fetching from the NASA Lessons Learned Information System public search API. `load_llis_lessons()` loads the pre-fetched `data/lessons_learned/llis_corpus.json`. Each `LlisLesson` converts to a `LessonRecord` via `to_lesson_record()`. |
| `ecss_ingest.py` | `EcssStandardRecord` dataclass and `EcssFetcher` for scraping `ecss.nl`. Requires browser-exported cookies in `ARIA_ECSS_COOKIE_*` env vars (the site is reCAPTCHA-gated). `load_ecss_records()` and `write_ecss_records()` handle the pre-fetched `data/ecss/active_standards.json`. ECSS records are not currently loaded into `TfIdfIndex` by `build_default_lesson_index()`; they are available for future integration. |
| `procedures.py` | `load_default_procedures()` loads 18 standard operating procedures (cabin depressurisation, fire, CO2 scrubber failure, battery thermal runaway, collision avoidance, EVA pre-breathe, docking approach, and others) into a `MemoryStore` instance. These are retrieved via the memory layer, not the TF-IDF index. |

---

## The corpus

### Curated lessons (52 records, in-memory)

The `lessons_learned.py` module hard-codes 52 `LessonRecord` instances derived from published accident investigation reports and mission documents. They span:

- Major accidents: Apollo 1, Apollo 13, Challenger, Columbia, Ariane 5 Flight 501, Genesis
- Near-misses and anomalies: MCO unit-conversion loss, SOHO attitude loss, Cassini units near-miss, ISS Quest airlock leak, ISS ammonia false alarm, Parmitano EVA-23 helmet water
- Recovery and graceful-degradation cases: Hayabusa 1, Kepler K2, PROBA-2 magnetometer recovery, Soyuz MS-11 pad abort
- Debris and collision events: Mir-Spektr, Iridium-Cosmos, Fengyun-1C ASAT
- Recent ISS: SARJ bearing contamination, TCS pump failure, WPA pump failure, Zvezda leaks (2020, 2025), Boeing Starliner CFT thrusters, JWST micrometeorite

Each record carries: `record_id`, `title`, `summary` (100–400 words), `keywords`, `source` (report identifier), `citation` (full reference string), and `parameters` (telemetry parameter names the lesson is relevant to).

### NASA Lessons Learned Information System (2,126 records, on-disk)

`data/lessons_learned/llis_corpus.json` holds 2,126 records fetched from the NASA LLIS public search API (`llis.nasa.gov`). Each record maps to a `LlisLesson` with fields `lesson_id`, `title`, `abstract`, `description_event`, `lesson`, `recommendation`, `lesson_date`, `submitting_organization`, `topics`, and `categories`. On load, each converts to a `LessonRecord` with the event description, lesson text, and recommendation joined as the summary (capped at 1,500 characters).

The LLIS corpus covers structural/fatigue reliability, software engineering, propulsion, manufacturing quality, and ground operations, sourced from across NASA centres. Dates range from the 1960s to the 2020s.

### Doctrine entries (279 entries, 25 JSON files)

`data/doctrine/` holds 25 JSON files totalling 279 `DoctrineEntry` records. These are flight rules, malfunction procedures, checklists, and reference extracts. Breakdown by file:

| File | Records | Coverage |
|------|---------|----------|
| `iss_subsystem_flight_rules.json` | 11 | ISS subsystem-level rules |
| `iss_extended_rules.json` + `_2` + `_3` | 24 | Extended ISS operational rules |
| `ecss_active_catalog.json` | 144 | ECSS standard catalog (mirrors ECSS data) |
| `spacecraft_subsystems_misc.json` | 9 | Mixed subsystem rules |
| `skylab_apollo_flight_rules.json` | 6 | Skylab/Apollo rules |
| `sts_flight_rules.json` | 6 | Space Shuttle rules |
| `nasa_lessons_learned.json` | 10 | Condensed NASA lessons |
| `nasa_standards_extract.json` | 6 | NASA standard extracts |
| `ecss_standards_extract.json` | 6 | ECSS standard extracts |
| Other files (14) | 57 | CCSDS, cubesat, cybersecurity, deep space, EVA, ESA/JAXA, ISS ECLSS, ITU radio, launch vehicle, Mars rover, crew vehicle, payload/science, Soyuz/Progress rules |

Each `DoctrineEntry` has `rule_id`, `kind` (flight_rule / malfunction_procedure / incident_report / checklist / reference), `title`, `body`, `keywords`, `citation`, and `parameters`. The `render()` method formats it as `[KIND RULE_ID] Title  (citation)\nbody` for direct prompt injection.

### ECSS active standards (144 records, separate path)

`data/ecss/active_standards.json` holds 144 `EcssStandardRecord` objects scraped from `ecss.nl`. Each carries `standard_id` (e.g. `ECSS-E-ST-31-02C`), `title`, `url`, `issue_date`, `standard_type` (engineering / product_assurance / management / system), and `pdf_urls`. These are currently available for lookup via `load_ecss_records()` but are not wired into `build_default_lesson_index()`; the TF-IDF index does not include them at runtime.

---

## Current limitations

**Classical IR baseline, no semantic retrieval.** `TfIdfIndex` is a bag-of-words TF-IDF scorer with sublinear term frequency and smoothed IDF. It finds records that share tokens with the query. It has no understanding of synonyms, acronym expansion, or semantic proximity. A query for "oxygen depressurisation" will miss records that only contain "ppO2 drop" unless those tokens overlap. A dense-retrieval approach (bi-encoder embeddings + approximate nearest-neighbour search) would retrieve semantically related records that TF-IDF misses, at the cost of an embedding model dependency and index-build time. There is currently no embedding-based retrieval path.

**Doctrine relevance scoring is keyword-weighted heuristic, not learned.** `select_relevant_entries()` in `doctrine/loader.py` assigns 100 points for a direct parameter match, 25 for a parameter name appearing in the text, 5 for severity-word overlap, and fractional scores for state-token and free-text token intersections. These weights were set by inspection, not tuned against held-out relevance judgements.

**ECSS corpus not in the retrieval index.** The 144 ECSS standard records are on disk and loadable, but `build_default_lesson_index()` does not call `load_ecss_records()`. Integrating them would require either converting `EcssStandardRecord` to `LessonRecord` or extending `TfIdfIndex` to accept a second record type.

**LLIS corpus freshness.** `data/lessons_learned/llis_corpus.json` is a static snapshot. NASA continuously adds new lessons to the public LLIS database. `LlisFetcher.fetch_all()` can refresh it, but there is no automated refresh schedule.

**Corpus coverage is uneven.** The 2,178 indexed records weight ISS, Apollo-era, and robotic planetary missions heavily. CubeSat/SmallSat anomalies, commercial launch vehicle history, and non-English-language agency records (ISRO, CNSA) are sparse or absent. The corpus is sufficient for demonstration at TRL 3–5 but not for claims of comprehensive coverage.

**No relevance feedback or query expansion.** Queries are the anomaly parameter name plus severity label plus detector reason string — constructed programmatically. There is no mechanism for the crew or operator to refine retrieval or flag a poor result.

---

## Where to start reading

**Entry points**

- [`../../src/aria/knowledge/retrieval.py`](../../src/aria/knowledge/retrieval.py) — `TfIdfIndex` and `build_default_lesson_index()`. Start here for the retrieval mechanism.
- [`../../src/aria/knowledge/lessons_learned.py`](../../src/aria/knowledge/lessons_learned.py) — `LessonRecord` definition and the 52 curated records. The `_CURATED_LESSONS_CORE` tuple at line 99 is where the historical record entries live.
- [`../../src/aria/cognitive/doctrine/loader.py`](../../src/aria/cognitive/doctrine/loader.py) — `DoctrineLoader`, `DoctrineEntry`, `select_relevant_entries()`, `format_doctrine_for_prompt()`. This is how doctrine reaches the prompt.
- [`../../src/aria/replay/closed_loop.py`](../../src/aria/replay/closed_loop.py) — `ClosedLoopRunner._build_doctrine()` and `_build_lessons()` show how both retrieval paths are merged and injected into `_build_prompt()`.

**Tests**

- [`../../tests/integration/test_retrieval.py`](../../tests/integration/test_retrieval.py) — confirms that Apollo 13, STS-107, Parmitano, Iridium-Cosmos, and MCO/Cassini units queries return the correct top hits. Also tests keyword-boost behaviour and top-k bounding.

**Related subsystem docs**

- [`./cognitive.md`](./cognitive.md) — the engine that consumes the doctrine excerpt and calls the LLM.
- [`../../docs/APOLLO13_REPLAY_REPORT.md`](../../docs/APOLLO13_REPLAY_REPORT.md) — a worked replay showing doctrine and lesson records as they appeared in the LLM prompt.
