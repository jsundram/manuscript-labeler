"""Copies the labeler's scoring code into the package when it is built, so
there is one copy of it: from the labeler checkout around this folder, or,
building a wheel from an sdist, from the sdist, where it is already in place."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ENGINE = {
    "../tools/zeus_score.py": "zeus_score/engine/score.py",
    "../tools/musvit_score.py": "zeus_score/engine/musvit_score.py",
    "../experiments/musvit/proto.py": "zeus_score/engine/proto.py",
    "../experiments/zeus/compare.py": "zeus_score/engine/compare.py",
    "../experiments/zeus/dataset.py": "zeus_score/engine/dataset.py",
    "../labels.py": "zeus_score/engine/labels.py",
    "../structure.py": "zeus_score/engine/structure.py",
}


class Engine(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        for src, dst in ENGINE.items():
            if (root / src).exists():
                build_data["force_include"][str((root / src).resolve())] = dst
            elif not (root / dst).exists():
                raise FileNotFoundError(f"zeus-score: neither {src} nor {dst} is here to build from")
