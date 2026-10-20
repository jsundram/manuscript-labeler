# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
import io, pickle, time
from pathlib import Path
from PIL import Image
S = Path(__file__).parent
c = pickle.loads((S / "bench-crops.pkl").read_bytes())
crops = list(c.values())[:64]
def png(b):
    buf = io.BytesIO(); Image.open(io.BytesIO(b)).save(buf, "PNG"); return buf.getvalue()
crops = [png(b) for b in crops]
from zeus import InferenceOptions, Zeus
model = Zeus.load(Path.home() / ".cache/manuscript-labeler/models/zeus/J-lr1e5-e8@2026-10-16")
for rep in range(2):
    t0 = time.time()
    out = list(model.predict(crops, InferenceOptions(batch_size=8)))
    print(f"Zeus J: {len(crops)} staves in {time.time() - t0:.1f} s, {(time.time() - t0) / len(crops):.3f} s a staff")
