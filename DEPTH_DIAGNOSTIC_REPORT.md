# Depth Diagnostic Report

## Objective

Analyze the complete `grok-research-agent` workflow to determine why `FINAL_REPORT.md` is overly simplified and excessively summarized even when the user selects and approves `all` options during testing.

## Executive Conclusion

The shallow final report is caused by a stack of compounding compression steps across the pipeline, not by user approval behavior.

Even when the user chooses `all`, the system still loses detail because:

1. Source discovery is under-specified and may return too few or too broad sources.
2. HTML content is reduced through a readability summary before extraction.
3. Long source content is hard-truncated before the model sees it.
4. Extractions ask only for "key information" instead of exhaustive retention.
5. The notebook step collapses many extractions into grouped summaries.
6. The synthesis and final polish prompts are report-style and summary-oriented.
7. The final report generation does not use full-source copies or compiled knowledge-base artifacts.

In short: the system is architected as a multi-stage summarizer, not a detail-preserving research compiler.

## Why Selecting `all` Does Not Fix It

Selecting `all` only means:

- all discovered sources are curated
- all curated sources are eligible for extraction
- optionally all sources can be copied offline in Phase 6

It does **not** guarantee:

- the discovery phase found enough sources
- the full source text was retained
- the full source text was sent to the model
- the notebook preserved detailed evidence
- the final report consumed all retained material

By the time the system reaches `FINAL_REPORT.md`, it is operating on multiple layers of prior summaries and truncations.

## End-to-End Workflow Analysis

### 1. Discovery Is Optimized for Brevity, Not Coverage

**Code / prompt evidence**

- [discovery_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/discovery_prompt.txt)
- [workflow_phases.py:L373-L387](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L373-L387)

**Observed behavior**

- The prompt only asks for a "comprehensive discovery table" but does not require:
  - minimum source count
  - category quotas
  - canonical/primary sources first
  - exhaustive subtopic coverage
- The output schema includes a `Short TL;DR` column, which biases the model toward concise source descriptions rather than exhaustive enumeration.

**Impact on depth**

- If the model returns only a moderate number of sources, selecting `all` still yields an incomplete evidence base.
- There is no enforcement that discovery includes enough official documentation, papers, implementation writeups, benchmarks, critiques, and design discussions.

**Required modification**

- Add explicit coverage constraints:
  - minimum total sources, e.g. 25-40
  - minimum quotas by source type
  - required subtopic checklist
  - instruction to prefer primary sources over derivative summaries

## 2. Curation UX Hides Potentially Large Source Sets

**Code evidence**

- [workflow_phases.py:L389-L427](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L389-L427)

**Observed behavior**

- The terminal preview shown to the user is limited to the first 20 non-empty lines:
  - `preview = "\n".join(lines[:20])`

**Impact on depth**

- This does not truncate the data passed to Grok for curation, but it reduces human visibility into the discovery set.
- A user may approve `all` without seeing whether discovery was broad or weak.

**Severity**

- Medium UX issue, not the main content-loss cause.

**Required modification**

- Show the full table paginated or save and open the full discovery table before approval.
- Add a count summary: total sources, by type, by date, by domain.

## 3. HTML Is Compressed Before Extraction

**Code evidence**

- [workflow_phases.py:L436-L442](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L436-L442)

**Observed behavior**

- HTML pages are passed through:

```python
doc = Document(resp.text)
return doc.summary(html_partial=True)
```

**Impact on depth**

- `readability.Document.summary()` is itself a lossy reduction step.
- Non-primary sections often disappear:
  - appendices
  - tables
  - code snippets
  - footnotes
  - sidebars
  - structured metadata
  - headings outside the main body
- The extractor then receives an already compressed representation rather than the full page text.

**Severity**

- High. This is one of the earliest hard detail-loss points.

**Required modification**

- Preserve both:
  - raw fetched content
  - cleaned plain text version
- Prefer a full-text extraction path rather than `summary()`.
- Store source snapshots before any summarization.

## 4. Source Content Is Hard-Truncated Before Extraction

**Code evidence**

- [workflow_phases.py:L477-L495](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L477-L495)

**Observed behavior**

- The extraction model input is truncated:

```python
{"topic": ctx.state.topic, "title": title, "url": url, "content": raw[:200000]}
```

**Impact on depth**

- Long documents are silently cut off.
- Everything after the first 200,000 characters is never seen by the extractor.
- This especially hurts:
  - long technical docs
  - RFC-style documents
  - papers with long appendices
  - benchmark/result sections
  - implementation details later in the document

**Severity**

- High.

**Required modification**

- Replace single-pass truncation with chunked extraction.
- Extract per section / per chunk and merge.
- Track chunk provenance so later stages know what evidence came from where.

## 5. Extraction Prompt Explicitly Requests Compressed "Key Information"

**Prompt evidence**

- [extraction_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/extraction_prompt.txt)

**Observed behavior**

- The instruction is:
  - "Extract key information from the content below."
- Output sections are limited to a small number of top-level buckets:
  - Key Definitions
  - Key Components / Architecture
  - Quotes
  - Limitations / Critiques
  - Diagram Descriptions
  - Notes

**Impact on depth**

- The model is encouraged to summarize salient ideas rather than preserve detailed evidence.
- No instruction requires:
  - exhaustive claims
  - all important mechanisms
  - all experimental results
  - all tradeoffs
  - all cited numbers
  - section-by-section retention
  - ambiguity markers
- Quotes are optional and not density-controlled.

**Severity**

- High.

**Required modification**

- Redesign extraction prompt to require:
  - exhaustive section coverage
  - evidence tables
  - concrete claims with citations
  - numeric facts, examples, comparisons, caveats
  - unknown/missing areas
- Add minimum output richness rules.

## 6. Notebook Phase Re-Summarizes All Extractions

**Code evidence**

- [workflow_phases.py:L498-L516](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L498-L516)

**Observed behavior**

- The notebook input is merged and truncated:

```python
merged = "\n\n---\n\n".join(extracted_parts)
{"topic": ctx.state.topic, "extractions": merged[:220000]}
```

- The notebook prompt asks for grouped sections, contradictions, and cross references:
  - [notebook_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/notebook_prompt.txt)

**Impact on depth**

- This is a second major compression pass.
- Even if individual extractions are detailed, the notebook prompt asks Grok to merge them into thematic groups.
- Grouping collapses per-source nuance and can destroy traceability.
- The truncation means some extractions may not reach notebook generation at all.

**Severity**

- Critical. This is the strongest architectural reason the final report becomes shallow.

**Required modification**

- Do not use one monolithic merged prompt for all extractions.
- Build the notebook incrementally:
  - one section at a time
  - one topic cluster at a time
  - preserve source-indexed evidence blocks
- Add appendices or evidence ledgers instead of replacing raw extraction detail.

## 7. Synthesis Prompt Is Explicitly Executive-Summary Oriented

**Code evidence**

- [workflow_phases.py:L518-L530](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L518-L530)

**Prompt evidence**

- [synthesis_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/synthesis_prompt.txt)

**Observed behavior**

- Notebook is truncated again:

```python
{"topic": ctx.state.topic, "notebook": notebook_path.read_text(encoding="utf-8")[:240000]}
```

- Prompt requires:
  - Executive summary
  - TOC
  - Draft sections
  - References

**Impact on depth**

- "Executive summary" framing strongly biases concise synthesis.
- No minimum length, section depth, citation density, or appendix requirements.
- No rule says: preserve all important mechanisms, edge cases, failures, examples, or competing interpretations.

**Severity**

- High.

**Required modification**

- Split synthesis into:
  - detailed technical body
  - executive summary as separate derived section
- Add explicit output contract for depth:
  - required subsections
  - minimum citation density
  - evidence-backed claims
  - dedicated deep-dive appendices

## 8. Final Polish Is Another Compression Pass

**Code evidence**

- [workflow_phases.py:L630-L649](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L630-L649)

**Prompt evidence**

- [final_polish_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/final_polish_prompt.txt)

**Observed behavior**

- Both notebook and draft are truncated:

```python
"notebook": notebook_path.read_text(encoding="utf-8")[:180000],
"draft": latest_draft[:180000],
```

- Prompt only asks for:
  - TOC
  - Inline citations
  - Reference list
  - Glossary

**Impact on depth**

- Final polish has no instruction to expand the draft.
- It is effectively formatting and light summarization, not content enrichment.
- Since the inputs are already compressed, the final report becomes a polished summary of a summary of a summary.

**Severity**

- Critical.

**Required modification**

- Final stage should assemble, not compress:
  - combine structured sections
  - preserve evidence-rich appendices
  - include source-by-source notes as annexes
- Remove the assumption that final polish should operate on truncated notebook + truncated draft only.

## 9. Full Offline Collection Happens Too Late To Help the Report

**Code evidence**

- [workflow_phases.py:L565-L628](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L565-L628)

**Observed behavior**

- Full offline source capture is Phase 6.
- Final report quality depends on extraction, notebook, and synthesis completed earlier.
- If user chooses `none`, finalization proceeds immediately.
- Even if user chooses `all`, these saved full copies are not fed back into synthesis/final polish.

**Impact on depth**

- The richest raw material is collected after most reasoning is already finished.
- Therefore Phase 6 does not materially deepen the report.

**Severity**

- High architectural issue.

**Required modification**

- Move full-content retention earlier:
  - before extraction or during extraction
- Allow Phase 6 assets to trigger notebook and synthesis regeneration.

## 10. Knowledge Compilation Outputs Are Not Used by the Final Report

**Code evidence**

- CLI routes `compile`, `drill`, `show` as separate commands:
  - [cli.py:L113-L130](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/cli.py#L113-L130)
- Structured outputs are produced separately:
  - [workflow_phases.py:L186-L237](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L186-L237)

**Observed behavior**

- `compile` creates:
  - `hypergraph.json`
  - `core_concepts.json`
- `drill` creates:
  - `drill_pack.md`
- But the main report workflow does not consume these files when generating `FINAL_REPORT.md`.

**Impact on depth**

- The structured knowledge system exists in parallel, not in the final report pipeline.
- Richer graph/core-concept representations do not improve the report body.

**Severity**

- High.

**Required modification**

- Feed `knowledge_base` artifacts into notebook, synthesis, and final polish.
- Use hypergraph/core concepts to enforce topic coverage and concept completeness.

## 11. No Chunking, No Iterative Expansion, No Evidence Ledger

**Code evidence**

- Hard slices across pipeline:
  - [workflow_phases.py:L490](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L490)
  - [workflow_phases.py:L512](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L512)
  - [workflow_phases.py:L528](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L528)
  - [workflow_phases.py:L643-L644](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L643-L644)

**Observed behavior**

- The system repeatedly solves context-window pressure by cutting off content.
- There is no:
  - chunk map
  - retrieval index
  - iterative section expansion
  - evidence ledger
  - appendix generation from overflow material

**Impact on depth**

- Detail loss is guaranteed as corpus size grows.
- Long, multi-source topics will always collapse toward summary.

**Severity**

- Critical architectural limitation.

**Required modification**

- Introduce:
  - chunked ingestion
  - per-chunk extraction
  - source evidence store
  - section-level synthesis
  - final assembly step

## 12. Output Formatting Rules Encourage Compactness

**Prompt evidence**

- [synthesis_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/synthesis_prompt.txt)
- [final_polish_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/final_polish_prompt.txt)

**Observed behavior**

- Neither prompt defines:
  - target word count
  - target section length
  - minimum examples per section
  - minimum number of citations per section
  - required appendix content

**Impact on depth**

- The model defaults to concise, well-structured summaries.
- Markdown formatting without explicit depth constraints tends toward shorter outputs.

**Severity**

- Medium to High, depending on topic size.

**Required modification**

- Add explicit output budgets and required section granularity.

## 13. Tests Validate Control Flow, Not Report Depth

**Code evidence**

- [test_workflow_happy_path.py:L41-L118](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/tests/test_workflow_happy_path.py#L41-L118)
- [test_workflow_happy_path.py:L168-L247](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/tests/test_workflow_happy_path.py#L168-L247)

**Observed behavior**

- Test fixtures intentionally use tiny fake outputs:
  - extraction: `"## Key Definitions\nX\n## Notes\nY"`
  - notebook: `"# Notebook\nMerged"`
  - draft: `"# Draft..."`
  - final: `"# Final..."`

**Impact on depth**

- The tests confirm phase wiring and file creation only.
- They cannot detect:
  - detail loss
  - shallow synthesis
  - citation sparsity
  - appendix omissions
  - premature truncation side effects

**Severity**

- Medium, but important for regression protection.

**Required modification**

- Add quality-oriented tests:
  - long multi-source inputs
  - section preservation checks
  - citation density checks
  - appendix preservation checks

## Root Cause Ranking

### Critical

1. Repeated hard truncation across extraction, notebook, synthesis, and final polish
2. Notebook stage collapsing all extractions into grouped summaries
3. Final polish operating on already-compressed inputs
4. No chunking / iterative assembly architecture

### High

5. Readability summary discarding source detail before extraction
6. Extraction prompt asking only for "key information"
7. Synthesis prompt oriented around executive-summary style writing
8. Full offline collection happening too late to influence report quality
9. Knowledge-base artifacts not integrated into final report generation

### Medium

10. Discovery prompt lacks explicit source-count and coverage constraints
11. Curation preview hides most of discovery from user inspection
12. Tests do not measure report richness

## Specific Code and Parameter Changes Recommended

### A. Replace Single-Pass Truncation With Chunked Processing

Files:

- [workflow_phases.py](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py)

Change:

- Replace all `[:N]` prompt slicing for core report generation with chunked ingestion + iterative synthesis.

Current truncation points to remove or redesign:

- [workflow_phases.py:L490](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L490)
- [workflow_phases.py:L512](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L512)
- [workflow_phases.py:L528](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L528)
- [workflow_phases.py:L643-L644](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L643-L644)

### B. Preserve Full Source Text Earlier

File:

- [workflow_phases.py:L436-L442](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L436-L442)

Change:

- Store raw response text and cleaned full text.
- Avoid `Document.summary()` as the only source body.

### C. Redesign Extraction Prompt for Exhaustive Retention

File:

- [extraction_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/extraction_prompt.txt)

Change:

- Replace "Extract key information" with a detailed extraction contract.
- Require:
  - section-by-section coverage
  - numbered factual claims
  - quotes with context
  - examples
  - implementation details
  - metrics/results
  - unresolved issues

### D. Make Notebook a Structured Evidence Store, Not a Summary Layer

Files:

- [workflow_phases.py:L498-L516](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L498-L516)
- [notebook_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/notebook_prompt.txt)

Change:

- Generate notebook sections incrementally.
- Preserve source-attributed evidence blocks.
- Add appendices or per-source annexes.

### E. Separate Executive Summary From Full Technical Report

Files:

- [synthesis_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/synthesis_prompt.txt)
- [final_polish_prompt.txt](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/prompts/final_polish_prompt.txt)

Change:

- Make executive summary optional and derived.
- Require the main body to be exhaustive.
- Add mandatory deep-dive sections and appendices.

### F. Feed Structured Knowledge Back Into the Main Report

Files:

- [cli.py:L113-L130](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/cli.py#L113-L130)
- [workflow_phases.py:L186-L237](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/grok_research_agent/workflow_phases.py#L186-L237)

Change:

- Use `hypergraph.json` and `core_concepts.json` during synthesis and final polish.
- Check final report completeness against core concepts and graph coverage.

## Recommended Target Architecture

To produce thorough, complete documentation, the workflow should become:

1. Discover many high-quality sources with coverage constraints
2. Capture raw/full source text before summarization
3. Chunk long sources
4. Extract detailed evidence per chunk
5. Merge chunk outputs into source dossiers
6. Build notebook as a structured evidence repository
7. Generate report section-by-section from notebook + source dossiers + knowledge graph
8. Assemble final report with appendices and evidence annexes
9. Run completeness checks against required concepts and citations

## Bottom Line

The final report is shallow because the system repeatedly compresses information at nearly every stage and never performs a detail-preserving re-expansion step.

The most important fixes are:

1. remove truncation-first design
2. stop using readability summary as the only HTML representation
3. redesign extraction to preserve evidence, not just "key points"
4. turn notebook/synthesis/final-polish into section-wise assembly instead of repeated summarization
5. integrate the knowledge-base outputs into report generation

Until those changes are made, the system will continue to produce polished but overly summarized reports, even when all sources are selected and approved.
