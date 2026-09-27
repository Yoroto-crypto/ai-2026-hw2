"""Sublab Hard - stories in, CVs out, the best candidate by code.

Three stages:
  1. extract a structured CV from each unstructured story
  2. ask the model for a 0-5 score per rubric criterion (nothing else)
  3. compute the weighted total and the winner IN CODE, not in the model

Run as: python -m sublab_hard.cv_extract_and_rank
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATA = Path(__file__).resolve().parent.parent / "data"
CANDIDATES_DIR = DATA / "candidates"
MODEL = "gpt-5.6-luna"


def client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env.")
    return OpenAI(api_key=key)


def call_model(messages: list[dict]) -> dict:
    response = client().chat.completions.create(model=MODEL, messages=messages)
    return {
        "text": response.choices[0].message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def parse_json(text: str) -> tuple[dict | None, str | None]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, f"no JSON object found: {text!r}"
    try:
        return json.loads(text[start:end + 1]), None
    except json.JSONDecodeError as exc:
        return None, f"JSONDecodeError: {exc}"


def load_rubric() -> dict:
    return json.loads((DATA / "candidate_rubric.json").read_text(encoding="utf-8"))


def load_candidates() -> list[dict]:
    files = sorted(CANDIDATES_DIR.glob("story-*.md"))
    return [
        {"id": f.stem, "path": f, "text": f.read_text(encoding="utf-8")}
        for f in files
    ]


# --------------------------------------------------------------------------
# Part 1: extract a CV from each story
# --------------------------------------------------------------------------

EXTRACTION_PROMPT = """
You will read one scholarship applicant's written story and extract a
structured CV from it. Output ONLY a JSON object with exactly this shape - no
prose, no markdown fences:

{
  "candidate_id": "<the file name, given to you below>",
  "full_name": "<string or null>",
  "degree": "<string or null>",
  "graduation_year": <integer or null>,
  "gpa_4_scale": <number or null>,
  "gpa_original": {"value": <number or null>, "scale": "<string or null>"},
  "languages": [<list of strings>],
  "publications_published": [
    {"title": "<string>", "evidence": "<short quote from the story>"}
  ],
  "publications_other": [
    {"title": "<string>", "status": "<submitted|under_review|in_preparation|in_press|other>", "evidence": "<short quote>"}
  ],
  "experience_months_total": <integer or null>,
  "experience_periods": [
    {"description": "<string>", "months": <integer or null>, "evidence": "<short quote>"}
  ],
  "ambiguities": [<list of short strings describing any contradiction or unresolved gap you found>]
}

Rules - follow these exactly, they are checked:

- A fact the story does not state is null. NEVER estimate or infer a missing
  value (e.g. no GPA stated -> gpa_4_scale is null, do not guess one from the
  degree or the tone of the letter).
- If the GPA is given on a scale other than 4.0, convert it to a 4.0 scale
  for "gpa_4_scale" AND record the original value and scale in "gpa_original".
  If the story gives no GPA at all, both gpa_4_scale and gpa_original.value
  are null.
- A publication counts as "published" ONLY when the story explicitly says it
  is published or accepted. Anything described as "submitted", "under
  review", "in preparation", "planned" or "in press" goes in
  "publications_other" with the matching status, NOT in
  "publications_published".
- Count experience in months. Overlapping periods count once, not twice. A
  period with no stated dates/duration is not countable towards
  experience_months_total - list it in experience_periods with months: null,
  and note it in ambiguities.
- If the story contradicts itself on any field (e.g. two different GPA
  figures, two different graduation years), do NOT resolve it and do NOT
  average it: set that field to null, and describe the contradiction in
  "ambiguities".
- Every field you fill with a real value must be traceable to a quote from
  the story, given in "evidence".

Candidate id: __CANDIDATE_ID__

Story:
__STORY_TEXT__
""".strip()


def extract_cv(candidate_id: str, story_text: str) -> dict:
    prompt = (EXTRACTION_PROMPT
          .replace("__CANDIDATE_ID__", candidate_id)
          .replace("__STORY_TEXT__", story_text))
    result = call_model([{"role": "user", "content": prompt}])
    parsed, error = parse_json(result["text"])
    return {
        "cv": parsed,
        "error": error,
        "raw": result["text"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }


def extract_all(candidates: list[dict]) -> dict[str, dict]:
    return {c["id"]: extract_cv(c["id"], c["text"]) for c in candidates}


# --------------------------------------------------------------------------
# Part 2: score (model), rank (code)
# --------------------------------------------------------------------------

SCORING_PROMPT = """
Score this candidate's CV against the rubric below. Output ONLY this JSON
object - no prose:

{{"academic": <0-5>, "research": <0-5>, "experience": <0-5>}}

Do not compute a weighted total or a rank - that is not your job. Just the
three scores.

Rubric:
{rubric}

Candidate CV:
{cv}
""".strip()


def score_cv(cv: dict, rubric: dict) -> dict:
    prompt = SCORING_PROMPT.format(
        rubric=json.dumps(rubric, ensure_ascii=False, indent=2),
        cv=json.dumps(cv, ensure_ascii=False, indent=2),
    )
    result = call_model([{"role": "user", "content": prompt}])
    parsed, error = parse_json(result["text"])
    return {
        "scores": parsed,
        "error": error,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }


def weighted_total(scores: dict, rubric: dict) -> float:
    weights = {c["id"]: c["weight"] for c in rubric["criteria"]}
    total = (
        weights["academic"] * scores["academic"]
        + weights["research"] * scores["research"]
        + weights["experience"] * scores["experience"]
    )
    return round(total, 2)


def rank_candidates(all_scores: dict[str, dict], rubric: dict) -> list[tuple[str, float]]:
    totals = [
        (cid, weighted_total(s["scores"], rubric))
        for cid, s in all_scores.items()
        if s["scores"] is not None
    ]
    return sorted(totals, key=lambda x: x[1], reverse=True)


# --------------------------------------------------------------------------
# Prose ranking, for comparison - a SEPARATE call, not used for the winner
# --------------------------------------------------------------------------

PROSE_RANKING_PROMPT = """
Here are six scholarship candidates' extracted CVs and the rubric used to
judge them. In prose, say which candidate you think should win the funded
place, and briefly why. This is your opinion only - it will be compared
against a score computed separately, not used to pick the winner.

Rubric:
{rubric}

Candidates:
{cvs}
""".strip()


def prose_ranking(all_cvs: dict[str, dict], rubric: dict) -> dict:
    cvs_text = json.dumps(
        {cid: c["cv"] for cid, c in all_cvs.items() if c["cv"]},
        ensure_ascii=False, indent=2,
    )
    prompt = PROSE_RANKING_PROMPT.format(
        rubric=json.dumps(rubric, ensure_ascii=False, indent=2), cvs=cvs_text
    )
    result = call_model([{"role": "user", "content": prompt}])
    return {"text": result["text"], "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"]}


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------

def print_extraction_table(all_cvs: dict[str, dict]) -> None:
    print("\n=== Part 1: extraction ===")
    for cid, entry in all_cvs.items():
        print(f"\n-- {cid} --")
        if entry["error"]:
            print(f"  FAILED TO PARSE: {entry['error']}")
            continue
        cv = entry["cv"]
        null_fields = [k for k, v in cv.items() if v in (None, [], "")]
        print(f"  parsed OK. null/empty fields: {null_fields}")
        print(f"  ambiguities: {cv.get('ambiguities')}")
        if cid == "story-06":
            print(json.dumps(cv, ensure_ascii=False, indent=2))


def print_ranking(all_scores: dict[str, dict], rubric: dict) -> None:
    print("\n=== Part 2: scores and computed ranking ===")
    for cid, s in all_scores.items():
        print(f"  {cid}: {s['scores']}")
    print("\n  ranking (computed in code):")
    for rank, (cid, total) in enumerate(rank_candidates(all_scores, rubric), start=1):
        print(f"  {rank}. {cid}: {total}")


if __name__ == "__main__":
    rubric = load_rubric()
    candidates = load_candidates()

    all_cvs = extract_all(candidates)
    print_extraction_table(all_cvs)

    all_scores = {
        cid: score_cv(entry["cv"], rubric)
        for cid, entry in all_cvs.items() if entry["cv"] is not None
    }
    print_ranking(all_scores, rubric)

    print("\n=== Part 2: prose ranking (separate call, for comparison) ===")
    prose = prose_ranking(all_cvs, rubric)
    print(prose["text"])