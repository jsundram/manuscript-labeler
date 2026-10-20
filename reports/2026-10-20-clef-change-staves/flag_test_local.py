# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy", "scipy", "pypdf"]
# ///
"""The edition's flag_test.py with one extra model from a local release
folder, not the registry: its scores go to the scratchpad, not build/.

    uv run flag_test_local.py FOLDER NAME@VERSION SHA256 -- <flag_test args>
"""
import subprocess, sys
from pathlib import Path
folder, spec, sha = sys.argv[1:4]
sys.argv = ["flag_test.py"] + sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, str(Path.home() / "Dropbox/Code/boccherini-opus-48/scripts"))
import encode, flag_test  # noqa: E402
name, _, version = spec.partition("@")
reg = encode.zeus_registry()
reg["models"].append({"name": name, "version": version, "sha256": sha, "engine": "musvit"})
encode.zeus_registry = lambda: reg
flag_test.OUT = Path(__file__).parent / "flag-test"
run = subprocess.run
def patched(cmd, *a, **k):
    if isinstance(cmd, list) and "--model" in cmd and cmd[cmd.index("--model") + 1] == spec:
        cmd = cmd[:]; i = cmd.index("--model") + 1
        cmd[i:i + 1] = [folder, "--model-name", name, "--model-version", version]
    return run(cmd, *a, **k)
flag_test.subprocess.run = patched
flag_test.main()
