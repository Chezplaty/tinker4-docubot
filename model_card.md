# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

> DocuBot answers developer questions about a small sample codebase by relying on the project's own Markdown/text documentation instead of the LLM's general training knowledge. It supports three modes so the same questions can be compared: asking the LLM directly with no context, doing pure keyword retrieval with no LLM, and combining retrieval with the LLM (RAG) so answers are grounded in and cite the actual docs.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> A user question (free text string), the contents of the `docs/` folder (`.md` and `.txt` files, loaded as filename/text pairs), and environment variables read from `.env`: `GEMINI_API_KEY` (required for modes 1 and 3) and an optional `docs_folder` path override.

**What outputs does DocuBot produce?**

> A single text answer. In retrieval-only mode this is the raw matched snippets labeled by filename. In naive and RAG mode it is the LLM's generated text, which in RAG mode is expected to name which files it relied on. Any mode can instead return the fixed refusal string `"I do not know based on these docs."` / `"...docs I have."` when there isn't enough evidence.

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> Indexing: every document is tokenized with a shared `_tokenize` helper — lowercase, split on whitespace, strip surrounding punctuation, and drop common stopwords (the, is, what, how, etc.) so they can't fake relevance. `build_index` produces an inverted index: `{word: {filenames that contain it}}`.
>
> Scoring: `score_document` tokenizes the query and the candidate text the same way, builds a `Counter` of the text's words, and sums up how many times each query word occurs in the text. Repeated mentions of a query word increase the score (term frequency), not just presence/absence.
>
> Choosing snippets: `retrieve` first uses the inverted index to cheaply find only the documents that contain at least one query word (instead of scoring every document), scores just those candidates, drops anything scoring 0, and sorts the rest descending. For each surviving document, `_extract_snippet` scores every *line* of that document by query-word overlap and returns only the top 5 lines (in original order) instead of the whole file, so retrieval returns focused excerpts.

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> Simplicity over semantic accuracy: this is pure bag-of-words keyword overlap with no stemming or synonym awareness, so a query using different wording than the docs (e.g. "log in" vs "authenticate") can under-match even when the docs cover the topic. Speed over completeness: using the index to pre-filter candidate documents keeps scoring cheap, but line-level snippet selection can strand a heading from its explanatory line if that line individually scores lower (see the failure cases below) — a small context window would be more complete but more expensive and noisier.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode:
- Retrieval only mode:
- RAG mode:

> Naive LLM mode calls only the LLM
> Retrievel mode uses no LLM, just documents
> RAG mode calls the LLM and uses documents as well

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> The RAG prompt tells the model it is a "cautious documentation assistant," shows it only the retrieved snippets (labeled by filename) plus the question, and gives three rules: (1) use only the information in the snippets — do not invent functions, endpoints, or configuration values; (2) if the snippets aren't enough to answer confidently, reply with the exact string `"I do not know based on the docs I have."` rather than guessing; (3) when it does answer, briefly say which files it relied on. `answer_from_snippets` also short-circuits to the refusal message before even calling the LLM if `retrieve()` returned zero snippets.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Harmful — gave a generic, fluent explanation of IdPs/Auth0/JWTs that has nothing to do with this codebase. | Helpful — surfaced the actual `AUTH.md`/`API_REFERENCE.md` lines about token generation and `AUTH_SECRET_KEY`. | Helpful — correctly answered that the token is generated by the login endpoint, citing `API_REFERENCE.md`. | Naive mode sounded confident despite being entirely inapplicable. |
| How do I connect to the database? | Harmful — gave generic multi-language DB connection tutorials (psycopg2, mysql2, JDBC) irrelevant to this app. | Helpful — surfaced the real `DATABASE_URL` variable and `db.py` module info. | Helpful — correctly synthesized `DATABASE_URL`, the SQLite fallback, and `db.py`, citing both `DATABASE.md` and `SETUP.md`. | RAG mode was the clear best here — concise and accurate. |
| Which endpoint lists all users? | Harmful — invented a generic `GET /users` REST example with fabricated JSON fields (`username`, `createdAt`, etc.) that don't exist in this app. | Helpful — surfaced the real line "Returns a list of all users. Only accessible to admins." | Helpful — gave a short, correct, cited answer. | Naive mode's fabricated example response is the kind of output a developer could mistakenly trust. |
| How does a client refresh an access token? | Harmful — described a generic OAuth refresh-token flow that never mentions this app's actual `/api/refresh` endpoint. | Helpful — surfaced `/api/refresh` and the token-expiry env var directly. | Not tested — hit a Gemini free-tier rate limit (429 RESOURCE_EXHAUSTED, 5 requests/min) during this run. | Retrieval alone already had the right answer; RAG likely would too based on the snippets shown. |
| What environment variables are required for authentication? | Harmful — listed unrelated conventions (OAuth, AWS, JWT_SECRET) not used by this app. | Helpful — surfaced `AUTH_SECRET_KEY` directly. | **Harmful (over-refusal)** — replied "I do not know based on the docs I have." even though `AUTH_SECRET_KEY` was plainly present in the shown snippet. | See Failure Case 1 below. |
| What does the /api/projects/<project_id> route return? | Harmful — fabricated a large JSON schema with invented fields (`budget`, `teamMembers`, `tags`). | Weak — only the section heading `### GET /api/projects/<project_id>` was selected, not the line describing what it returns. | Correct refusal given what it was shown, but only because retrieval failed to surface the descriptive line. | See Failure Case 2 below. |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

> Naive mode is impressive-but-untrustworthy on every query: it always produces long, fluent, well-structured answers, but since it's told to ignore the docs entirely, it fills in with generic industry knowledge and outright fabricates specifics (fake JSON fields, wrong auth providers, endpoints that don't exist here). It's the most dangerous mode precisely because it never sounds unsure.
>
> Retrieval only is clearly better whenever the answer is a short, literal sentence in the docs — it never hallucinates, but it dumps raw excerpts from multiple files and makes the user do the synthesis themselves.
>
> RAG is clearly best when retrieval surfaced the right lines — it turns those excerpts into a short, direct, cited answer. But RAG's honesty is double-edged: on the environment-variables query it refused even though the answer was sitting in the snippet, because the model wanted a complete list and only saw one variable named outright. Grounded caution can tip into being unhelpful when the model demands more certainty than the excerpt provides.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

> **Failure case 1 — over-refusal despite present evidence.** Question: "What environment variables are required for authentication?" The retrieved `AUTH.md` snippet included both "Internally, the token is signed using the secret stored in the `AUTH_SECRET_KEY` environment variable" and "The authentication system depends on two variables," but RAG mode still replied "I do not know based on the docs I have." What should have happened: the model had enough to name at least `AUTH_SECRET_KEY` confidently; the second variable's name was cut off by the 5-line snippet limit, but the prompt's "answer only if confident" instruction pushed the model to refuse entirely rather than answer partially with what it did know.

> **Failure case 2 — snippet extraction stranded a heading from its content.** Question: "What does the /api/projects/<project_id> route return?" Retrieval-only mode returned just the line `### GET /api/projects/<project_id>` with no body text, because that heading line literally repeats more of the query's words (the exact route string) than the actual descriptive sentence beneath it, so the heading outscored it in `_extract_snippet`'s line-by-line scoring and made the top-5 cut alone. RAG mode then correctly refused given only a bare heading — a reasonable response to what it was shown, but the real defect is upstream in retrieval, not in the LLM's judgment.

**When should DocuBot say "I do not know based on the docs I have"?**  
Give at least two specific situations.

> (1) When the query's meaningful (non-stopword) terms don't appear anywhere in the indexed documents at all — e.g. asking about payment processing or the weather, topics genuinely absent from these docs. (2) When retrieval returns snippets that are only tangentially related (a heading, a passing mention) and don't actually contain the specific fact being asked for, so answering would require guessing beyond what's shown.

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

> - Stopword filtering in `_tokenize` so common words like "the," "is," "what," and "how" can't manufacture false relevance matches.
> - `retrieve()` enforces a minimum-evidence threshold: any candidate document scoring 0 (no real keyword overlap) is dropped before it ever reaches the LLM.
> - Both `answer_retrieval_only` and `answer_rag` explicitly check for an empty snippet list and return a fixed "I do not know" message instead of calling the LLM at all.
> - The RAG prompt requires the model to answer using only the provided snippets, forbids inventing endpoints/functions/values, mandates the exact refusal string when unsure, and requires citing filenames when it does answer.
> - `top_k` (default 3) caps how many documents get surfaced per query, bounding both retrieval noise and LLM context size/cost.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. Pure keyword/bag-of-words matching with no synonym or stemming awareness — differently worded but semantically equivalent queries (e.g. "log in" vs "authenticate") can fail to match relevant docs.
2. Line-based snippet extraction can separate a heading from its explanatory content, since an isolated heading line can literally contain more matching keywords than the sentence describing it (observed directly in Failure Case 2).
3. No handling for LLM rate limits — the Gemini free tier's 5-requests-per-minute cap was hit during testing (`429 RESOURCE_EXHAUSTED`), and both naive and RAG mode simply surface the raw error string to the user with no retry/backoff.
4. Naive mode ignores the provided documents by design (a Phase 0 baseline), so its fluent, confident-sounding answers can be entirely inapplicable to this specific codebase if a user doesn't realize retrieval isn't happening in that mode.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Score snippets using a small window of surrounding lines around each match (not isolated single lines), so a heading's following content isn't lost the way it was in Failure Case 2.
2. Move from raw term-frequency scoring toward TF-IDF/BM25 so uncommon, specific terms are weighted more heavily than merely frequent ones.
3. Add retry-with-backoff for LLM rate-limit errors instead of surfacing the raw `429` message as the final answer.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> Naive mode's fabricated specifics (invented JSON fields, wrong auth providers, made-up endpoints) look just as confident as correct answers, so a developer who doesn't realize that mode ignores the docs could copy fake field names, environment variables, or endpoint paths straight into real code or configuration. Even RAG's cited answers should be spot-checked, since the model summarizes rather than quotes verbatim, and a missing citation isn't visually distinguished from a subtly wrong one. Retrieval-only mode surfaces raw doc text verbatim, so if `docs/` ever contained sensitive or outdated information, it would be exposed unfiltered.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Treat naive (mode 1) output as generic background knowledge only, never as fact about this specific codebase — it does not read the docs.
- Verify any file citations RAG gives you against the actual document before acting on them (e.g. before running a command or setting an env var).
- Treat "I do not know based on these docs" as a prompt to go read or improve the underlying documentation, not as a bug to route around.
- Keep `docs/` accurate and up to date — retrieval and RAG quality are both direct functions of documentation quality.

---
