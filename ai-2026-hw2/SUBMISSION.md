# HW2 submission

**Name: Dauletov Rakhat**
**Student ID: S23070384**
**Group: CSS4007-ENG-10**
**Repository:https://github.com/Yoroto-crypto/ai-2026-hw2**

## AI tool disclosure

> Used Claude (Anthropic) to help design and write the code for all three
> sublabs (prompts, extraction/validation logic, scoring pipeline), to debug
> environment/venv setup issues, and to help interpret my own run results.
> All written analysis below reflects my own numbers from my own runs.

---

## Sublab Easy — one task, four roles

### Decisions per role

| Enquiry | policy_officer | front_desk | auditor | bilingual_clerk |
|---|---|---|---|---|
| E-01 | granted ✓ | granted ✓ | more_info ✗ | granted ✓ |
| E-02 | more_info ✓ | more_info ✓ | more_info ✓ | more_info ✓ |
| E-03 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-04 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-05 | granted ✓ | granted ✓ | more_info ✗ | granted ✓ |
| E-06 | granted ✓ | granted ✓ | granted ✓ | granted ✓ |
| E-07 | granted ✓ | granted ✓ | more_info ✗ | granted ✓ |
| E-08 | not_found ✓ | not_found ✓ | not_found ✓ | not_found ✓ |
| E-09 | refused ✓ | more_info ✗ | refused ✓ | refused ✓ |
| E-10 | more_info ✓ | more_info ✓ | more_info ✓ | more_info ✓ |
| **agrees with `expected`** | 10/10 | 7/10 | 7/10 | 10/10 |
| **parsed** | 10/10 | 10/10 | 10/10 | 10/10 |
| **schema-valid** | 10/10 | 10/10 | 10/10 | 10/10 |

*(Disagreement with `expected` for front_desk and auditor is by design — each role deliberately softens/hardens the decision relative to the strict policy officer; it is reported as a result, not an error.)*

### Which field moved, on which enquiry, under which role

| Field | Enquiries that moved | Role(s) that moved it |
|---|---|---|
| `found` | none | no role moved this field |
| `decision` | E-03, E-04, E-09 (→ more_info) / E-01, E-05, E-07 (→ more_info) | front_desk (first group) / auditor (second group) |
| `amount` | E-01, E-05, E-07 | auditor |
| `missing_documents` | none | no role moved this field |

### Raw replies

Paste the full reply for **one enquiry where a role changed the decision** away
from the policy officer's:
```
{
"applicant_id": "A-201",
"found": true,
"decision": "more_info",
"amount": 0,
"missing_documents": [],
"reason": "The record shows GPA 3.4, income band 1, and both required documents (transcript and id_card), satisfying the Need-based study grant 2026 eligibility rule (minimum GPA 2.67, allowed bands 1 or 2, and required documents). Under the auditor rule, a grant is not issued on first reading; a second reader must confirm eligibility and the band 1 amount of 250,000 tenge."
}
```

Paste the full reply for **E-07 (the Kazakh enquiry)** from the bilingual
clerk, so the `reason` language is visible:
```
{
"applicant_id": "A-201",
"found": true,
"decision": "granted",
"amount": 250000,
"missing_documents": [],
"reason": "Сіз грант талаптарына сай келесіз: GPA 3.4, табыс санаты 1 және қажетті құжаттардың екеуі де бар."
}
```


### Written answers

**1. Which fields are role-sensitive and which are not?**

> `decision` and `amount` are role-sensitive: both moved under `auditor` (every "granted" case reverts to `more_info`, and amount drops to 0 with it), and `decision` also moved under `front_desk` (every "refused" case becomes `more_info`). `found` and `missing_documents` never moved under any role — facts about the applicant stay facts regardless of role; only what to do with them changes. `bilingual_clerk` is the role that moves only `reason`: it agrees with `policy_officer` on all 10 enquiries across all four structural fields.

**2. Which enquiries are most sensitive to the role, and why those?**

> E-03, E-04 (clear refusals: low GPA, disallowed income band) are the ones front_desk softens into `more_info`. E-07 (the Kazakh-language enquiry) shows no structural movement under any role — it tests language handling, not strictness: all four roles reach the same decision as on E-01 (same applicant, Aigerim), just bilingual_clerk answers in Kazakh. E-10 tests whether the bot accepts an unverified claim ("I uploaded my id card") as fact; policy_officer already correctly ignores it (`more_info`, still missing id_card) — auditor doesn't need to move it further here because policy_officer was already at its strictest possible outcome for this record.

**3. Where does discretion belong — the role paragraph, or code that reads `decision` afterwards?**

> The discretion (what counts as sufficient grounds to soften or harden a decision) lives in the role paragraph — it's the role text that decides whether a strict policy outcome gets converted to `more_info` or not. But a downstream program reading only the JSON reply cannot tell which role produced it — the response has no "role" field. If that distinction matters (e.g. `more_info` from front_desk vs. from policy_officer should be handled differently downstream), the role needs to become an explicit field in the response object itself, not stay only in the system prompt.

**4. Is a role a boundary?**

> No. Both `auditor` and `bilingual_clerk` are just different interpretations of the same underlying facts via different system-prompt text; neither blocks or verifies anything externally. In Week 2 terms — a system prompt is tokens continuing the same "document" as the rest of the context; the model has no stronger obligation to follow it than anything else in the input. If a wrong `decision` were expensive (real grant money), the boundary needs to be in code: a hard post-check like `if not (gpa >= policy["gpa_min"] and band in policy["allowed_income_bands"] and docs_complete): decision != "granted"`, applied to ANY model reply regardless of role, rather than trusting the role's wording.

---

## Sublab Medium — memory you choose

### Tokens per call

| Call | A — never compressed | B — compressed at the `compress` turn |
|---|---|---|
| 1 | in=588 out=39 | in=588 out=34 |
| 2 | in=649 out=138 | in=644 out=122 |
| 3 | in=740 out=119 | in=735 out=106 |
| 4 | in=834 out=33 | in=819 out=29 |
| 5 | in=888 out=136 | in=869 out=56 |
| 6 | in=981 out=51 | in=949 out=55 |
| 7 | in=1059 out=117 | in=1031 out=145 |
| 8 | in=1144 out=62 | in=1126 out=143 |
| 9 | in=1232 out=199 | in=1230 out=205 |
| 10 (`<compress>`) | — skipped entirely, not sent | in=1507 out=535 (the compress call itself) |
| 11 | in=1345 out=63 | in=835 out=50 |
| 12 | in=1422 out=26 | in=899 out=24 |
| **peak** | **1422** | **1507** |
| **total tokens (in+out) for the run** | **11865** | **12736** |

### Probes after the conversation

| Probe | Tests | A retrieved? | A answer | B retrieved? | B answer |
|---|---|---|---|---|---|
| Q-1 identity | turn 1 | ✓ | "You are Daniyar Qoshan (Данияр Қошан), applicant A-202." | ✓ | same |
| Q-2 missing document | turn 5 | ✓ | "Your ID card is still missing... transcript is already on record." | ✓ | "Your ID card is still missing from your file." |
| Q-3 band and amount | turns 3–4 | ✓ | "income band is 2... grant of 150,000 теңге" | ✓ | "income band is 2... 150,000 tenge" |
| Q-4 the constraint | turn 6 | ✓ | "You said you can come to the office on Thursdays." | ✓ | "You can come to the office on Thursdays." |
| Q-5 the open question | turn 7 | ✓ | "You asked whether a scanned letter from your employer would count..." | ✓ | "You asked whether a scanned employer letter could be used... not required..." |
| **retrieved** | | **5/5** | | **5/5** | |

### The state my compression produced

```json
{
  "applicant_id": "A-202",
  "topic": "Need-based study grant eligibility and document submission",
  "facts": [
    "The applicant's name is Daniyar Qoshan.",
    "The applicant sent their transcript last week.",
    "The applicant stated that their income band is 2 and that their family's certificate says so.",
    "The applicant could not upload their ID card because the scanner at home broke.",
    "The applicant can only come to the office on Thursdays because they have lab classes all week otherwise.",
    "The applicant stated that their sister Aruzhan applied last year and is on file."
  ],
  "decisions": [
    "The application currently does not qualify because the ID card is missing from the record.",
    "If the ID card is submitted and added to the record, the grant amount would be 150,000 tenge.",
    "A scanned employer letter is not required and cannot substitute for the ID card.",
    "The decision-making time after submitting the ID card is not specified."
  ],
  "constraints": [
    "The ID card must be received and added to the record for the application to qualify.",
    "The applicant can come to the office only on Thursdays."
  ],
  "open_questions": [],
  "language": "English"
}
```

### Written answers

**1. What did compression buy?**

> On just these 12 turns, compression cost MORE overall: total tokens 12736 (B) vs 11865 (A), and even the peak was higher (1507 vs 1422), because the compress call itself bundles the full 9-turn history plus a long instruction. But the shape of the cost differs: post-compression calls (turns 11, 12) dropped to 835/899 tokens versus 1345/1422 in the uncompressed run — nearly half. On a longer conversation than this 12-turn script, the compressed version would overtake the uncompressed one in total cost; here it hasn't had the chance to pay off yet. No probes were lost — 5/5 both ways.

**2. Why must the state be structured rather than a paragraph?**

> A named-field object lets the program validate mechanically (check all 7 fields exist with the right type, as `validate_state()` does) without ever reading the content — a free-text paragraph gives no way to programmatically detect "the model dropped a fact" versus "the model just phrased it more concisely." Named fields also separate categories that matter differently downstream: `open_questions` needs a follow-up, `constraints` needs to be respected in scheduling, `facts` is just context — a paragraph blurs all three into one undifferentiated blob.

**3. What is missing from your state that you would add?**

> I would add a token-cost-so-far or `last_updated_turn` field, to track how expensive the conversation has been cumulatively — useful for deciding when to compress again. I would consider dropping `topic` (a single descriptive phrase) to make room, since its content is largely redundant with the first entry in `facts`.

**4. When is compression the wrong choice?**

> If Daniyar had dictated an exact legal claim or dispute wording he wanted preserved verbatim (e.g., an exact quote for a formal appeal), compression would paraphrase it into `facts` as a summary, losing the precise wording that might matter. `validate_state()` only checks the SHAPE of the state (field names and types), not whether content was preserved — so the program would not notice this kind of loss at all.

---

## Sublab Hard — stories in, CVs out, the best candidate by code

### Part 1 — extraction

| Story | Parsed? | Valid? | Fields that came back `null` | Traps hit |
|---|---|---|---|---|
| story-01 | ✓ | ✓ | none (only empty `publications_other`) | none — clean record |
| story-02 | ✓ | ✓ | `graduation_year`, `gpa_4_scale` | no GPA stated |
| story-03 | ✓ | ✓ | none | GPA on another scale (5.0 → converted) |
| story-04 | ✓ | ✓ | none | paper not published (2 in prep, 1 under review) |
| story-05 | ✓ | ✓ | none | paper not published (1 unsubmitted); Kazakh source text |
| story-06 | ✓ | ✓ | `graduation_year`, `gpa_4_scale` | self-contradiction (GPA 3.2 vs 3.5; grad year 2024 vs 2026) |

Extraction for **story-06** (the one that contradicts itself):

```json
{
  "candidate_id": "story-06",
  "full_name": "Nurzhan Abilov",
  "degree": "BSc in Statistics",
  "graduation_year": null,
  "gpa_4_scale": null,
  "gpa_original": {
    "value": null,
    "scale": null
  },
  "languages": ["Kazakh", "Russian", "English"],
  "publications_published": [
    {
      "title": "Survey weighting",
      "evidence": "one paper published, in a peer-reviewed proceedings, on survey weighting"
    }
  ],
  "publications_other": [],
  "experience_months_total": 40,
  "experience_periods": [
    {
      "description": "Insurance analytics team; part-time for the first eight months, then full-time",
      "months": 40,
      "evidence": "I have been at an insurance analytics team since February 2023, which is about forty months. I was part-time for the first eight of those"
    }
  ],
  "ambiguities": [
    "Graduation year is contradictory: the story says the applicant graduated in 2024 and is currently a final-year student graduating in 2026.",
    "GPA is contradictory and unresolved: both 3.2 and 3.5 are stated, with uncertainty about which is correct.",
    "The publication's exact title is not stated; it is described only as being on survey weighting."
  ]
}
```

### Part 2 — scores and the winner

| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |
|---|---|---|---|---|
| story-01 | 5 | 5 | 2 | **4.4** |
| story-02 | 1 | 2.5 | 5 | 2.25 |
| story-03 | 4 | 3 | 3 | 3.5 |
| story-04 | 4 | 2.5 | 5 | 3.75 |
| story-05 | 5 | 2.5 | 1.25 | 3.5 |
| story-06 | 1 | 2.5 | 5 | 2.25 |

**Winner, computed by my code:** story-01 (Aziza Bekova), 4.4

**The model's prose answer, asked separately ("who should win?"):**

> "I think Aziza Bekova (story-01) should win. She has a strong stated academic record (3.8/4.0 GPA), the strongest research profile with two published peer-reviewed outputs, and some directly relevant data experience. Although her experience totals only eight months, her combination of excellent academics and the highest publication record gives her the strongest overall fit under the rubric."

### Part 3 — written answers

**1. Which rule did you have to add, and what broke without it?**

> The "do not resolve, do not average contradictions" rule was decisive for story-06: without it, the model could have averaged 3.2 and 3.5 into 3.35, or picked the later-stated figure, either of which would have hidden the fact that the source genuinely contradicts itself. With the rule, both `gpa_4_scale` and `graduation_year` correctly came back `null`, with the contradiction logged in `ambiguities`.

**2. Where did the model guess, and where did your code have to decide?**

> The model exercised judgment in the SCORING step — e.g. giving Aisha (story-05, 6 months) a lower experience score (1.25) than Lyazzat (story-03, 5 months, score 3) is not strictly monotonic in months alone, meaning the model weighs more than raw duration when interpreting the 0-5 scale. My code made the deterministic decision in the RANKING step: the weighted-sum formula and the sort by total are entirely in `weighted_total()`/`rank_candidates()` — the model never sees or influences that computation, and story-02/story-06 tying exactly at 2.25 shows the formula being applied mechanically rather than judged.

**3. Did your prose ranking and your computed ranking agree?**

> Yes — both independently picked story-01 (Aziza) as the winner, citing the same reasoning (published papers, high GPA). Since they agreed here, before trusting the prose-only judgment alone on a less clear-cut set of candidates, I would want to see the full score breakdown and margin from the prose call as well, not just a name — a prose answer can agree by coincidence on an easy case without reliably tracking a formula on a closer one.

**4. The rubric has no anchor for a contradicted field.**

> I set the field to `null` and logged the contradiction in `ambiguities`, which the scoring step effectively treated as weak evidence (story-06 scored only 1/5 on academic despite claiming a completed degree). I think the rubric should explicitly state that a contradicted field scores no better than a missing one on that sub-criterion — right now this is left entirely to the scoring model's own judgment, and different runs could plausibly score it differently (my own two runs gave story-06 academic scores of 1 and 2 across attempts).

**5. How close were your top two candidates?**

> 4.4 (story-01) vs 3.75 (story-04) — a gap of 0.65, well outside the 0.05 "too close to call" threshold. Because the gap is large, I would tell the committee the result is clear-cut and doesn't need a manual tie-break. Had it been close, `experience` would be the first criterion I'd scrutinize — it showed the least consistent behavior across my two runs of this assignment (research and academic scores shifted by 0.5-1 point between runs) and is the criterion most vulnerable to inconsistent model judgment run-to-run.

---

## Reflection (optional, one short paragraph)

> Having now written a role prompt, compressed a conversation, and ranked six extractions — the main lesson was that reliability comes from splitting "what the model decides" from "what the code decides" as narrowly as possible: the model gives raw scores or raw facts, and code does every arithmetic, ranking, or policy-threshold check on top of that. Re-running the same sublabs twice and seeing scores shift by half a point reinforced this — anything the model outputs as a free-floating number should be treated as noisy, and only computations done in code are reproducible. Next time I build something needing structured output, I'd push even sub-decisions (like a 0–5 experience score) toward more concrete inputs — e.g. asking for months-worked-per-period rather than a pre-digested score — so more judgment moves out of the model and into code I can inspect and reproduce.