# /// script
# requires-python = ">=3.11"
# dependencies = ["certifi", "pillow"]
# ///
"""The edition's /encode reader, with an open model in Opus's place: the same
instructions, the same tools, the same bars, so the two readings can be
compared bar for bar against the person's final notes.

    VLLM_API_KEY=<key> uv run experiments/llm/agent_read.py <edition-copy> --part vn1 --chunk 1 \\
        --url https://<app>.modal.run/v1 --model Qwen/Qwen3.6-27B-FP8

<edition-copy> is a clone of the edition at the commit the run's readers
started from, its run folder holding only the files written before reading
began, its note files seeded (encode.py seed). Never the edition itself:
the model writes the note file and the run's records.

The prompt is the one .claude/workflows/encode.js gives a reader (its setup,
phase file and assignment, from the run's plan-read.json), after the
encoder agent's instructions (.claude/agents/encoder.md). The tools are
that agent's: a shell, reading a file or a picture, writing a file. Pictures
are shrunk as Claude Code shrinks them for Opus (at most 2000 px a side and
about 1.15 million pixels). The model thinks before each turn.

Run this inside Claude Code's sandbox: every command the model runs is then
held to it. Python's own TLS (certifi) is used because the sandbox blocks
the macOS certificate service. Each turn is logged to
<edition-copy>/build/<model>/<part>-<chunk>.jsonl.

--thinking-budget caps each reply's thinking (vLLM ends the thinking there);
--image-tokens sets Gemma 4's picture budget (its default, 280 tokens, would
shrink a zoom below what Opus is shown).
"""

import argparse
import base64
import io
import json
import os
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi
from PIL import Image

MAX_SIDE, MAX_PIXELS = 2000, 1_150_000  # what Opus is shown (encode-status.md, "the two display limits")
OUTPUT_LIMIT = 30_000  # characters of a command's output returned, as Claude Code's shell does
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
# Each model card's sampling for thinking; at most 32,768 tokens a reply
SAMPLING = {"qwen": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0},
            "gemma": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
            "glimmer": {"temperature": 1.0, "top_p": 0.95, "top_k": 64}}
THINK = {"qwen": {"enable_thinking": True}, "gemma": {"enable_thinking": True},
         "glimmer": {"reasoning_strength": "high"}}  # Glimmer's card: high for agentic tasks
NUDGE = ("Your thinking reached the 32,768-token limit three times without acting. Act now on what you have "
         "seen: write the bars you have read with bars.py set and record them, then go on bar by bar.")

TOOLS = [
    {"type": "function", "function": {
        "name": "bash", "description": "Run a shell command (bash) in the repository root. The working directory "
        "and environment are reset between commands. Returns stdout and stderr, cut to 30,000 characters.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "The command to run"},
            "timeout": {"type": "integer", "description": "Seconds before the command is stopped (default 300)"}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read", "description": "Read a file, by path relative to the repository root or absolute. A text "
        "file comes back with line numbers (up to 2000 lines from offset); a picture (.png, .jpg) is shown to you.",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
            "required": ["file_path"]}}},
    {"type": "function", "function": {
        "name": "write", "description": "Write a file (overwriting it), by path relative to the repository root "
        "or absolute.", "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}}},
]


def prompts(repo: Path, part: str, chunk: int) -> tuple[str, str]:
    """The encoder agent's instructions, and the reader's task as encode.js writes it."""
    system = re.sub(r"\A---.*?---\s*", "", (repo / ".claude/agents/encoder.md").read_text(), flags=re.S)
    plan = json.loads(next((repo / "build/encode").glob("*/plan-read.json")).read_text())
    job = next(j for j in plan["jobs"] if j["part"] == part)
    mine = job["chunks"]
    i = chunk - 1
    bars, last = mine[i], i == len(mine) - 1
    setup = (f'Run: {plan["run"]} (folder {plan["run_dir"]}). Quartet {plan["quartet"]}, movement {plan["mvt"]}, '
             f'source "{plan["source"]}".\nBefore anything else run, in your shell:  export ENCODE_RUN={plan["run"]}  '
             f'and  export OP48_SOURCE="{plan["source"]}"\nRead docs/encode/common.md, then the phase file named '
             f'below, then do the assignment. Return only the JSON summary the phase file asks for.')
    assignment = {"part": job["part"], "file": job["file"], "bars": bars, "record": job["record"],
                  "chunk": f"{i + 1} of {len(mine)}", "form": job["form"], "conventions": plan["conventions"]}
    task = f"{setup}\nPhase file: docs/encode/reader.md\nAssignment: {json.dumps(assignment, separators=(',', ':'))}\n"
    if i > 0 or job.get("after") is not None:
        prev = mine[i - 1][-1] if i > 0 else job["after"]
        task += (f"Bars before {bars[0]} were read by an earlier agent and are in the file; start from them (bars.py "
                 f"show) and do not change them except for an octave mark they leave wrong. First check that the "
                 f"earlier agent's chunk is complete: no %% SEED line in it, and a record for its last bar ({prev}); "
                 f"read any bar it left before your own.\n")
    task += f"Before you return, confirm with bars.py show that none of your bars ({bars[0]}-{bars[-1]}) is still a %% SEED line.\n"
    task += (f"You read the last chunk: run uv run --offline scripts/encode.py check {plan['run']} read and read any bar "
             f"of {job['part']} it lists as having no record; fix the records it names for {job['part']}; then finish "
             f'with the reread of the first eight bars of the part (a second record each, "pass": 2), and the bar '
             f"count check." if last else "Do not reread the first eight bars; the last chunk's agent does.")
    return system, task


class Tools:
    def __init__(self, repo: Path):
        self.repo = repo
        self.allowed = [repo.resolve(), Path(os.environ.get("TMPDIR", "/tmp")).resolve()]

    def path(self, p: str) -> Path:
        q = (self.repo / p).resolve() if not p.startswith("/") else Path(p).resolve()
        if not any(q == a or a in q.parents for a in self.allowed):
            raise PermissionError(f"{p} is outside the repository and $TMPDIR")
        return q

    def bash(self, command: str, timeout: int = 300) -> tuple[str, list]:
        try:
            r = subprocess.run(["bash", "-c", command], cwd=self.repo, capture_output=True, text=True,
                               timeout=min(int(timeout or 300), 600))
            out = (r.stdout + r.stderr)
            out = (out[:OUTPUT_LIMIT] + f"\n... ({len(out) - OUTPUT_LIMIT} characters cut)") if len(out) > OUTPUT_LIMIT else out
            return (out or "(no output)") + ("" if r.returncode == 0 else f"\n[exit code {r.returncode}]"), []
        except subprocess.TimeoutExpired:
            return f"[stopped after {timeout} s]", []

    def read(self, file_path: str, offset: int = 1, limit: int = 2000) -> tuple[str, list]:
        p = self.path(file_path)
        if not p.exists():
            return f"File does not exist: {file_path}", []
        if p.suffix.lower() in IMAGES:
            im = Image.open(p).convert("RGB")
            f = min(1.0, MAX_SIDE / max(im.size), (MAX_PIXELS / (im.width * im.height)) ** 0.5)
            if f < 1:
                im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return f"[picture {file_path}, shown at {im.width}x{im.height}]", [base64.b64encode(buf.getvalue()).decode()]
        lines = p.read_text(errors="replace").split("\n")
        start = max(1, int(offset or 1))
        chosen = lines[start - 1: start - 1 + int(limit or 2000)]
        return "\n".join(f"{n:6}\t{l}" for n, l in enumerate(chosen, start)) or "(empty file)", []

    def write(self, file_path: str, content: str) -> tuple[str, list]:
        p = self.path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {file_path} ({len(content)} characters)", []

    def call(self, name: str, args: dict) -> tuple[str, list]:
        try:
            return getattr(self, name)(**args) if name in ("bash", "read", "write") else (f"No tool {name}", [])
        except Exception as e:  # the model sees the error and goes on, as with Claude Code
            return f"Error: {type(e).__name__}: {e}", []


def read_stream(r) -> dict:
    """A streamed reply put back together as one non-streamed reply. Streamed, because Modal
    cuts off a web request with no answer after 150 s and a thinking turn can take longer."""
    content, thinking, calls, finish, usage = [], [], {}, None, None
    for raw in r:
        line = raw.decode().strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        chunk = json.loads(line[5:])
        usage = chunk.get("usage") or usage
        for ch in chunk.get("choices", []):
            d = ch.get("delta", {})
            content.append(d.get("content") or "")
            thinking.append(d.get("reasoning_content") or d.get("reasoning") or "")
            for tc in d.get("tool_calls") or []:
                c = calls.setdefault(tc["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                c["id"] = tc.get("id") or c["id"]
                fn = tc.get("function") or {}
                c["function"]["name"] += fn.get("name") or ""
                c["function"]["arguments"] += fn.get("arguments") or ""
            finish = ch.get("finish_reason") or finish
    message = {"content": "".join(content), "reasoning_content": "".join(thinking),
               "tool_calls": [calls[k] for k in sorted(calls)]}
    return {"choices": [{"message": message, "finish_reason": finish}],
            "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0}}


def chat(url: str, key: str, body: dict, ctx) -> dict:
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(url + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=600) as r:
                return read_stream(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:2000]
            if e.code < 500 or attempt == 3:
                raise SystemExit(f"agent_read: the server refused the request ({e.code}): {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == 3:
                raise SystemExit(f"agent_read: no answer from the server: {e}")
        time.sleep(10 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path, help="the edition copy (never the edition itself)")
    ap.add_argument("--part", required=True)
    ap.add_argument("--chunk", type=int, default=1, help="the reader's chunk of the part, from 1 (plan-read.json)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-turns", type=int, default=400)
    ap.add_argument("--context", type=int, default=131072, help="the server's context length")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--thinking-budget", type=int, help="the most thinking tokens a reply")
    ap.add_argument("--image-tokens", type=int, help="Gemma 4's picture budget (70-1120)")
    ap.add_argument("--reasoning-strength", choices=["low", "medium", "high", "xhigh"],
                    help="Muse Glimmer's own control of its thinking (its thinking budget doesn't take)")
    a = ap.parse_args()
    family = next(k for k in SAMPLING if k in a.model.lower())
    extra = {**SAMPLING[family], "chat_template_kwargs": THINK[family]}
    if a.reasoning_strength:
        extra["chat_template_kwargs"] = {"reasoning_strength": a.reasoning_strength}
    if a.thinking_budget:
        extra["thinking_token_budget"] = a.thinking_budget
    if a.image_tokens:
        extra["mm_processor_kwargs"] = {"max_soft_tokens": a.image_tokens}
    repo = a.repo.resolve()
    if Path.home() / "Dropbox" in repo.parents:
        raise SystemExit("agent_read: give it a copy of the edition, not the edition")
    key = os.environ["VLLM_API_KEY"]
    ctx = ssl.create_default_context(cafile=certifi.where())
    system, task = prompts(repo, a.part, a.chunk)
    tools = Tools(repo)
    log = repo / "build" / a.model.split("/")[-1].lower() / f"{a.part}-{a.chunk}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    with log.open("a") as f:
        f.write(json.dumps({"start": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": a.model, "seed": a.seed,
                            "settings": extra,
                            "system": system, "task": task}) + "\n")
    t0, prompt_tokens, output_tokens, final, nudges = time.time(), 0, 0, None, 0
    for turn in range(1, a.max_turns + 1):
        t = time.time()
        for attempt in range(3):  # a reply cut off before it acts is asked again, with another seed
            r = chat(a.url, key, {"model": a.model, "messages": messages, "tools": TOOLS, "tool_choice": "auto",
                                  "max_tokens": 32768, **extra, "seed": a.seed * 100_000 + turn * 10 + attempt},
                     ctx)
            m, u = r["choices"][0]["message"], r["usage"]
            prompt_tokens += u["prompt_tokens"]
            output_tokens += u["completion_tokens"]
            calls = m.get("tool_calls") or []
            cut = r["choices"][0]["finish_reason"] == "length" and not calls
            if not cut:
                break
            with log.open("a") as f:
                f.write(json.dumps({"turn": turn, "cut_off": attempt + 1, "output_tokens": u["completion_tokens"],
                                    "thinking": m.get("reasoning_content")}) + "\n")
        if cut:  # three times cut off: say so, as the one help Opus never needed
            nudges += 1
            messages.append({"role": "user", "content": NUDGE})
            print(f"turn {turn}: cut off three times; nudged", flush=True)
            continue
        messages.append({"role": "assistant", "content": m.get("content") or "",
                         **({"tool_calls": calls} if calls else {})})
        entry = {"turn": turn, "seconds": round(time.time() - t, 1), "prompt_tokens": u["prompt_tokens"],
                 "output_tokens": u["completion_tokens"], "finish": r["choices"][0]["finish_reason"],
                 "thinking": m.get("reasoning_content") or m.get("reasoning"), "content": m.get("content"),
                 "calls": []}
        pictures = []
        for c in calls:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except ValueError:
                args = None
            out, images = tools.call(c["function"]["name"], args) if isinstance(args, dict) else \
                ("Error: the arguments were not valid JSON", [])
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
            pictures += images
            entry["calls"].append({"name": c["function"]["name"], "args": args, "output": out[:4000],
                                   "pictures": len(images)})
        if pictures:  # a picture can't ride in a tool result here; it follows as the user's message
            messages.append({"role": "user", "content": [{"type": "text", "text": "The pictures you read, in order:"}] +
                             [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{p}"}} for p in pictures]})
        with log.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"turn {turn}: {entry['seconds']} s, context {u['prompt_tokens']}, "
              + (", ".join(f"{c['name']} {json.dumps(c['args'])[:90]}" for c in entry["calls"]) or "answer"), flush=True)
        if not calls:
            final = m.get("content")
            break
        if u["prompt_tokens"] + u["completion_tokens"] > a.context - 34000:  # room for one more reply
            final = f"stopped: the context is nearly full ({u['prompt_tokens']} tokens)"
            break
    else:
        final = f"stopped: {a.max_turns} turns"
    summary = {"part": a.part, "chunk": a.chunk, "turns": turn, "minutes": round((time.time() - t0) / 60, 1),
               "prompt_tokens": prompt_tokens, "output_tokens": output_tokens, "nudges": nudges, "final": final}
    with log.open("a") as f:
        f.write(json.dumps({"summary": summary}) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
