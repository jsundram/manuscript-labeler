"""An open vision-language model served on a Modal GPU by vLLM, behind its
OpenAI-style API, for bars.py --backend openai.

    VLLM_API_KEY=<key> modal deploy experiments/llm/vllm_modal.py
    VLLM_MODEL=google/gemma-4-31B-it VLLM_GPU=H100 VLLM_API_KEY=<key> modal deploy ...
    VLLM_AGENT=1 VLLM_GPU=H100 VLLM_API_KEY=<key> modal deploy ...  # for agent_read.py
    VLLM_APP=labeler-glimmer VLLM_MODEL=meta-models/Muse-Glimmer-30B ...  # a second server beside the first
    modal app stop labeler-vllm                                  # when done

The model's weights land in the hf-cache volume, so only the first start
downloads them. The server scales to zero 10 minutes after its last request;
stop the app anyway when a run is finished. The key is any string: the
server refuses requests without it, and bars.py sends it from VLLM_API_KEY.

VLLM_AGENT=1 sets the server up for agent_read.py: tool calls, a 128k
context, a few long conversations at a time and pictures without limit.
"""

import os
import subprocess

import modal

MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3.6-27B-FP8")  # FP8 fits one 48 GB L40S
GPU = os.environ.get("VLLM_GPU", "L40S")
APP = os.environ.get("VLLM_APP", "labeler-vllm")  # its URL: https://<workspace>--<app>-serve.<region>.modal.run
# vLLM's parsers for each family's thinking and tool calls
PARSERS = {"Qwen": ("qwen3", "qwen3_coder"), "gemma-4": ("gemma4", "gemma4"), "Muse-Glimmer": ("muse_glimmer", "muse_glimmer")}
REASONING, TOOL_CALLS = next((p for k, p in PARSERS.items() if k in MODEL), ("", ""))
BASE = os.environ.get("VLLM_EXTRA", f"--reasoning-parser {REASONING}" if REASONING else "")  # thinking kept apart
AGENT = os.environ.get("VLLM_AGENT", "")
EXTRA = BASE + (f" --enable-auto-tool-choice --tool-call-parser {TOOL_CALLS}" if AGENT else "")
# --max-num-seqs: vLLM's default of 256 needs more Mamba cache than one GPU leaves (2026-11-03)
LIMITS = (["--max-model-len", "131072", "--limit-mm-per-prompt", '{"image": 1000}', "--max-num-seqs", "8"] if AGENT
          else ["--max-model-len", "32768", "--limit-mm-per-prompt", '{"image": 48}', "--max-num-seqs", "32"])
PORT = 8000

image = (modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.12")
         .entrypoint([])
         .uv_pip_install("vllm==0.33.0", "huggingface_hub")
         .env({"VLLM_MODEL": MODEL, "VLLM_GPU": GPU, "VLLM_EXTRA": BASE, "VLLM_AGENT": AGENT, "VLLM_APP": APP}))
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)
app = modal.App(APP)


@app.function(image=image, gpu=GPU, timeout=4 * 3600, scaledown_window=10 * 60,
              volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
              secrets=[modal.Secret.from_dict({"VLLM_API_KEY": os.environ.get("VLLM_API_KEY", "")})])
@modal.concurrent(max_inputs=32)
@modal.web_server(port=PORT, startup_timeout=40 * 60)
def serve():
    if not os.environ.get("VLLM_API_KEY"):
        raise SystemExit("vllm_modal: deploy with VLLM_API_KEY set")
    subprocess.Popen(["vllm", "serve", MODEL, "--host", "0.0.0.0", "--port", str(PORT),
                      "--served-model-name", MODEL, "--api-key", os.environ["VLLM_API_KEY"],
                      *LIMITS, "--enable-prefix-caching", "--gpu-memory-utilization", "0.92", *EXTRA.split()])
