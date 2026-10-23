"""zeus-score: how likely an OMR model finds a reading of a manuscript's
staves, token by token, with a named, versioned, checked model: Zeus, or a
MuSViT reader (a registry entry's `engine`).

    zeus-score --pdf M.pdf --structure S.json --events DIR --out scores.json \\
        [--bars M.bars.json] [--parts ...] [--movements ...] [--shifts 0 -1 1] \\
        [--model NAME[@VERSION] | --model PATH] [--renders DIR] [--cache DIR]
    zeus-score --edition DIR --source SRC ...   the Op. 48 edition's layout
    zeus-score read --edition DIR --source SRC --out reading.json \\
        [--movements ...] [--parts ...] [--against DIR] [--model NAME[@VERSION]]
                                          a MuSViT reader's own reading of each staff,
                                          with each token's probability; with
                                          --against (our notes), each bar counted
                                          as the model card counts it
    zeus-score compare --edition DIR --source SRC --events A --against B --out FILE
                                          two sets of our notes counted the same way
    zeus-score fetch [NAME[@VERSION]]     download a model (the default if none
                                          is named) and build the environment:
                                          the one step that needs the network
    zeus-score models                     the registry
    zeus-score --version

The inputs, options and output are those of the labeler's
tools/zeus_score.py, which this runs in an environment of its own (Python
3.10, Zeus, tensorflow), started with uv, offline; for a MuSViT reader,
tools/musvit_score.py (PyTorch) in one of its own. The package's README.md
describes them all. Models come from the registry
(models.json): fetched once into --cache, checked against their sha256 when
fetched and every time they are used. A path to a model folder still works,
for experiments; its scores then don't say what it was trained on.

The models' weights derive from OmniOMR's Zeus weights or from MuSViT
(PRAIG), and are licensed CC BY-NC-SA 4.0: non-commercial use only. This
code is MIT.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Each engine: its scoring script, the file its registry sha256 is of, the
# files its archive holds, and what its environment is.
ENGINES = {
    "zeus": {"script": HERE / "engine" / "score.py", "weights": "weights.h5",
             "files": {"weights.h5", "architecture_options.yaml", "model_options.yaml", "token_map.txt", "LICENSE",
                       "NOTICE.md"},
             "env": "Python 3.10, Zeus, tensorflow"},
    "musvit": {"script": HERE / "engine" / "musvit_score.py", "weights": "reader.safetensors",
               "files": {"reader.safetensors", "reader.json", "vocab.json", "LICENSE", "NOTICE.md"},
               "env": "PyTorch, transformers"},
}
REGISTRY = HERE / "models.json"
CACHE = Path.home() / ".cache" / "manuscript-labeler" / "models"
# uv's managed Python 3.10 for Zeus, kept apart from the user's own.
PYTHON = Path.home() / ".cache" / "manuscript-labeler" / "zeus" / "py"
# Written by fetch once an engine's environment is built: a failed score run
# before then is most likely the environment missing.
ENV_BUILT = PYTHON.parent / "zeus-score-env-built"


def env_built(engine: str) -> Path:
    return ENV_BUILT if engine == "zeus" else ENV_BUILT.with_name(f"zeus-score-{engine}-env-built")


def engine_of(m: dict) -> str:
    return m.get("engine", "zeus")


def engine_at(path: Path) -> str:
    """A model folder given by path: a MuSViT reader has reader.json."""
    return "musvit" if (path / "reader.json").exists() else "zeus"


def registry() -> list[dict]:
    return json.loads(REGISTRY.read_text())["models"]


def find(spec: str | None, models: list[dict] | None = None) -> dict:
    """The registry entry NAME[@VERSION] names (its latest version if none
    is given), or the default one."""
    models = registry() if models is None else models
    if not spec:
        return next(m for m in models if m.get("default"))
    name, _, version = spec.partition("@")
    found = [m for m in models if m["name"] == name and (not version or m["version"] == version)]
    if not found:
        known = ", ".join(f"{m['name']}@{m['version']}" for m in models)
        sys.exit(f"zeus-score: no model {spec} in the registry ({known})")
    return max(found, key=lambda m: m["version"])


def is_path(spec: str) -> bool:
    return "/" in spec or spec.endswith(".model") or Path(spec).is_dir()


def folder(cache: Path, m: dict) -> Path:
    return cache / engine_of(m) / f"{m['name']}@{m['version']}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(d: Path, m: dict) -> None:
    """The model's weights are the registry's, or exit."""
    w = d / ENGINES[engine_of(m)]["weights"]
    if not w.exists():
        sys.exit(f"zeus-score: {m['name']}@{m['version']} isn't in {d.parent}; "
                 f"run `zeus-score fetch {m['name']}@{m['version']}` once, with the network")
    if sha256(w) != m["sha256"]:
        sys.exit(f"zeus-score: {w} doesn't match the registry's sha256; fetch it again")


def extract(archive: Path, into: Path, files: set[str] = ENGINES["zeus"]["files"]) -> None:
    """The model's files, flat, into `into`: nothing else, no paths."""
    with tarfile.open(archive) as t:
        for member in t.getmembers():
            name = Path(member.name).name
            if member.isdir() or name.startswith("._"):  # macOS tar's metadata entries
                continue
            if not member.isfile() or name not in files:
                raise ValueError(f"unexpected {member.name} in {archive.name}")
            with t.extractfile(member) as src, open(into / name, "wb") as dst:
                shutil.copyfileobj(src, dst)


def uv(args: list[str], offline: bool, quiet: bool = False, engine: str = "zeus") -> int:
    cmd = ["uv", "run", "--quiet", "--python-preference", "only-managed", *(["--offline"] if offline else []),
           "--script", str(ENGINES[engine]["script"]), *args]
    return subprocess.call(cmd, env={**os.environ, "UV_PYTHON_INSTALL_DIR": str(PYTHON)},
                           stdout=subprocess.DEVNULL if quiet else None)


def labeler_commit() -> str | None:
    """The labeler commit this package was built from, when installed from git
    (None from a local folder: its checkout may have moved on since)."""
    try:
        info = json.loads(metadata.distribution("zeus-score").read_text("direct_url.json") or "{}")
    except metadata.PackageNotFoundError:
        return None
    commit = info.get("vcs_info", {}).get("commit_id")
    return commit[:7] if commit else None


def trained_on(m: dict) -> dict:
    """The registry's trained_on, with its other sources as every movement."""
    return {**{s: ["*"] for s in m.get("trained_on_other", [])}, **m["trained_on"]}


def cmd_fetch(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="zeus-score fetch")
    ap.add_argument("model", nargs="?", help="NAME[@VERSION]; the default model if left out")
    ap.add_argument("--cache", type=Path, default=CACHE)
    a = ap.parse_args(argv)
    m = find(a.model)
    eng = ENGINES[engine_of(m)]
    d = folder(a.cache, m)
    if (d / eng["weights"]).exists() and sha256(d / eng["weights"]) == m["sha256"]:
        print(f"{m['name']}@{m['version']} is already in {d}")
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=d.parent) as tmp:
            archive = Path(tmp) / "model.tar.gz"
            print(f"fetching {m['url']}")
            with urllib.request.urlopen(m["url"], timeout=60) as r, open(archive, "wb") as f:
                shutil.copyfileobj(r, f)
            if sha256(archive) != m["archive_sha256"]:
                sys.exit(f"zeus-score: {m['url']} doesn't match the registry's archive_sha256")
            staged = Path(tmp) / "model"
            staged.mkdir()
            extract(archive, staged, eng["files"])
            check(staged, m)
            if d.exists():
                shutil.rmtree(d)
            staged.rename(d)
        print(f"{m['name']}@{m['version']} is in {d} ({m['licence']})")
    print(f"building the scoring environment ({eng['env']}) if it isn't built")
    if uv(["--help"], offline=False, quiet=True, engine=engine_of(m)):
        return 1
    built = env_built(engine_of(m))
    built.parent.mkdir(parents=True, exist_ok=True)
    built.write_text(metadata.version("zeus-score") if has_dist() else "")
    return 0


def has_dist() -> bool:
    try:
        metadata.distribution("zeus-score")
        return True
    except metadata.PackageNotFoundError:
        return False


def cmd_models(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="zeus-score models")
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--json", action="store_true", help="the registry as it is")
    a = ap.parse_args(argv)
    if a.json:
        print(REGISTRY.read_text())
        return 0
    for m in registry():
        fetched = (folder(a.cache, m) / ENGINES[engine_of(m)]["weights"]).exists()
        print(f"{m['name']}@{m['version']}{'  (default)' if m.get('default') else ''}"
              f"{'' if fetched else '  (not fetched)'}")
        print(f"  engine: {engine_of(m)}")
        print(f"  licence: {m['licence']}")
        print(f"  trained on: " + "; ".join(f"{s} {' '.join(v)}" for s, v in m["trained_on"].items())
              + (f"; and {len(m.get('trained_on_other', []))} other sources" if m.get("trained_on_other") else ""))
        for src, acc in m.get("accuracy", {}).items():  # (a source held out whole names no movements)
            print(f"  held out, {' '.join([src, *acc.get('movements', [])])}: {acc['bars_exact']:.0%} of bars exact"
                  + (f", {acc['events_right']:.0%} of events right" if "events_right" in acc else ""))
        print(f"  trained at labeler {m['trained_at']}; sha256 {m['sha256'][:12]}…")
    return 0


def cmd_compare(argv: list[str]) -> int:
    """Two sets of notes compared: no model, in the default model's environment."""
    eng = engine_of(find(None))
    commit = labeler_commit()
    code = uv(["compare", *argv, *(["--labeler-commit", commit] if commit else [])], offline=True, engine=eng)
    if code and not env_built(eng).exists():
        print("zeus-score: the scoring environment may not be built: run `zeus-score fetch` once, with the network",
              file=sys.stderr)
    return code


def cmd_score(argv: list[str]) -> int:
    """Scoring, and `read` (argv[0]): a model's run, in its engine's environment."""
    ap = argparse.ArgumentParser(prog="zeus-score", add_help=False)
    ap.add_argument("--model")
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("-h", "--help", action="store_true")
    a, rest = ap.parse_known_args(argv)
    if a.help and rest[:1] == ["read"]:
        return uv([*rest, "--help"], offline=True, engine="musvit")
    if a.help:
        print(__doc__)
        print("The scoring options (tools/zeus_score.py's):\n", flush=True)
        return uv(["--help"], offline=True)
    fetch = "zeus-score fetch"
    if a.model and is_path(a.model):
        model, eng = ["--model", a.model], engine_at(Path(a.model))
        fetch += f" {find(None)['name']}" if eng == "musvit" else ""  # the default reader
    else:
        m = find(a.model)
        eng = engine_of(m)
        fetch += f" {m['name']}@{m['version']}" if a.model else ""
        d = folder(a.cache, m)
        check(d, m)
        model = ["--model", str(d), "--model-name", m["name"], "--model-version", m["version"],
                 "--model-sha256", m["sha256"], "--trained-on", json.dumps(trained_on(m))]
    commit = labeler_commit()
    code = uv([*rest, *model, *(["--labeler-commit", commit] if commit else [])], offline=True, engine=eng)
    if code and not env_built(eng).exists():
        print(f"zeus-score: the scoring environment may not be built: run `{fetch}` once, with the network",
              file=sys.stderr)
    return code


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in ("--version", "version"):
        from zeus_score import __version__
        print(f"zeus-score {__version__}")
        sys.exit(0)
    if argv and argv[0] == "fetch":
        sys.exit(cmd_fetch(argv[1:]))
    if argv and argv[0] == "models":
        sys.exit(cmd_models(argv[1:]))
    if argv and argv[0] == "compare":
        sys.exit(cmd_compare(argv[1:]))
    sys.exit(cmd_score(argv))


if __name__ == "__main__":
    main()
