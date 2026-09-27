"""Sublab Medium - memory you choose: the compress command.

Same twelve scripted turns, run twice: uncompressed (resend the whole thread
every call) and compressed (on the <compress> command, replace the history
with one structured state object and continue from that).

Run as:
  python -m sublab_medium.chat_memory
  python -m sublab_medium.chat_memory --interactive
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATA = Path(__file__).resolve().parent.parent / "data"
MODEL = "gpt-5.6-luna"
COMPRESS_MARKER = "<compress>"


def client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env.")
    return OpenAI(api_key=key)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_records() -> list[dict]:
    return json.loads((DATA / "records.json").read_text(encoding="utf-8"))


def load_policy() -> dict:
    return json.loads((DATA / "policy.json").read_text(encoding="utf-8"))


def load_chat_script() -> dict:
    return json.loads((DATA / "chat_script.json").read_text(encoding="utf-8"))


def records_block(records: list[dict]) -> str:
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


def base_system_prompt(records: list[dict], policy: dict) -> str:
    return (
        "You are a helpful assistant for a university grant office, talking "
        "directly with an applicant in a chat. Answer naturally, in the "
        "language the applicant is writing in. Use the applicant records and "
        "policy below to answer questions about eligibility, missing "
        "documents, and amounts. Do not invent facts the applicant has not "
        "told you that are not in the records below.\n\n"
        f"Applicant records:\n{records_block(records)}\n\n"
        f"Policy:\n{policy_block(policy)}"
    )


# --------------------------------------------------------------------------
# Calling the model
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Compression
# --------------------------------------------------------------------------

COMPRESS_INSTRUCTION = """
Summarise this conversation so far into ONE JSON object, and output ONLY that
JSON object - no prose, no markdown fences.

The object must have exactly these fields:
  applicant_id: string or null - the applicant's id, or null if never stated
  topic: string - one short phrase for what this conversation is about
  facts: array of strings - things the APPLICANT stated (not things you worked out)
  decisions: array of strings - decisions made so far in this conversation
  constraints: array of strings - conditions on how/when something can happen
    (a day, a deadline, a requirement the applicant set)
  open_questions: array of strings - things asked and not yet answered
  language: string - the language the applicant has been writing in

Never invent a fact that was not actually said. Use empty arrays where
nothing applies - never omit a field.
""".strip()

REQUIRED_STATE_FIELDS = {
    "applicant_id": (str, type(None)),
    "topic": (str,),
    "facts": (list,),
    "decisions": (list,),
    "constraints": (list,),
    "open_questions": (list,),
    "language": (str,),
}


def validate_state(obj) -> tuple[bool, str | None]:
    if not isinstance(obj, dict):
        return False, "not a JSON object"
    extra = set(obj) - set(REQUIRED_STATE_FIELDS)
    if extra:
        return False, f"unexpected fields: {sorted(extra)}"
    missing = set(REQUIRED_STATE_FIELDS) - set(obj)
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    for field, types in REQUIRED_STATE_FIELDS.items():
        if not isinstance(obj[field], types):
            return False, f"field '{field}' has wrong type: {type(obj[field]).__name__}"
    for field in ("facts", "decisions", "constraints", "open_questions"):
        if not all(isinstance(x, str) for x in obj[field]):
            return False, f"field '{field}' must be a list of strings"
    return True, None


def compress(messages: list[dict]) -> dict:
    """Ask the model to summarise `messages` into the structured state."""
    result = call_model(messages + [{"role": "user", "content": COMPRESS_INSTRUCTION}])
    parsed, error = parse_json(result["text"])
    if parsed is not None:
        ok, verr = validate_state(parsed)
        if not ok:
            parsed, error = None, verr
    return {
        "state": parsed,
        "error": error,
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
    }


def state_to_message(state: dict) -> dict:
    """The one message that replaces the discarded turns."""
    return {
        "role": "system",
        "content": "Conversation state so far (compressed):\n"
                    + json.dumps(state, ensure_ascii=False),
    }


# --------------------------------------------------------------------------
# Running the scripted session
# --------------------------------------------------------------------------

def run_session(compress_enabled: bool, records: list[dict], policy: dict,
                 script: dict) -> dict:
    system_msg = {"role": "system", "content": base_system_prompt(records, policy)}
    messages = [system_msg]
    call_log = []

    for turn_text in script["conversation"]:
        if turn_text == COMPRESS_MARKER:
            if not compress_enabled:
                continue  # skipped entirely in the uncompressed run
            result = compress(messages)
            call_log.append({
                "turn": "<compress>",
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "ok": result["state"] is not None,
                "error": result["error"],
                "state": result["state"],
            })
            if result["state"] is not None:
                messages = [system_msg, state_to_message(result["state"])]
            # else: malformed summary - keep the existing history, don't swap it
            continue

        messages = messages + [{"role": "user", "content": turn_text}]
        result = call_model(messages)
        messages = messages + [{"role": "assistant", "content": result["text"]}]
        call_log.append({
            "turn": turn_text,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        })

    return {"messages": messages, "call_log": call_log}


def run_probes(session_messages: list[dict], probes: list[dict]) -> list[dict]:
    results = []
    for p in probes:
        probe_messages = session_messages + [{"role": "user", "content": p["question"]}]
        result = call_model(probe_messages)
        text_lower = result["text"].lower()
        retrieved = any(s.lower() in text_lower for s in p["expect_contains"])
        results.append({"id": p["id"], "reply": result["text"], "retrieved": retrieved})
    return results


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------

def print_call_log(label: str, call_log: list[dict]) -> int:
    print(f"\n=== {label}: per-call tokens ===")
    peak = 0
    for c in call_log:
        turn_repr = c["turn"] if len(c["turn"]) < 50 else c["turn"][:47] + "..."
        print(f"  in={c['input_tokens']:5d}  out={c.get('output_tokens', 0):5d}  {turn_repr}")
        peak = max(peak, c["input_tokens"])
    print(f"  peak input tokens: {peak}")
    return peak


def print_probe_results(label: str, results: list[dict]) -> None:
    print(f"\n=== {label}: probes ===")
    for r in results:
        status = "RETRIEVED" if r["retrieved"] else "LOST"
        print(f"  {r['id']} [{status}]: {r['reply'][:120]}")


def run_scripted_comparison() -> None:
    records = load_records()
    policy = load_policy()
    script = load_chat_script()

    print("\n########## UNCOMPRESSED RUN ##########")
    uncompressed = run_session(False, records, policy, script)
    peak_u = print_call_log("uncompressed", uncompressed["call_log"])
    probes_u = run_probes(uncompressed["messages"], script["probes"])
    print_probe_results("uncompressed", probes_u)

    print("\n########## COMPRESSED RUN ##########")
    compressed = run_session(True, records, policy, script)
    peak_c = print_call_log("compressed", compressed["call_log"])
    compress_entry = next(c for c in compressed["call_log"] if c["turn"] == "<compress>")
    print("\n  compressed state object:")
    print(json.dumps(compress_entry["state"], ensure_ascii=False, indent=2))
    probes_c = run_probes(compressed["messages"], script["probes"])
    print_probe_results("compressed", probes_c)

    print("\n########## SUMMARY ##########")
    print(f"  peak tokens uncompressed: {peak_u}")
    print(f"  peak tokens compressed:   {peak_c}")
    ru = sum(1 for r in probes_u if r["retrieved"])
    rc = sum(1 for r in probes_c if r["retrieved"])
    print(f"  probes retrieved uncompressed: {ru}/{len(probes_u)}")
    print(f"  probes retrieved compressed:   {rc}/{len(probes_c)}")


# --------------------------------------------------------------------------
# Interactive mode
# --------------------------------------------------------------------------

def run_interactive() -> None:
    records = load_records()
    policy = load_policy()
    system_msg = {"role": "system", "content": base_system_prompt(records, policy)}
    messages = [system_msg]
    last_tokens = None

    print("Interactive chat. Type 'compress' to compress, 'tokens' for the "
          "last call's cost, 'quit' to exit.")
    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text:
            continue
        if user_text.lower() == "quit":
            break
        if user_text.lower() == "tokens":
            if last_tokens:
                print(f"  last call: in={last_tokens['input_tokens']} "
                      f"out={last_tokens['output_tokens']}")
            else:
                print("  no call made yet")
            continue
        if user_text.lower() == "compress":
            result = compress(messages)
            last_tokens = {"input_tokens": result["input_tokens"],
                            "output_tokens": result["output_tokens"]}
            if result["state"] is not None:
                messages = [system_msg, state_to_message(result["state"])]
                print("  compressed OK. New state:")
                print(json.dumps(result["state"], ensure_ascii=False, indent=2))
            else:
                print(f"  compression FAILED ({result['error']}) - history kept")
            continue

        messages = messages + [{"role": "user", "content": user_text}]
        result = call_model(messages)
        messages = messages + [{"role": "assistant", "content": result["text"]}]
        last_tokens = {"input_tokens": result["input_tokens"],
                        "output_tokens": result["output_tokens"]}
        print(f"bot: {result['text']}")


if __name__ == "__main__":
    if "--interactive" in sys.argv:
        run_interactive()
    else:
        run_scripted_comparison()