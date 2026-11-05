# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "certifi", "pillow"]
# ///
"""Can an open model see what D5 misses? Two closed questions, each bar
shown alone at 100 px a staff space (zoom.py), against the edition's final
notes: how many grace notes, and how many stems carry two heads (a double
stop or chord).

    VLLM_API_KEY=<key> uv run experiments/llm/see_test.py <edition-copy> <edition> \\
        --url https://<app>.modal.run/v1 --model google/gemma-4-31B-it
    uv run experiments/llm/see_test.py <edition-copy> <edition> --model claude-opus-5-5 [--effort high]

The bars: every bar of the run's movement with a grace note or a chord in
the final notes, and --negatives bars with neither. Counted per question:
bars where there is one and the model says so (and among them those D5
missed), and bars where there is none and the model says there is.
Writes <edition-copy>/build/see-<model>.jsonl.
"""

import argparse
import base64
import json
import os
import random
import re
import ssl
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sys

import certifi

from agent_read import SAMPLING, chat

THINK = {"qwen": {"enable_thinking": True}, "gemma": {"enable_thinking": True},
         "glimmer": {"reasoning_strength": "medium"}}  # each one's thinking on (Glimmer has no off)
from check_read import NAMES, Copy, picture

SCHEMA = {"type": "object", "properties": {"where": {"type": "string"}, "count": {"type": "integer"}},
          "required": ["where", "count"], "additionalProperties": False}
INTRO = ("One bar of the {name} part of an 18th-century manuscript string quartet (Boccherini, Op. 48 no. 4), its "
         "staff straightened; each line and space is named with its pitch in the left margin. ")
QUESTIONS = {
    "grace": ("How many grace notes are in this bar? A grace note is written smaller than the bar's other notes, "
              "with a thin stem, often slanted, and a small flag or a curl at the stem's end, just before a main "
              "note. Say where each one is (before which note, at what pitch), then give the count; 0 if none."),
    "chord": ("How many stems in this bar carry two or more note heads (a double stop or chord)? Count also two "
              "stems drawn on one head (a unison). Say where each one is (which note, which pitches), then give the "
              "count; 0 if none.")}


def counts(final: str) -> dict:
    return {"grace": len(re.findall(r"(^| )g[<A-G]", final or "")), "chord": len(re.findall(r"<", final or ""))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path, help="the edition copy (pictures are rendered in it)")
    ap.add_argument("edition", type=Path, help="the edition (read only): its run's final notes and D5's reading")
    ap.add_argument("--url", help="the vLLM server (not for a claude- model)")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high"], help="a claude- model's effort")
    ap.add_argument("--model", required=True)
    ap.add_argument("--negatives", type=int, default=40)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--thinking-budget", type=int, default=2048)
    ap.add_argument("--image-tokens", type=int, default=1120)
    ap.add_argument("--no-thinking", action="store_true", help="answer at once (Qwen thinks past any cap here)")
    a = ap.parse_args()
    state = json.loads(next((a.repo / "build/encode").glob("*/state.json")).read_text())
    copy = Copy(a.repo, state["quartet"], state["mvt"], state["run"], state["source"]["name"])
    copy.env["SS"] = "100"
    bars = json.loads((a.edition / "build/encode" / state["run"] / "d5/reading-vs-final.json").read_text())["against"]["bars"]
    bars = [b for b in bars if b.get("ours")]  # bars compared (not those with a clef change inside)
    hits = [b for b in bars if any(counts(b["ours"]).values())]
    rest = [b for b in bars if not any(counts(b["ours"]).values())]
    chosen = hits + random.Random(1).sample(rest, a.negatives)
    claude = a.model.startswith("claude-")
    if claude:  # the labeler's own Anthropic key and client, as bars.py
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        import anthropic
        import reader
        client = anthropic.Anthropic(api_key=reader.api_key(), max_retries=3, timeout=300.0)
    else:
        family = next(k for k in SAMPLING if k in a.model.lower())
        extra = {**SAMPLING[family], "chat_template_kwargs": {"enable_thinking": False} if a.no_thinking else THINK[family]}
        if family == "gemma":  # Gemma's thinking cap and picture budget; the others take neither
            extra.update({"thinking_token_budget": a.thinking_budget, "mm_processor_kwargs": {"max_soft_tokens": a.image_tokens}})
        key, ctx = os.environ["VLLM_API_KEY"], ssl.create_default_context(cafile=certifi.where())
    pics = {}
    for b in chosen:  # rendered one at a time: zoom.py writes one file name per bar
        out = copy.tool("scripts/zoom.py", copy.q, b["part"], copy.mvt, str(b["bar"]))
        path = a.repo / re.search(r"(build/\S+\.png)", out).group(1)
        pics[(b["part"], b["bar"])] = picture(path)
    log = a.repo / "build" / (f"see-{a.model.split('/')[-1].lower()}{'-' + a.effort if a.model.startswith('claude-') else ''}"
                              f"{'-nothink' if a.no_thinking else ''}.jsonl")

    def ask_claude(text: str, pic: dict) -> tuple[dict | None, str | None, dict]:
        media, data = re.match(r"data:(.*?);base64,(.*)", pic["image_url"]["url"]).groups()
        r = client.messages.create(
            model=a.model, max_tokens=16000, output_config={"effort": a.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [{"type": "text", "text": text},
                                                   {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}]}])
        out = next((x.text for x in r.content if x.type == "text"), "")
        try:
            return json.loads(out), None, r.usage.to_dict()
        except ValueError:
            return None, None, r.usage.to_dict()

    def one(job):
        b, q = job
        text = INTRO.format(name=NAMES[b["part"]]) + QUESTIONS[q]
        if "glimmer" in a.model.lower():  # it writes prose whatever the schema: ask for a last line to read
            text += " End with a last line: COUNT: <the number>."
        if claude:
            ans, thinking, usage = ask_claude(text, pics[(b["part"], b["bar"])])
            e = {"part": b["part"], "bar": b["bar"], "question": q, "true": counts(b["ours"])[q],
                 "d5": counts(b["read"])[q], "answer": ans, "thinking": thinking, "usage": usage}
            with log.open("a") as f:
                f.write(json.dumps(e) + "\n")
            return e
        body = {"model": a.model, "max_tokens": 12000, **extra, "seed": 1,
                "response_format": {"type": "json_schema", "json_schema": {"name": "count", "schema": SCHEMA, "strict": True}},
                "messages": [{"role": "user", "content": [{"type": "text", "text": text},
                                                          pics[(b["part"], b["bar"])]]}]}
        r = chat(a.url, key, body, ctx)
        m = r["choices"][0]["message"]
        content = m.get("content") or ""
        found = re.search(r"\{.*\}", content, re.S)  # the JSON, if wrapped in a code fence or words
        try:
            ans = json.loads(found.group(0)) if found else None
        except ValueError:
            ans = None
        last = re.findall(r"COUNT:\s*\**\s*(\d+)", content)
        if ans is None and last:  # a model that ignores the schema (Glimmer): its last line
            ans = {"where": content[-500:], "count": int(last[-1])}
        e = {"part": b["part"], "bar": b["bar"], "question": q, "true": counts(b["ours"])[q],
             "d5": counts(b["read"])[q], "answer": ans, "content": content, "finish": r["choices"][0]["finish_reason"],
             "thinking": m.get("reasoning_content")}
        with log.open("a") as f:
            f.write(json.dumps(e) + "\n")
        return e

    with ThreadPoolExecutor(a.workers) as pool:
        got = list(pool.map(one, [(b, q) for b in chosen for q in QUESTIONS]))
    for q in QUESTIONS:
        es = [e for e in got if e["question"] == q and e["answer"]]
        pos = [e for e in es if e["true"] > 0]
        neg = [e for e in es if e["true"] == 0]
        missed = [e for e in pos if e["d5"] < e["true"]]
        said = lambda e: e["answer"]["count"] > 0
        print(f"{q}: there and seen {sum(map(said, pos))}/{len(pos)} (exact count {sum(e['answer']['count'] == e['true'] for e in pos)}); "
              f"of those D5 missed, seen {sum(map(said, missed))}/{len(missed)}; "
              f"not there but said {sum(map(said, neg))}/{len(neg)}")
    if claude:
        u = [e["usage"] for e in got]
        cost = sum(x["input_tokens"] for x in u) * reader.PRICE["input"] / 1e6 + sum(x["output_tokens"] for x in u) * reader.PRICE["output"] / 1e6
        print(f"tokens in {sum(x['input_tokens'] for x in u)}, out {sum(x['output_tokens'] for x in u)}: ${cost:.2f}")


if __name__ == "__main__":
    main()
