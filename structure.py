"""A movement's Structure.ily block from a source's reviewed labels.

The labeler offers it once a movement is complete in all of a source's
parts (labels.bars_export's `complete`) and Structure.ily has no real
block for it yet (missing, or still the template's `s2*1`). It never
overwrites a written block: a source that differs from one is a
difference between sources, for the editor.

From the labels: each part's bars (counts, pickups), repeat signs, the
key and time written at the movement's start and where they change
(staff starts and signature marks), and tempo marks. The parts must
agree. What the page doesn't show is asked: each key's mode (major or
minor; its signature is the same) and an upbeat's length. The block is
read back with labels.parse_structure and must give the labels' bars,
repeats, key and time before it can be written.
"""

import re
from datetime import date
from fractions import Fraction

import labels

PARTS = ["vn1", "vn2", "va", "vc"]
TONIC = {
    "major": {0: "c", 1: "g", 2: "d", 3: "a", 4: "e", 5: "b", 6: "fis", 7: "cis",
              -1: "f", -2: "bes", -3: "es", -4: "as", -5: "des", -6: "ges", -7: "ces"},
    "minor": {0: "a", 1: "e", 2: "b", 3: "fis", 4: "cis", 5: "gis", 6: "dis", 7: "ais",
              -1: "d", -2: "g", -3: "c", -4: "f", -5: "bes", -6: "es", -7: "as"},
}
REPEAT_END = ("repeat_end", "repeat_both")
REPEAT_START = ("repeat_start", "repeat_both")


def meter(time: str) -> tuple[int, int]:
    return {"C": (4, 4), "C/": (2, 2)}.get(time) or tuple(int(x) for x in time.split("/"))


def duration(length: Fraction) -> str:
    """A length in whole notes as a LilyPond duration: 2, 2., 1, 8*3 ..."""
    for den in (1, 2, 4, 8, 16, 32):
        if length == Fraction(1, den):
            return str(den)
        if length == Fraction(3, 2 * den):
            return f"{den}."
    return f"{length.denominator}*{length.numerator}"


def spacer(length: Fraction, n: int = 1) -> str:
    d = duration(length)
    if n == 1:
        return f"s{d}"
    return f"s{d}*{n}" if "*" not in d else f"s{d.split('*')[0]}*{int(d.split('*')[1]) * n}"


def _mid(b: dict) -> float:
    return (b["x0"] + b["x1"]) / 2


def part_bars(doc: dict, movement: str) -> dict[str, list[dict]]:
    """{part: its bars of the movement, in order}, parts only (no score)."""
    out: dict[str, list] = {}
    for nb in labels.number_bars(doc):
        if nb["movement"] == movement and nb["part"] in PARTS:
            out.setdefault(nb["part"], []).append(nb)
    return out


def bar_changes(doc: dict, nb: dict) -> dict:
    """The key and time written in this bar (on its line's start, for a
    line's first bar; or a signature mark inside it, or at its first bar
    line): {"key": 2, "time": "3/4"}, each only if written there."""
    page = doc["pages"][str(nb["page"])]
    s = nb["system"]
    x1 = _mid(nb["right"])
    out = {}
    for field in ("key", "time"):
        for t, x, v in labels.sig_changes(page, field):
            if t is not s:
                continue
            if (nb["left"] is None and x <= s.get("start", s["left"])) or \
                    (nb["left"] is not None and _mid(nb["left"]) - 1e-9 <= x < x1) or \
                    (nb["left"] is None and s.get("start", s["left"]) < x < x1):
                out[field] = v
    return out


def where(b: dict) -> tuple[int, bool]:
    """A bar's place in the movement, the same in every part: its number,
    and whether it's an upbeat (count 0, sharing the number before it)."""
    return (b["bar"], b["count"] == 0)


def tempos(doc: dict, movement: str) -> dict[tuple, list[str]]:
    """Tempo marks by the bar they belong to (where), across the parts."""
    out: dict[tuple, list[str]] = {}
    exp = labels.bars_export(doc)["bars"]
    texts = {m["id"]: m.get("text", "") for p in doc["pages"].values() for m in p.get("marks", [])
             if m.get("kind") == "tempo" and m.get("text")}
    for b in exp:
        if b["part"] in PARTS and b["movement"] == movement:
            for mid in b["marks"]:
                if mid in texts and texts[mid] not in out.setdefault(where(b), []):
                    out[where(b)].append(texts[mid])
    return {k: v for k, v in out.items() if v}


def shape(bars: list[dict]) -> list[tuple]:
    """What the parts must agree on exactly, bar number by bar number (a
    multi-bar rest standing for each of its bars): upbeats and repeats."""
    out = []
    for b in bars:
        n = max(b["count"], 1)
        for k in range(n):
            last = k == n - 1
            out.append((b["bar"] + k, b["count"] == 0, last and b["right"]["kind"] in REPEAT_END,
                        last and b["right"]["kind"] in REPEAT_START))
    return out


def merged_changes(doc: dict, parts: dict[str, list[dict]]) -> tuple[dict, list[str]]:
    """Key and time written at each bar (where), from any part (a part that
    leaves one unwritten agrees); and where two parts write different ones."""
    out: dict[tuple, dict] = {}
    problems = []
    for p, bars in parts.items():
        for b in bars:
            for f, v in bar_changes(doc, b).items():
                have = out.setdefault(where(b), {})
                if f in have and have[f][0] != v:
                    problems.append(f"bar {b['bar']}: {have[f][1]} writes {f} {have[f][0]}, {p} {v}")
                have.setdefault(f, (v, p))
    return {k: {f: v for f, (v, _) in c.items()} for k, c in out.items()}, problems


def lily_string(t: str) -> str:
    return '"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'


def slots(parts: dict[str, list[dict]], changes: dict, tempo: dict) -> list[dict]:
    """The movement bar by bar, the same in every part (they agree on
    shape): {"where", "upbeat", "end", "start", "changes", "tempo"} per bar,
    a multi-bar rest standing for each of its bars, so no one part's
    writing of them decides the block."""
    ref = next(iter(parts.values()))
    out = []
    for number, upbeat, end, start in shape(ref):
        w = (number, upbeat)
        out.append({"where": w, "upbeat": upbeat, "end": end, "start": start,
                    "changes": changes.get(w, {}), "tempo": (tempo.get(w) or [None])[0]})
    return out


def key_events(sl: list[dict]) -> list[tuple[int, int]]:
    """(slot index, sharps or flats) where the key changes (a restated key isn't a change)."""
    out, now = [], None
    for i, s in enumerate(sl):
        k = s["changes"].get("key")
        if k is not None and k != now:
            out.append((i, k))
            now = k
    return out


def render(sl: list[dict], movement: str, modes: list[str], upbeat: Fraction | None, source: str) -> str:
    """The \\tag block from the slots; `modes`: one per key event."""
    events = dict(zip((i for i, _ in key_events(sl)), modes))
    pickup_start = sl[0]["upbeat"]
    out = [f"% From the reviewed labels of {source}, all parts agreeing; written by the labeler, "
           f"{date.today().isoformat()}.", f"\\tag #'mvt{movement} {{"]
    st = {"time": None, "bar": None, "numeric": False}

    def header(i):
        """\\time, \\key and \\tempo at slot i (a restated time or key changes nothing)."""
        items = []
        c = sl[i]["changes"]
        if "time" in c and c["time"] != st["time"]:
            st["time"] = c["time"]
            n, d = meter(c["time"])
            st["bar"] = Fraction(n, d)
            numeric = c["time"] in ("4/4", "2/2")  # written as numbers, not as C or ¢
            if numeric != st["numeric"]:
                items.append("\\numericTimeSignature" if numeric else "\\defaultTimeSignature")
                st["numeric"] = numeric
            items.append(f"\\time {n}/{d}")
        if i in events:
            mode = events[i]
            items.append(f"\\key {TONIC[mode][c['key']]} \\{mode}")
        lines = [" ".join(items)] if items else []
        if sl[i]["tempo"]:
            lines.append(f"\\tempo {lily_string(sl[i]['tempo'])}")
        return lines

    # sections: closed by a repeat sign (repeated) or opened by a start-repeat
    sections, cur = [], []
    for i, s in enumerate(sl):
        cur.append(i)
        if s["end"]:
            sections.append((True, cur))
            cur = []
        elif s["start"]:
            sections.append((False, cur))
            cur = []
    if cur:
        sections.append((False, cur))
    for repeated, idx in sections:
        tokens, run = [], 0

        def flush():
            nonlocal run
            if run:
                tokens.append(spacer(st["bar"], run))
                run = 0
        for k, i in enumerate(idx):
            h = header(i)
            if k == 0:
                out += ["  " + line for line in h]
            elif h:
                flush()
                tokens += h
            nxt = sl[i + 1] if i + 1 < len(sl) else None
            if sl[i]["upbeat"]:  # the pickup, or the rest of a bar a repeat split
                flush()
                tokens.append((f"\\partial {duration(upbeat)} " if i == 0 else "") + spacer(upbeat))
            elif upbeat and ((nxt and nxt["upbeat"]) or (nxt is None and pickup_start)):
                flush()  # a short bar: the upbeat after it completes it (or the last, matching the pickup)
                tokens.append(spacer(st["bar"] - upbeat))
            else:
                run += 1
        flush()
        body = " ".join(tokens)
        out.append(f"  \\repeat volta 2 {{ {body} }}" if repeated else f"  {body}")
    out.append("}")
    return "\n".join(out)


def expected_from_labels(sl: list[dict]) -> dict:
    """What the block must read back as: total, pickup, repeat ends, the
    opening key and time and each change (bar, field, value)."""
    total = sum(1 for s in sl if not s["upbeat"])
    n, ends = 0, []
    for s in sl:
        n += 0 if s["upbeat"] else 1
        if s["end"]:
            ends.append(n)
    changes, now = [], {}
    for i, s in enumerate(sl):
        for f in ("key", "time"):
            v = s["changes"].get(f)
            if v is not None and v != now.get(f):
                if i:
                    changes.append((s["where"][0], f, v))
                now[f] = v
    return {"total": total, "pickup": sl[0]["upbeat"], "repeat_ends": ends,
            "key": sl[0]["changes"].get("key"), "time": sl[0]["changes"].get("time"), "changes": changes}


def check(text: str, movement: str, want: dict) -> list[str]:
    """Problems reading the block back (empty: it says what the labels say)."""
    got = labels.parse_structure(text).get(movement)
    if not got:
        return ["the block doesn't parse"]
    cum, ends = 0, []
    for s in got["segments"]:
        cum += s["bars"]
        if s["repeat"]:
            ends.append(cum)
    have = {"total": got["total"], "pickup": got["pickup"], "repeat_ends": ends, "key": got.get("key"),
            "time": got.get("time"),
            "changes": [(c["bar"], f, c[f]) for c in got.get("changes", []) for f in ("key", "time") if f in c]}
    return [f"{k}: the block gives {have[k]}, the labels {want[k]}" for k in want if have[k] != want[k]]


ALLOWED = re.compile(r"""\\time\s+\d+\s*/\s*\d+|\\key\s+[a-z]+\s*\\(?:major|minor)|\\tempo\s+"[^"]*"|\\repeat\s+volta\s+\d+"""
                     r"""|\\bar\s+"[^"]*"|\\(?:numeric|default)TimeSignature|s\d+\.*\s*\*\s*1(?![\d/])|[{}\s]""")


def block_text(text: str, movement: str) -> str | None:
    """The movement's \\tag block in Structure.ily, or None."""
    music = labels._blank(text)
    m = re.search(r"\\tag\s+#'mvt" + re.escape(movement) + r"\s*\{", music)
    if not m:
        return None
    depth, j = 0, m.end() - 1
    while j < len(music):
        depth += {"{": 1, "}": -1}.get(music[j], 0)
        j += 1
        if depth == 0:
            break
    return music[m.end():j - 1]


def is_template(text: str, movement: str) -> bool:
    """No real block for the movement yet: none, or only the template's own
    one-bar spacers among \\time, \\key, \\tempo, repeats and bar lines.
    Anything else (counted spacers, rests, music, variables) is real."""
    body = block_text(text, movement)
    if body is None:
        return True
    rest = ALLOWED.sub("", body)
    return not rest.strip() and bool(re.search(r"s\d+\.*\s*\*\s*1(?![\d/])", body))


def offers(doc: dict, text: str | None) -> list[str]:
    """Movements this source could write: complete in every part, and
    still the template (or missing) in Structure.ily."""
    if text is None:
        return []
    complete = labels.bars_export(doc)["complete"]
    mvts = set.intersection(*(set(complete.get(p, [])) for p in PARTS)) if all(p in complete for p in PARTS) else set()
    return sorted((m for m in mvts if is_template(text, m)), key=lambda m: labels.ROMAN.index(m) if m in labels.ROMAN else 99)


UPBEATS = ["2", "4", "4.", "8", "8.", "16"]


def propose(doc: dict, movement: str, existing: dict | None, answers: dict | None = None) -> dict:
    """{"ok", "problems", "questions", "text", "want"} for one movement of one source."""
    answers = answers or {}
    parts = part_bars(doc, movement)
    complete = labels.bars_export(doc)["complete"]
    problems = []
    missing = [p for p in PARTS if movement not in complete.get(p, [])]
    if missing:
        problems.append("not complete (every page reviewed, the movement's end marked) in: " + ", ".join(missing))
    if not parts:
        return {"ok": False, "problems": problems or ["no bars"], "questions": [], "text": ""}
    ref_part = next(p for p in PARTS if p in parts)
    ref_shape = shape(parts[ref_part])
    for p, bars in parts.items():
        sh = shape(bars)
        if sh != ref_shape:
            k = next((i for i, (a, b) in enumerate(zip(sh, ref_shape)) if a != b), min(len(sh), len(ref_shape)))
            at = f"bar {sh[k][0]}" if k < len(sh) else "its end"
            problems.append(f"{p} differs from {ref_part} at {at} (its bars, upbeats or repeats)")
    changes, conflicts = merged_changes(doc, parts)
    problems += conflicts
    tempo = tempos(doc, movement)
    sl = slots(parts, changes, tempo)
    for f in ("key", "time"):
        if f not in sl[0]["changes"]:
            problems.append(f"no part has its {f} set at the movement's start")
    # what the page doesn't show: each key's mode (default: what Structure.ily
    # says, else the mode before), an upbeat's length
    old = ([existing.get("mode")] + [c.get("mode") for c in existing.get("changes", []) if "key" in c]) if existing else []
    modes, questions, prev = [], [], "major"
    for n, (i, k) in enumerate(key_events(sl)):
        dflt = answers.get(f"mode{n}") or (old[n] if n < len(old) and old[n] else prev)
        if dflt not in TONIC:
            problems.append(f"mode{n}: major or minor")
            dflt = prev
        modes.append(dflt)
        prev = dflt
        questions.append({"id": f"mode{n}", "ask": f"Key of {labels_key(k)}: major or minor?",
                          "choices": ["major", "minor"], "value": dflt})
    upbeat = None
    if any(s["upbeat"] for s in sl):
        u = answers.get("upbeat") or "4"
        questions.append({"id": "upbeat", "ask": "Length of its upbeats (4 = a quarter, 8 = an eighth, 4. = a dotted quarter)",
                          "choices": UPBEATS, "value": u})
        bar = Fraction(*meter(sl[0]["changes"]["time"])) if "time" in sl[0]["changes"] else None
        upbeat = _dotted(u) if u in UPBEATS else None
        if upbeat is None or (bar is not None and not 0 < upbeat < bar):
            problems.append("an upbeat must be shorter than a bar")
    if problems:
        return {"ok": False, "problems": problems, "questions": questions, "text": ""}
    texts = {w: v for w, v in tempo.items() if len(v) > 1}
    notes = [f"bar {w[0]}: the parts' tempo marks differ ({' / '.join(v)}); the first is used" for w, v in texts.items()]
    source = (doc["source"].get("siglum", "") + " " + doc["source"].get("shelfmark", "")).strip()
    text = render(sl, movement, modes, upbeat, source)
    want = expected_from_labels(sl)
    probs = check(text, movement, want)
    return {"ok": not probs, "problems": probs, "notes": notes, "questions": questions, "text": text, "want": want}


def _dotted(u: str) -> Fraction:
    base = Fraction(1, int(u.rstrip(".")))
    return base * (2 - Fraction(1, 2 ** u.count(".")))


def labels_key(k: int) -> str:
    return "no sharps or flats" if k == 0 else f"{k} sharp{'s' * (k > 1)}" if k > 0 else f"{-k} flat{'s' * (k < -1)}"


def write_block(text: str, movement: str, block: str) -> str:
    """Structure.ily's text with movement's \\tag block replaced by `block`
    (its comment lines just above, if the labeler wrote them, too), or
    added after the last movement's block."""
    music = labels._blank(text)
    m = re.search(r"\\tag\s+#'mvt" + re.escape(movement) + r"\s*\{", music)
    if m:
        depth, j = 0, m.end() - 1
        while j < len(music):
            depth += {"{": 1, "}": -1}.get(music[j], 0)
            j += 1
            if depth == 0:
                break
        start = m.start()
        before = text[:start]
        prev = before.rstrip("\n").rsplit("\n", 1)
        if len(prev) == 2 and prev[1].startswith("% From the reviewed labels of"):
            start = len(prev[0]) + 1
        return text[:start] + block + text[j:]
    ends = [mm.start() for mm in re.finditer(r"\\tag\s+#'mvt", music)]
    if not ends:
        return text.rstrip("\n") + "\n\n" + block + "\n"
    last = ends[-1]
    depth, j = 0, music.index("{", last)
    while j < len(music):
        depth += {"{": 1, "}": -1}.get(music[j], 0)
        j += 1
        if depth == 0:
            break
    return text[:j] + "\n\n" + block + text[j:]
