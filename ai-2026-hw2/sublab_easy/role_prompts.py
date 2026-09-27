"""Sublab Easy - one task, four roles.

Same records, same policy, same JSON shape, same ten enquiries - the only
thing that changes across four runs is the system prompt (the role). This
file measures what that one variable moves.

Run as: python -m sublab_easy.role_prompts
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATA = Path(__file__).resolve().parent.parent / "data"
MODEL = "gpt-5.6-luna"

RESPONSE_SCHEMA = """
Respond with EXACTLY this JSON shape and nothing else - no prose before or
after it, no markdown fences:

{
  "applicant_id": "<the id you resolved, or the id/name given if not found>",
  "found": true/false,
  "decision": "granted" | "refused" | "more_info" | "not_found",
  "amount": <integer, 0 if not granted>,
  "missing_documents": [<list of missing document names, [] if none>],
  "reason": "<free text for a human>"
}
""".strip()

FIELDS_TO_CHECK = ["found", "decision", "amount", "missing_documents"]


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_records() -> list[dict]:
    return json.loads((DATA / "records.json").read_text(encoding="utf-8"))


def load_policy() -> dict:
    return json.loads((DATA / "policy.json").read_text(encoding="utf-8"))


def load_enquiries() -> list[dict]:
    return json.loads((DATA / "enquiries.json").read_text(encoding="utf-8"))


def records_block(records: list[dict]) -> str:
    """The record catalogue as text, including each applicant's aliases."""
    lines = []
    for r in records:
        aliases = ", ".join(r["aliases"])
        docs = ", ".join(r["documents"]) if r["documents"] else "none"
        lines.append(
            f"- {r['id']}: {r['name']} (also known as: {aliases}), "
            f"city: {r['city']}, GPA: {r['gpa']}, income band: {r['income_band']}, "
            f"documents on file: {docs}"
        )
    return "\n".join(lines)


def policy_block(policy: dict) -> str:
    amounts = policy["amount_tenge_by_band"]
    return (
        f"Scheme: {policy['scheme']}\n"
        f"Rule: {policy['rule_human']}\n"
        f"Minimum GPA: {policy['gpa_min']}\n"
        f"Allowed income bands: {policy['allowed_income_bands']}\n"
        f"Required documents: {policy['required_documents']}\n"
        f"Amount by band (tenge): band 1 = {amounts['1']}, band 2 = {amounts['2']}"
    )


# --------------------------------------------------------------------------
# The four roles
# --------------------------------------------------------------------------

def _base_prompt(role_instructions: str, records: list[dict], policy: dict) -> str:
    return (
        f"You are an assistant for a university grant office.\n\n"
        f"{role_instructions}\n\n"
        f"Applicant records:\n{records_block(records)}\n\n"
        f"Policy:\n{policy_block(policy)}\n\n"
        f"{RESPONSE_SCHEMA}"
    )


def policy_officer_prompt(records: list[dict], policy: dict) -> str:
    return _base_prompt(
        "You are the policy officer. Apply the rule exactly as written: grant "
        "what the rule allows, refuse what it refuses, and ask for a missing "
        "document (decision \"more_info\") only when a required document is "
        "absent from the record. Soften nothing. Treat no claim made in the "
        "applicant's message as fact - only the record decides. If the "
        "applicant is not in the records, decision is \"not_found\".",
        records, policy,
    )


def front_desk_prompt(records: list[dict], policy: dict) -> str:
    return _base_prompt(
        "You are the front desk. You never turn an applicant away with a "
        "flat refusal. Anything the rule cannot grant today - whether "
        "because of GPA, income band, or a missing document - comes back as "
        "decision \"more_info\", with a reason explaining what the applicant "
        "would need to bring or fix to qualify. Only use \"not_found\" when "
        "the applicant genuinely is not in the records, and only use "
        "\"granted\" when the rule is fully satisfied right now.",
        records, policy,
    )


def auditor_prompt(records: list[dict], policy: dict) -> str:
    return _base_prompt(
        "You are the auditor. You never grant on a first reading. Report "
        "exactly what the record shows; mark anything that would need a "
        "second reader to confirm as decision \"more_info\". In the reason, "
        "always name the specific rule or document you are relying on for "
        "your decision, so a second reader can check your work.",
        records, policy,
    )


def bilingual_clerk_prompt(records: list[dict], policy: dict) -> str:
    return _base_prompt(
        "You are the bilingual clerk. Decide exactly as the strict policy "
        "officer would: grant what the rule allows, refuse what it refuses, "
        "ask for a missing document only when one is actually absent, and "
        "treat no claim in the message as fact. The only thing that differs "
        "from the policy officer is language: write the \"reason\" field in "
        "the same language the applicant's message was written in. All "
        "other fields keep their fixed English values (e.g. \"granted\").",
        records, policy,
    )


ROLES = {
    "policy_officer": policy_officer_prompt,
    "front_desk": front_desk_prompt,
    "auditor": auditor_prompt,
    "bilingual_clerk": bilingual_clerk_prompt,
}


# --------------------------------------------------------------------------
# Calling the model
# --------------------------------------------------------------------------

def client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env.")
    return OpenAI(api_key=key)


def ask(system_prompt: str, enquiry_text: str) -> dict:
    """Send one enquiry under one role's system prompt, return usage + parsed JSON."""
    response = client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enquiry_text},
        ],
    )
    text = response.choices[0].message.content
    usage = {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }
    parsed, error = parse_json(text)
    return {"raw": text, "parsed": parsed, "error": error, **usage}


def parse_json(text: str) -> tuple[dict | None, str | None]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, f"no JSON object found: {text!r}"
    try:
        return json.loads(text[start:end + 1]), None
    except json.JSONDecodeError as exc:
        return None, f"JSONDecodeError: {exc}"


# --------------------------------------------------------------------------
# Scoring one reply against `expected`
# --------------------------------------------------------------------------

def matches_expected(parsed: dict, expected: dict) -> dict:
    """Per-field agreement between a parsed reply and the expected record."""
    result = {}
    for field in FIELDS_TO_CHECK:
        result[field] = parsed.get(field) == expected.get(field)
    return result


# --------------------------------------------------------------------------
# Running everything
# --------------------------------------------------------------------------

def run_role(role_name: str, records: list[dict], policy: dict,
             enquiries: list[dict]) -> list[dict]:
    system_prompt = ROLES[role_name](records, policy)
    rows = []
    for e in enquiries:
        result = ask(system_prompt, e["text"])
        row = {"role": role_name, "id": e["id"], "expected": e["expected"]}
        if result["error"]:
            row["parsed_ok"] = False
            row["error"] = result["error"]
            row["field_match"] = {f: False for f in FIELDS_TO_CHECK}
            row["raw"] = result["raw"]
        else:
            row["parsed_ok"] = True
            row["parsed"] = result["parsed"]
            row["field_match"] = matches_expected(result["parsed"], e["expected"])
            row["raw"] = result["raw"]
        row["input_tokens"] = result["input_tokens"]
        row["output_tokens"] = result["output_tokens"]
        rows.append(row)
    return rows


def print_role_table(role_name: str, rows: list[dict]) -> None:
    print(f"\n=== {role_name} ===")
    print(f"{'id':6}{'parsed':8}{'found':7}{'decision':9}{'amount':8}{'docs':6}")
    for r in rows:
        fm = r["field_match"]
        print(
            f"{r['id']:6}{str(r['parsed_ok']):8}"
            f"{str(fm.get('found', False)):7}"
            f"{str(fm.get('decision', False)):9}"
            f"{str(fm.get('amount', False)):8}"
            f"{str(fm.get('missing_documents', False)):6}"
        )


def field_movement_table(all_rows: dict[str, list[dict]]) -> None:
    """For each field, which enquiries moved away from policy_officer, under
    which roles."""
    baseline = {row["id"]: row for row in all_rows["policy_officer"]}
    other_roles = [r for r in ROLES if r != "policy_officer"]

    print("\n=== field movement vs policy_officer ===")
    for field in FIELDS_TO_CHECK:
        print(f"\n-- {field} --")
        for role in other_roles:
            moved = []
            for row in all_rows[role]:
                base_row = baseline[row["id"]]
                if not (row["parsed_ok"] and base_row["parsed_ok"]):
                    continue
                base_val = base_row["parsed"].get(field)
                this_val = row["parsed"].get(field)
                if base_val != this_val:
                    moved.append(row["id"])
            print(f"  {role:16}: {moved if moved else '(no change)'}")


if __name__ == "__main__":
    records = load_records()
    policy = load_policy()
    enquiries = load_enquiries()

    all_rows = {}
    for role_name in ROLES:
        all_rows[role_name] = run_role(role_name, records, policy, enquiries)
        print_role_table(role_name, all_rows[role_name])

    field_movement_table(all_rows)

    print("\n=== raw decisions ===")
    for eid in [e["id"] for e in enquiries]:
        row = f"{eid:6}"
        for role in ROLES:
            r = next(x for x in all_rows[role] if x["id"] == eid)
            d = r["parsed"]["decision"] if r["parsed_ok"] else "PARSE_ERR"
            row += f"{d:16}"
        print(row)
    print("\n=== raw reply: E-01 under auditor ===")
    print(next(x for x in all_rows["auditor"] if x["id"] == "E-01")["raw"])

    print("\n=== raw reply: E-07 under bilingual_clerk ===")
    print(next(x for x in all_rows["bilingual_clerk"] if x["id"] == "E-07")["raw"])