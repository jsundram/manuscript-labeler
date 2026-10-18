"""The zeus-score package's launcher (zeus-score/zeus_score/cli.py): its
registry, the model check, unpacking and fetching. Zeus itself isn't run."""

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "zeus-score"))
from zeus_score import cli  # noqa: E402

MODELS = [
    {"name": "A", "version": "2026-01-01", "sha256": "x"},
    {"name": "A", "version": "2026-02-01", "sha256": "y", "default": True},
    {"name": "B", "version": "2026-01-15", "sha256": "z"},
]


def archive(path: Path, files: dict[str, bytes], top="M") -> Path:
    with tarfile.open(path, "w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return path


def test_find():
    assert cli.find(None, MODELS)["version"] == "2026-02-01"
    assert cli.find("A", MODELS)["version"] == "2026-02-01"  # the latest
    assert cli.find("A@2026-01-01", MODELS)["sha256"] == "x"
    assert cli.find("B", MODELS)["sha256"] == "z"
    with pytest.raises(SystemExit):
        cli.find("C", MODELS)
    with pytest.raises(SystemExit):
        cli.find("A@2025-12-31", MODELS)


def test_registry():
    """One default; every entry has what the edition reads."""
    models = cli.registry()
    assert sum(bool(m.get("default")) for m in models) == 1
    for m in models:
        for k in ("name", "version", "sha256", "archive_sha256", "url", "licence", "trained_on", "trained_at",
                  "accuracy"):
            assert m.get(k), (m["name"], k)
        assert "non-commercial" in m["licence"]
        assert m["url"].endswith(".tar.gz")


def test_is_path():
    assert cli.is_path("/x/J.model") and cli.is_path("J-lr1e5-e8.model") and cli.is_path("runs/x")
    assert not cli.is_path("J-lr1e5-e8") and not cli.is_path("J-lr1e5-e8@2026-10-16")


def test_check(tmp_path):
    m = {"name": "A", "version": "1", "sha256": hashlib.sha256(b"weights").hexdigest()}
    with pytest.raises(SystemExit, match="fetch"):
        cli.check(tmp_path, m)  # not fetched
    (tmp_path / "weights.h5").write_bytes(b"weights")
    cli.check(tmp_path, m)
    (tmp_path / "weights.h5").write_bytes(b"changed")
    with pytest.raises(SystemExit, match="sha256"):
        cli.check(tmp_path, m)


def test_extract(tmp_path):
    a = archive(tmp_path / "a.tar.gz", {"weights.h5": b"w", "LICENSE": b"l", "token_map.txt": b"t",
                                        "._weights.h5": b"macOS metadata"})
    out = tmp_path / "out"
    out.mkdir()
    cli.extract(a, out)
    assert sorted(p.name for p in out.iterdir()) == ["LICENSE", "token_map.txt", "weights.h5"]
    bad = archive(tmp_path / "b.tar.gz", {"../evil.py": b"x"}, top="")
    with pytest.raises(ValueError):
        cli.extract(bad, out)


def test_fetch(tmp_path, monkeypatch):
    files = {"weights.h5": b"weights", "LICENSE": b"CC BY-NC-SA", "token_map.txt": b"t"}
    a = archive(tmp_path / "m.tar.gz", files)
    m = {"name": "A", "version": "1", "default": True, "licence": "CC BY-NC-SA 4.0, non-commercial",
         "url": a.as_uri(), "sha256": hashlib.sha256(b"weights").hexdigest(),
         "archive_sha256": hashlib.sha256(a.read_bytes()).hexdigest()}
    monkeypatch.setattr(cli, "registry", lambda: [m])
    monkeypatch.setattr(cli, "ENV_BUILT", tmp_path / "env-built")
    calls = []
    monkeypatch.setattr(cli, "uv", lambda args, offline, quiet=False, engine="zeus": calls.append((args, offline)) or 0)
    cache = tmp_path / "cache"
    assert cli.cmd_fetch(["A", "--cache", str(cache)]) == 0
    assert (cache / "zeus" / "A@1" / "weights.h5").read_bytes() == b"weights"
    assert calls == [(["--help"], False)]  # the environment built online
    assert (tmp_path / "env-built").exists()
    assert cli.cmd_fetch(["--cache", str(cache)]) == 0  # already there: no download
    m["archive_sha256"] = "0" * 64
    import shutil
    shutil.rmtree(cache)
    with pytest.raises(SystemExit, match="archive_sha256"):
        cli.cmd_fetch(["A", "--cache", str(cache)])
    assert not (cache / "zeus" / "A@1").exists()


def test_score_args(tmp_path, monkeypatch):
    """A registry model goes to the scorer with its name, version and what it was trained on, offline."""
    (tmp_path / "zeus" / "A@1").mkdir(parents=True)
    (tmp_path / "zeus" / "A@1" / "weights.h5").write_bytes(b"w")
    m = {"name": "A", "version": "1", "default": True, "sha256": hashlib.sha256(b"w").hexdigest(),
         "trained_on": {"D-B_KHM-603": ["II"]}, "trained_on_other": ["Op32-G201-206"]}
    monkeypatch.setattr(cli, "registry", lambda: [m])
    monkeypatch.setattr(cli, "labeler_commit", lambda: "abc1234")
    calls = []
    monkeypatch.setattr(cli, "uv", lambda args, offline, quiet=False, engine="zeus": calls.append((args, offline)) or 0)
    assert cli.cmd_score(["--source", "S", "--cache", str(tmp_path), "--renders", "r"]) == 0
    args, offline = calls[0]
    assert offline
    assert args[:4] == ["--source", "S", "--renders", "r"]
    assert args[args.index("--model") + 1] == str(tmp_path / "zeus" / "A@1")
    assert args[args.index("--model-version") + 1] == "1"
    assert json.loads(args[args.index("--trained-on") + 1]) == {"D-B_KHM-603": ["II"], "Op32-G201-206": ["*"]}
    assert args[args.index("--model-sha256") + 1] == m["sha256"]
    assert args[args.index("--labeler-commit") + 1] == "abc1234"
    calls.clear()
    cli.cmd_score(["--model", "/some/X.model"])
    assert "--model-name" not in calls[0][0] and "/some/X.model" in calls[0][0]


def test_musvit_engine(tmp_path, monkeypatch):
    """A MuSViT entry: its own folder, weights file, archive files and scoring script."""
    m = {"name": "M", "version": "1", "default": True, "engine": "musvit", "sha256": hashlib.sha256(b"w").hexdigest(),
         "trained_on": {}}
    d = tmp_path / "musvit" / "M@1"
    assert cli.folder(tmp_path, m) == d
    d.mkdir(parents=True)
    with pytest.raises(SystemExit, match="fetch"):
        cli.check(d, m)
    (d / "reader.safetensors").write_bytes(b"w")
    cli.check(d, m)
    a = archive(tmp_path / "a.tar.gz", {"reader.safetensors": b"w", "reader.json": b"{}", "vocab.json": b"{}"})
    out = tmp_path / "out"
    out.mkdir()
    cli.extract(a, out, cli.ENGINES["musvit"]["files"])
    assert sorted(p.name for p in out.iterdir()) == ["reader.json", "reader.safetensors", "vocab.json"]
    with pytest.raises(ValueError):
        cli.extract(a, tmp_path)  # Zeus's files only
    monkeypatch.setattr(cli, "registry", lambda: [m])
    monkeypatch.setattr(cli, "labeler_commit", lambda: None)
    calls = []
    monkeypatch.setattr(cli, "uv", lambda args, offline, quiet=False, engine="zeus": calls.append(engine) or 0)
    cli.cmd_score(["--cache", str(tmp_path)])
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "reader.json").write_text("{}")
    cli.cmd_score(["--model", str(tmp_path / "x")])
    assert calls == ["musvit", "musvit"]
    assert cli.ENGINES["musvit"]["script"].name == "musvit_score.py"
