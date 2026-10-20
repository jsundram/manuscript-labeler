# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy"]
# ///
"""Prototype: MuSViT's encoder with a transformer decoder that writes LMX,
trained on dataset.py's staves (BRIEF.md, "Order of work" 1).

    uv run experiments/musvit/proto.py NAME --train SAMPLES... --dev SAMPLES...
        [--encoder light|full] [--epochs 20] [--lr 3e-4] [--limit N] [--overfit]

SAMPLES are dataset.py's samples.*.txt (each line a stave's path without
suffix; .jpg and .lmx beside it). Staves are read at 128 px high (--height) and their
own width (rounded to 16 px). The encoder gets LoRA adapters on its
attention; the decoder is plain torch.nn (no NVIDIA-only kernels), so the
same code runs on the CPU, the Mac's GPU (mps) and CUDA.

Two stages (BRIEF.md): stage 1 on public staves with --vocab-extra naming
the stage 2 data, so one vocabulary covers both; stage 2 with --init STAGE1.

Long runs (the public stage) can be resumed: --checkpoint saves the whole
training state after every pass (runs/NAME/state.pt: weights, optimizer,
schedule, pass, random state), and --resume continues from it with the same
command, or starts if there's none. --schedule wsd holds the learning rate
after warmup and decays it over the last --decay share of passes, so a run
resumed before its decay began can be given more --epochs.

--overfit trains and scores on the same staves: the pipeline works if it
learns them exactly. Each epoch prints the dev staves' symbol error rate
(SER, edit distance over reference length) and exact staves; the model and
log go to runs/NAME/ under $MUSVIT_CACHE (default
~/.cache/manuscript-labeler/musvit). On Modal: modal_app.py.
"""

import argparse
import contextlib
import io
import json
import math
import os
import random
import re
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn

CACHE = Path(os.environ.get("MUSVIT_CACHE", Path.home() / ".cache" / "manuscript-labeler" / "musvit"))
ENCODERS = {"light": CACHE / "weights" / "musvit-light", "full": CACHE / "weights" / "musvit"}
H, PATCH, MAXW, MAXLEN = 128, 16, 2688, 512  # H: the strip's height (--height); a run's config.json records it
PAD, BOS, EOS, UNK = "<pad>", "<s>", "</s>", "<unk>"
AMP = False  # bfloat16 autocast on CUDA (--amp); a run's config.json records it
COLOR = False  # read staves in colour, three channels (--color), not grey copied to three; config.json records it


def autocast():
    return torch.autocast("cuda", dtype=torch.bfloat16) if AMP else contextlib.nullcontext()


def staves(samples: list[Path], limit: int | None = None) -> list[tuple[Path, list[str]]]:
    out = []
    for f in samples:
        for line in f.read_text().split():
            p = f.parent / line
            out.append((p.with_suffix(".jpg"), p.with_suffix(".lmx").read_text().split()))
    if limit:
        random.Random(0).shuffle(out)
        out = out[:limit]
    return out


def opened(src) -> Image.Image:
    """A stave image from its path, or its encoded bytes (read_crops)."""
    return Image.open(io.BytesIO(src) if isinstance(src, bytes) else src)


def image(path, shift: int = 0) -> torch.Tensor:
    """A staff H px high (128 unless --height), its width by aspect: (H, w) grey, or (3, H, w) with COLOR."""
    im = opened(path).convert("RGB" if COLOR else "L")
    w = min(MAXW, round(im.width * H / im.height / PATCH) * PATCH)
    a = np.asarray(im.resize((w, H), Image.BILINEAR), dtype=np.float32) / 255
    if shift:  # Zeus's h:8, a sideways shift: white in on one side, ink out the other
        a = np.roll(a, shift, axis=1)
        if shift > 0:
            a[:, :shift] = 1
        else:
            a[:, shift:] = 1
    return torch.from_numpy(a).permute(2, 0, 1).contiguous() if COLOR else torch.from_numpy(a)


def zeus_augment(a: np.ndarray) -> np.ndarray:
    """Zeus's fuller augmentation (its paper, section 5), each step with a 50%
    chance, after the sideways shift: rotation up to 1 degree, vertical shift
    up to 4 px, dilation or erosion, up to 20% of edge pixels negated, 1% of
    all pixels negated, contrast by 2^U(-1,1), brightness by U(-0.5,0.2)."""
    from PIL import ImageFilter
    im = Image.fromarray((a * 255).astype(np.uint8))
    if random.random() < .5:
        im = im.rotate(random.uniform(-1, 1), resample=Image.BILINEAR, fillcolor=255)
    if random.random() < .5:
        im = im.transform(im.size, Image.AFFINE, (1, 0, 0, 0, 1, random.randint(-4, 4)), fillcolor=255)
    if random.random() < .5:  # ink is dark: MaxFilter thins it (erosion), MinFilter thickens it (dilation)
        im = im.filter(ImageFilter.MaxFilter(3) if random.random() < .5 else ImageFilter.MinFilter(3))
    a = np.asarray(im, dtype=np.float32) / 255
    if random.random() < .5:
        edge = np.abs(np.gradient(a)[0]) + np.abs(np.gradient(a)[1]) > 0.1
        flip = edge & (np.random.random(a.shape) < random.uniform(0, .2))
        a = np.where(flip, 1 - a, a)
    if random.random() < .5:
        a = np.where(np.random.random(a.shape) < random.uniform(0, .01), 1 - a, a)
    if random.random() < .5:
        a = np.clip((a - .5) * 2 ** random.uniform(-1, 1) + .5, 0, 1)
    if random.random() < .5:
        a = np.clip(a + random.uniform(-.5, .2), 0, 1)
    return a.astype(np.float32)


AUGMENT = "shift"  # or "zeus" (--augment): see zeus_augment


def batch(items, vocab, augment=False):
    ims = [image(p, random.randint(-8, 8) if augment else 0) for p, _ in items]
    if augment and AUGMENT == "zeus":
        assert not COLOR, "Zeus's augmentation is for grey staves"
        ims = [torch.from_numpy(zeus_augment(i.numpy())) for i in ims]
    W = max(i.shape[-1] for i in ims)
    x = torch.ones(len(ims), 3, H, W)
    cols = torch.zeros(len(ims), W // PATCH, dtype=torch.bool)  # True = padding
    for k, im in enumerate(ims):
        x[k, :, :, : im.shape[-1]] = im
        cols[k, im.shape[-1] // PATCH:] = True
    # patch order is row-major over (H/16, W/16), after the CLS token
    mask = torch.cat([torch.zeros(len(ims), 1, dtype=torch.bool), cols.repeat(1, H // PATCH)], 1)
    ids = [[vocab.get(t, vocab[UNK]) for t in toks][: MAXLEN - 1] for _, toks in items]
    L = max(len(i) for i in ids) + 1
    y_in = torch.full((len(ids), L), vocab[PAD])
    y_out = torch.full((len(ids), L), vocab[PAD])
    for k, i in enumerate(ids):
        y_in[k, : len(i) + 1] = torch.tensor([vocab[BOS]] + i)
        y_out[k, : len(i) + 1] = torch.tensor(i + [vocab[EOS]])
    return x, mask, y_in, y_out


class LSTMHead(nn.Module):
    """A decoder after Zeus's: LSTMs over the symbols written so far, with
    attention to the encoder's patches. Zeus feeds each step's attention
    back into its LSTM (one step at a time); here an LSTM reads the
    symbols, attends, and a second LSTM reads what it attended to, so a
    staff trains in one pass (Luong's form, without input feeding)."""

    def __init__(self, d: int, n_vocab: int, dropout=0.2):
        super().__init__()
        self.embed = nn.Embedding(n_vocab, d)
        self.lstm1 = nn.LSTM(d, d, batch_first=True)
        self.query = nn.Linear(d, d)
        self.lstm2 = nn.LSTM(2 * d, d, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(d, n_vocab)

    def forward(self, mem, mask, y):
        h, _ = self.lstm1(self.drop(self.embed(y)))
        scores = self.query(h) @ mem.transpose(1, 2) / math.sqrt(h.shape[-1])
        scores = scores.masked_fill(mask[:, None, :], float("-inf"))
        ctx = torch.softmax(scores.float(), -1).to(mem.dtype) @ mem
        g, _ = self.lstm2(self.drop(torch.cat([h, ctx.to(h.dtype)], -1)))
        return self.out(self.drop(g))


class ZeusHead(nn.Module):
    """Zeus's decoder (zeus/model/rnn_cells_with_attention.py and
    keras_model.py): at each step, Bahdanau attention from the first LSTM's
    state to the encoder's memory; what it attends to joins the symbol's
    embedding as the LSTMs' input, so where it looked feeds into where it
    looks next. Two LSTM layers, the second added to the first's output.
    One step at a time, in training too."""

    def __init__(self, d: int, n_vocab: int, layers=2, att=256, dropout=0.2):
        super().__init__()
        self.d = d
        self.embed = nn.Embedding(n_vocab, d)
        self.enc_proj = nn.Linear(d, att)
        self.dec_proj = nn.Linear(2 * d, att)
        self.v = nn.Linear(att, 1)
        self.cells = nn.ModuleList([nn.LSTMCell(2 * d if i == 0 else d, d) for i in range(layers)])
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(d, n_vocab)

    def start(self, mem, mask) -> dict:
        z = mem.new_zeros(mem.shape[0], self.d, dtype=torch.float32)
        return {"mem": mem, "mask": mask, "proj": self.enc_proj(mem), "h": [z] * len(self.cells), "c": [z] * len(self.cells)}

    def step(self, st: dict, tok):
        q = self.dec_proj(torch.cat([st["h"][0], st["c"][0]], -1).to(st["proj"].dtype))[:, None]
        e = self.v(torch.tanh(st["proj"] + q)).squeeze(-1).float().masked_fill(st["mask"], float("-inf"))
        ctx = (torch.softmax(e, -1)[..., None] * st["mem"].float()).sum(1)
        inp = torch.cat([self.drop(self.embed(tok)).float(), ctx], -1)
        hs, cs = [], []
        for i, cell in enumerate(self.cells):
            h, c = cell(inp, (st["h"][i], st["c"][i]))
            inp = h if i == 0 else inp + h
            hs.append(h)
            cs.append(c)
        return self.out(self.drop(inp)), {**st, "h": hs, "c": cs}

    def forward(self, mem, mask, y):
        st, outs = self.start(mem, mask), []
        for t in range(y.shape[1]):
            o, st = self.step(st, y[:, t])
            outs.append(o)
        return torch.stack(outs, 1)


class Reader(nn.Module):
    def __init__(self, encoder: str, n_vocab: int, d=256, layers=4, lora_r=16, lora_mlp=False, decoder="transformer",
                 memory="patches"):
        super().__init__()
        from transformers import ViTConfig, ViTModel
        if isinstance(encoder, dict):  # a released reader: the encoder's config, its weights in the reader's file
            enc = ViTModel(ViTConfig(**encoder), add_pooling_layer=False)
        else:
            enc = ViTModel.from_pretrained(ENCODERS.get(encoder, CACHE / "weights" / encoder), add_pooling_layer=False)
        self.encoder = enc
        if lora_r:  # 0: no adapters (a released reader has them folded in)
            from peft import LoraConfig, get_peft_model
            targets = ["q_proj", "k_proj", "v_proj"] + (["o_proj", "fc1", "fc2"] if lora_mlp else [])
            self.encoder = get_peft_model(enc, LoraConfig(r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.1,
                                                          target_modules=targets))
        # memory "columns": each column's 8 patches joined into one vector, as Zeus packs a column's height
        self.memory = memory
        self.project = nn.Linear(enc.config.hidden_size * (H // PATCH if memory == "columns" else 1), d)
        self.embed = nn.Embedding(n_vocab, d)
        angle = torch.arange(MAXLEN)[:, None] * torch.exp(torch.arange(0, d, 2) * (-math.log(10000.0) / d))
        pos = torch.zeros(MAXLEN, d)
        pos[:, 0::2], pos[:, 1::2] = torch.sin(angle), torch.cos(angle)
        self.register_buffer("pos", pos)
        layer = nn.TransformerDecoderLayer(d, 8, 4 * d, dropout=0.1, batch_first=True, norm_first=True)
        self.decoder = nn.TransformerDecoder(layer, layers, norm=nn.LayerNorm(d))
        self.out = nn.Linear(d, n_vocab)
        self.lstm = LSTMHead(d, n_vocab) if decoder == "lstm" else None
        self.zeus = ZeusHead(d, n_vocab) if decoder == "zeus" else None
        if self.lstm is not None or self.zeus is not None:  # the transformer's parts go unused
            del self.decoder, self.out, self.embed

    def readapt(self, lora_r: int, lora_mlp: bool):
        """Fold the encoder's adapters into its weights and give it fresh,
        possibly larger ones (stage 2 from a stage-1 run): the whole encoder
        is then saved with the reader."""
        from peft import LoraConfig, get_peft_model
        targets = ["q_proj", "k_proj", "v_proj"] + (["o_proj", "fc1", "fc2"] if lora_mlp else [])
        self.encoder = get_peft_model(self.encoder.merge_and_unload(),
                                      LoraConfig(r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.1, target_modules=targets))

    def unfreeze_top(self, n: int) -> list[str]:
        """Let the encoder's top n layers' own weights train (and its final
        norm); the names of those weights, saved with the reader."""
        if not n:
            return []
        layers = {int(m) for name, _ in self.encoder.named_parameters() for m in re.findall(r"layers\.(\d+)\.", name)}
        top = {f"layers.{i}." for i in sorted(layers)[-n:]}
        names = []
        for name, prm in self.encoder.named_parameters():
            if "lora" not in name and (any(t in name for t in top) or ".layernorm." in name):
                prm.requires_grad = True
                names.append("encoder." + name)
        return names

    def encode(self, x):
        hs = self.encoder(pixel_values=x, interpolate_pos_encoding=True).last_hidden_state
        if self.memory == "columns":  # drop CLS; (B, rows*cols, D) row-major -> (B, cols, rows*D)
            b, n, dim = hs[:, 1:].shape
            hs = hs[:, 1:].reshape(b, H // PATCH, n // (H // PATCH), dim).permute(0, 2, 1, 3).reshape(b, -1, (H // PATCH) * dim)
        return self.project(hs)

    @staticmethod
    def fit_mask(mem, mask):
        """batch()'s mask is over CLS and every patch; for column memory, the first row's columns."""
        return mask if mask.shape[1] == mem.shape[1] else mask[:, 1:1 + mem.shape[1]]

    def decode(self, mem, mask, y):
        mask = self.fit_mask(mem, mask)
        if self.lstm is not None:
            return self.lstm(mem, mask, y)
        if self.zeus is not None:
            return self.zeus(mem, mask, y)
        L = y.shape[1]
        causal = torch.triu(torch.full((L, L), float("-inf"), device=y.device), 1)
        h = self.embed(y) + self.pos[:L]
        return self.out(self.decoder(h, mem, tgt_mask=causal, memory_key_padding_mask=mask))

    @torch.no_grad()
    def read(self, x, mask, bos, eos, maxlen=MAXLEN):
        with autocast():
            mem = self.encode(x)
        y = torch.full((x.shape[0], 1), bos, device=x.device)
        done = torch.zeros(x.shape[0], dtype=torch.bool, device=x.device)
        if self.zeus is not None:  # its state carries the past: one step per symbol
            with autocast():
                st = self.zeus.start(mem, self.fit_mask(mem, mask))
            for _ in range(maxlen - 1):
                with autocast():
                    logits, st = self.zeus.step(st, y[:, -1])
                nxt = logits.argmax(-1)
                y = torch.cat([y, nxt[:, None]], 1)
                done |= nxt == eos
                if done.all():
                    break
            return [row[: row.index(eos)] if eos in row else row for row in y[:, 1:].tolist()]
        if self.lstm is None:
            return self.read_cached(mem, mask, bos, eos, maxlen)
        for _ in range(maxlen - 1):
            with autocast():
                nxt = self.decode(mem, mask, y)[:, -1].argmax(-1)
            y = torch.cat([y, nxt[:, None]], 1)
            done |= nxt == eos
            if done.all():
                break
        out = []
        for row in y[:, 1:].tolist():
            out.append(row[: row.index(eos)] if eos in row else row)
        return out

    @torch.no_grad()
    def read_cached(self, mem, mask, bos, eos, maxlen=MAXLEN):
        """The transformer decoder's greedy reading, one position a step: each
        layer keeps the keys and values of the image (made once) and of the
        symbols so far, so a symbol costs one position, not the whole
        prefix. The same arithmetic as decode() (pre-norm layers), in eval."""
        import torch.nn.functional as F
        mask = self.fit_mask(mem, mask)
        b, d = mem.shape[0], mem.shape[-1]
        layers = self.decoder.layers
        nh = layers[0].self_attn.num_heads

        def heads(t):  # (B, L, d) -> (B, heads, L, d / heads)
            return t.reshape(b, -1, nh, d // nh).transpose(1, 2)

        def joined(t):
            return t.transpose(1, 2).reshape(b, -1, d)

        see = (~mask)[:, None, None, :]  # True where the image is, not padding
        with autocast():
            cross = [(heads(F.linear(mem, l.multihead_attn.in_proj_weight[d: 2 * d], l.multihead_attn.in_proj_bias[d: 2 * d])),
                      heads(F.linear(mem, l.multihead_attn.in_proj_weight[2 * d:], l.multihead_attn.in_proj_bias[2 * d:])))
                     for l in layers]
        past = [[None, None] for _ in layers]
        tok = torch.full((b,), bos, device=mem.device)
        ys, done = [], torch.zeros(b, dtype=torch.bool, device=mem.device)
        for t in range(maxlen - 1):
            with autocast():
                h = (self.embed(tok) + self.pos[t])[:, None]
                for l, (ck, cv), kv in zip(layers, cross, past):
                    q, k, v = F.linear(l.norm1(h), l.self_attn.in_proj_weight, l.self_attn.in_proj_bias).chunk(3, -1)
                    kv[0] = heads(k) if kv[0] is None else torch.cat([kv[0], heads(k)], 2)
                    kv[1] = heads(v) if kv[1] is None else torch.cat([kv[1], heads(v)], 2)
                    h = h + l.self_attn.out_proj(joined(F.scaled_dot_product_attention(heads(q), kv[0], kv[1])))
                    q = F.linear(l.norm2(h), l.multihead_attn.in_proj_weight[:d], l.multihead_attn.in_proj_bias[:d])
                    h = h + l.multihead_attn.out_proj(joined(F.scaled_dot_product_attention(heads(q), ck, cv, attn_mask=see)))
                    h = h + l.linear2(l.activation(l.linear1(l.norm3(h))))
                tok = self.out(self.decoder.norm(h[:, 0])).argmax(-1)
            ys.append(tok)
            done |= tok == eos
            if done.all():
                break
        return [row[: row.index(eos)] if eos in row else row for row in torch.stack(ys, 1).tolist()]


def load(run: str, file: str = "reader.pt"):
    """A trained reader and its vocabulary, from runs/RUN/ (its encoder,
    decoder depth and precision from config.json; the first runs, without
    one, were MuSViT-light, 4 layers, float32)."""
    global AMP, COLOR, H
    vocab = json.loads((CACHE / "runs" / run / "vocab.json").read_text())
    cfg = {"encoder": "light", "layers": 4, "amp": False, "lora_r": 16, "lora_mlp": False, "decoder": "transformer",
           "memory": "patches"}
    if (CACHE / "runs" / run / "config.json").exists():
        cfg |= json.loads((CACHE / "runs" / run / "config.json").read_text())
    AMP = cfg["amp"] and torch.cuda.is_available()
    COLOR = cfg.get("color", False)
    H = cfg.get("height", 128)
    model = Reader(cfg["encoder"], len(vocab), layers=cfg["layers"], lora_r=cfg["lora_r"], lora_mlp=cfg["lora_mlp"],
                   decoder=cfg["decoder"], memory=cfg["memory"])
    got = model.load_state_dict(torch.load(CACHE / "runs" / run / file, map_location="cpu"), strict=False)
    assert not got.unexpected_keys and all(k.startswith("encoder.") and "lora" not in k for k in got.missing_keys), got
    return model, vocab



def load_release(folder: Path):
    """A released reader (release.py) and its vocabulary: reader.json (the
    encoder's config, the decoder's shape), vocab.json and
    reader.safetensors, the adapters folded in. Needs no MuSViT download
    and no peft."""
    from safetensors.torch import load_file
    global COLOR, H
    cfg = json.loads((folder / "reader.json").read_text())
    COLOR = cfg.get("color", False)
    H = cfg.get("height", 128)
    vocab = json.loads((folder / "vocab.json").read_text())
    model = Reader(cfg["vit"], len(vocab), d=cfg["d"], layers=cfg["layers"], lora_r=0, decoder=cfg["decoder"],
                   memory=cfg["memory"])
    model.load_state_dict({k: v.float() for k, v in load_file(folder / "reader.safetensors").items()})
    return model, vocab

def for_reading(model, device: str):
    """A trained reader made ready to read (not to train): the encoder's
    adapters folded into its weights, and on the Mac's GPU half precision
    (together 1.45x faster there; 63 of 64 clean-test staves read the same)."""
    if hasattr(model.encoder, "merge_and_unload"):
        model.encoder = model.encoder.merge_and_unload()
    model = model.to(device).eval()
    return model.half() if device == "mps" else model


def read_crops(run: str, file: str, crops: dict[str, bytes], device: str, bs: int = 8) -> dict[str, str]:
    """Read staff crops (encoded images, by key) with a trained reader:
    the LMX for each, in width-sorted batches as in training."""
    model, vocab = load(run, file)
    model = for_reading(model, device)
    dtype = next(model.parameters()).dtype
    inv = {i: t for t, i in vocab.items()}
    items = sorted(((png, key) for key, png in crops.items()), key=aspect)
    out = {}
    for k in range(0, len(items), bs):
        chunk = items[k: k + bs]
        x, mask, _, _ = batch([(png, []) for png, _ in chunk], vocab)
        for (_, key), ids in zip(chunk, model.read(x.to(device, dtype), mask.to(device), vocab[BOS], vocab[EOS])):
            out[key] = " ".join(inv[i] for i in ids)
    return out


@torch.no_grad()
def beam(model, x, mask, bos: int, eos: int, k: int = 8, maxlen: int = MAXLEN) -> list[tuple[list[int], float]]:
    """Beam search for one staff (x: 1 image): up to k finished readings
    with their log-probabilities, most likely first."""
    with autocast():
        mem = model.encode(x)
    live = [([bos], 0.0)]
    done = []
    for _ in range(maxlen - 1):
        y = torch.tensor([s for s, _ in live], device=x.device)
        with autocast():
            lp = torch.log_softmax(model.decode(mem.expand(len(live), -1, -1), mask.expand(len(live), -1), y)[:, -1].float(), -1)
        top_lp, top_i = lp.topk(k, -1)
        cand = sorted(((score + float(top_lp[j, m]), seq + [int(top_i[j, m])])
                       for j, (seq, score) in enumerate(live) for m in range(k)), reverse=True)
        live = []
        for score, seq in cand:
            (done if seq[-1] == eos else live).append((seq, score))
            if len(live) == k:
                break
        if len(done) >= k or not live or (done and max(sc for _, sc in done) > live[0][1]):
            break
    done = done or live
    return sorted(((seq[1:-1] if seq[-1] == eos else seq[1:], sc) for seq, sc in done), key=lambda t: -t[1])[:k]


def read_nbest(run: str, file: str, crops: dict[str, bytes], device: str, k: int = 8) -> dict[str, list]:
    """Up to k readings of each staff crop, with log-probabilities (beam)."""
    model, vocab = load(run, file)
    model = model.to(device).eval()
    inv = {i: t for t, i in vocab.items()}
    out = {}
    for key, png in crops.items():
        x, mask, _, _ = batch([(png, [])], vocab)
        out[key] = [[" ".join(inv[i] for i in ids), round(sc, 3)]
                    for ids, sc in beam(model, x.to(device), mask.to(device), vocab[BOS], vocab[EOS], k)]
    return out


def edits(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def aspect(item) -> float:
    w, h = opened(item[0]).size
    return w / h


def score(model, items, vocab, dev, bs=8):
    """Read the staves in batches of similar width, as in training: the
    encoder attends to a batch's white padding too, and stretches its
    position embeddings over the padded width, so a staff batched with a
    much wider one is read differently."""
    model.eval()
    items = sorted(items, key=aspect)
    inv = {i: t for t, i in vocab.items()}
    errs = capped = ref = exact = runaway = 0
    shown = []
    for k in range(0, len(items), bs):
        chunk = items[k: k + bs]
        x, mask, _, _ = batch(chunk, vocab)
        got = model.read(x.to(dev), mask.to(dev), vocab[BOS], vocab[EOS])
        for (p, toks), g in zip(chunk, got):
            g = [inv[i] for i in g]
            e = edits(g, toks)
            errs, ref, exact = errs + e, ref + len(toks), exact + (e == 0)
            # a runaway (a reading looping past the staff's end) can swamp the rate: also score it cut at twice the answer
            runaway += len(g) > 2 * len(toks)
            capped += edits(g[: 2 * len(toks)], toks)
            if len(shown) < 1:
                shown.append((p.parent.name + "/" + p.stem, " ".join(toks[:24]), " ".join(g[:24])))
    model.train()
    return errs / max(ref, 1), exact, shown, capped / max(ref, 1), runaway


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--train", nargs="+", type=Path, required=True)
    ap.add_argument("--dev", nargs="+", type=Path, default=[])
    ap.add_argument("--encoder", default="light", help="light, full, or weights/<NAME> in the cache (pretrain.py)")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--layers", type=int, default=4, help="the transformer decoder's layers")
    ap.add_argument("--decoder", choices=["transformer", "lstm", "zeus"], default="transformer",
                    help="a new run's decoder (LSTMHead; ZeusHead)")
    ap.add_argument("--memory", choices=["patches", "columns"], default="patches",
                    help="what the decoder attends to: every patch, or each column's patches joined (a new run)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dev-limit", type=int)
    ap.add_argument("--vocab-extra", nargs="+", type=Path, default=[],
                    help="more samples files whose tokens join the vocabulary (stage 1: the stage 2 data)")
    ap.add_argument("--init", help="start from this run's reader.pt and vocabulary (stage 2)")
    ap.add_argument("--init-file", default="reader.pt", help="or its best.pt; with --epochs 0, just score --dev")
    ap.add_argument("--eval-every", type=int, default=1)
    ap.add_argument("--overfit", action="store_true")
    ap.add_argument("--patience", type=int, default=0,
                    help="stop after this many scorings of --dev without a better SER (0: run all --epochs)")
    ap.add_argument("--amp", action="store_true", help="bfloat16 autocast (CUDA)")
    ap.add_argument("--lora-r", type=int, help="LoRA rank (default 16; with --init, fold its adapters in and start fresh ones)")
    ap.add_argument("--lora-mlp", action="store_true", help="LoRA on the attention output and MLP too (as --lora-r)")
    ap.add_argument("--unfreeze-top", type=int, default=0, help="train the encoder's top N layers' own weights too")
    ap.add_argument("--encoder-lr", type=float, default=0.1, help="their learning rate, as a share of --lr")
    ap.add_argument("--augment", choices=["shift", "zeus"], default="shift",
                    help="shift: sideways up to 8 px; zeus: Zeus's fuller set (zeus_augment)")
    ap.add_argument("--stop-at", type=int, help="stop after this pass, the learning rate still scheduled over --epochs "
                    "(to repeat a held-out run's best pass with nothing held out)")
    ap.add_argument("--color", action="store_true", help="read staves in colour (three channels), not grey")
    ap.add_argument("--height", type=int, default=128, help="the strip's height in px, a multiple of 16 (a new run; "
                    "with --init, the run it starts from sets it)")
    ap.add_argument("--replay", type=float, default=0, help="this share of each pass's staves drawn afresh from "
                    "--replay-from (stage 1's staves, so stage 2 keeps what it knew)")
    ap.add_argument("--replay-from", nargs="+", type=Path, default=[])
    ap.add_argument("--checkpoint", action="store_true", help="save the whole training state after every pass "
                    "(runs/NAME/state.pt), for --resume: for long runs")
    ap.add_argument("--resume", action="store_true", help="continue runs/NAME from its state.pt if it has one, else "
                    "start; the same command otherwise (implies --checkpoint)")
    ap.add_argument("--schedule", choices=["cosine", "wsd"], default="cosine",
                    help="cosine: warmup then cosine over --epochs; wsd: warmup, hold, then decay over the last --decay "
                    "share, so a resumed run that hasn't begun decaying can be given more --epochs")
    ap.add_argument("--decay", type=float, default=0.2, help="wsd: the share of passes the learning rate decays over")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    a = ap.parse_args()
    global AMP, AUGMENT, COLOR, H
    AUGMENT = a.augment
    COLOR = a.color
    assert a.height % PATCH == 0, "--height must be a multiple of 16"
    H = a.height
    assert 0 <= a.replay < 1 and (not a.replay or a.replay_from), "--replay is a share below 1, with --replay-from"
    readapt = False
    random.seed(0)
    torch.manual_seed(0)

    train = staves(a.train, a.limit)
    dev_items = train if a.overfit else staves(a.dev, a.dev_limit)
    pool = staves(a.replay_from) if a.replay else []  # replay staves count toward the vocabulary as training does
    if a.init:
        init_cfg = CACHE / "runs" / a.init / "config.json"
        if init_cfg.exists():
            c = json.loads(init_cfg.read_text())
            a.encoder, a.layers, a.decoder = c["encoder"], c["layers"], c.get("decoder", "transformer")
            a.memory = c.get("memory", "patches")
            a.height = H = c.get("height", 128)
            readapt = a.lora_r is not None or a.lora_mlp
            if not readapt:
                a.lora_r, a.lora_mlp = c.get("lora_r", 16), c.get("lora_mlp", False)
        vocab = json.loads((CACHE / "runs" / a.init / "vocab.json").read_text())
        missing = sorted({t for _, ts in train + pool for t in ts} - set(vocab))
        if missing:
            print(f"training tokens not in {a.init}'s vocabulary, read as {UNK}: {missing}", flush=True)
    else:
        tokens = {t for _, ts in train + pool + staves(a.vocab_extra) for t in ts}
        vocab = {t: i for i, t in enumerate([PAD, BOS, EOS, UNK] + sorted(tokens))}
    out = CACHE / "runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "vocab.json").write_text(json.dumps(vocab))
    if a.epochs:
        if a.lora_r is None:
            a.lora_r = 16
        (out / "config.json").write_text(json.dumps({"encoder": a.encoder, "layers": a.layers, "amp": a.amp,
                                                     "lora_r": a.lora_r, "lora_mlp": a.lora_mlp, "decoder": a.decoder,
                                                     "memory": a.memory, "color": a.color}
                                                    | ({"height": a.height} if a.height != 128 else {})
                                                    | ({"replay": a.replay, "replay_from": [str(f) for f in a.replay_from]}
                                                       if a.replay else {})))
    n_replay = round(len(train) * a.replay / (1 - a.replay)) if a.replay else 0
    if pool:
        print(f"replay: {n_replay} of {len(pool)} staves from --replay-from in each pass ({a.replay:.0%})", flush=True)
    unseen = sum(t not in vocab for _, ts in dev_items for t in ts)
    print(f"{len(train)} training staves, {len(dev_items)} dev, vocabulary {len(vocab)}, dev tokens unseen in training {unseen}", flush=True)

    model = load(a.init, a.init_file)[0] if a.init else Reader(a.encoder, len(vocab), layers=a.layers, decoder=a.decoder,
                                                              memory=a.memory,
                                                              lora_r=a.lora_r or 16, lora_mlp=a.lora_mlp)
    # load() set COLOR from the run it loaded: training reads as told, scoring alone as that run was trained
    COLOR = a.color or (a.epochs == 0 and COLOR)
    if readapt and a.epochs:
        model.readapt(a.lora_r, a.lora_mlp)
    # a run started from one that saved its whole encoder (readapted, or with unlocked layers) saves it too
    whole = readapt or bool(a.init and any(k.startswith("encoder.") and "lora" not in k for k in torch.load(
        CACHE / "runs" / a.init / a.init_file, map_location="cpu")))
    unfrozen = set(model.unfreeze_top(a.unfreeze_top)) if a.epochs else set()
    model = model.to(a.device)
    if a.epochs:  # training follows --amp; scoring alone follows the run's config (load)
        AMP = a.amp and a.device == "cuda"
    if a.epochs == 0:
        ser, exact, shown, ser_capped, runaway = score(model, dev_items, vocab, a.device)
        print(f"{a.init}/{a.init_file}: dev SER {ser:.3f}  exact {exact}/{len(dev_items)}  (runaways {runaway}; SER cut at 2x {ser_capped:.3f})", flush=True)
        return
    trainable = [p for p in model.parameters() if p.requires_grad]
    print(f"trainable parameters {sum(p.numel() for p in trainable) / 1e6:.1f}M of {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M on {a.device}", flush=True)
    named = dict(model.named_parameters())
    enc_own = [named[n] for n in unfrozen]
    rest = [p for n, p in named.items() if p.requires_grad and n not in unfrozen]
    opt = torch.optim.AdamW([{"params": rest, "lr": a.lr}] + ([{"params": enc_own, "lr": a.lr * a.encoder_lr}] if enc_own else []),
                            weight_decay=0.01)
    per_pass = math.ceil((len(train) + n_replay) / a.batch_size)
    steps = a.epochs * per_pass
    warm = max(1, min(200, steps // 10))
    decay_from = round(steps * (1 - a.decay))  # wsd: the step its decay begins

    def lr_share(s):
        if a.schedule == "cosine":
            return min(1, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps))
        tail = max(1, steps - decay_from)
        return min(1, (s + 1) / warm) * (1 if s < decay_from else 0.5 * (1 + math.cos(math.pi * min(s - decay_from, tail) / tail)))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_share)
    loss_fn = nn.CrossEntropyLoss(ignore_index=vocab[PAD])

    def weights():
        return {k: v for k, v in model.state_dict().items()
                if whole or "lora" in k or not k.startswith("encoder.") or k in unfrozen}

    # batches of similar width, so little of each is padding
    by_width = sorted(train, key=aspect)
    log, best, since_best, first = [], float("inf"), 0, 1
    # what must match for a resume: the data, the model's shape and the optimizer's settings
    same = {"train": [str(f) for f in a.train], "replay": a.replay, "batch_size": a.batch_size, "lr": a.lr,
            "init": a.init, "init_file": a.init_file, "schedule": a.schedule, "decay": a.decay, "per_pass": per_pass}
    checkpoint = out / "state.pt"
    if a.resume and checkpoint.exists():
        ck = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if ck["same"] != same:
            raise SystemExit(f"--resume: runs/{a.name} was started with other settings: "
                             f"{ {k: v for k, v in ck['same'].items() if same.get(k) != v} }")
        if ck["done"] and ck["epochs"] == a.epochs:
            print(f"--resume: runs/{a.name} already finished (pass {ck['ep']})", flush=True)
            return
        if ck["epochs"] != a.epochs and (a.schedule != "wsd" or ck["ep"] * per_pass > ck["decay_from"]):
            raise SystemExit(f"--resume: --epochs {ck['epochs']} → {a.epochs} only with --schedule wsd, "
                             f"before the decay began (pass {ck['decay_from'] // per_pass})")
        bad = model.load_state_dict(ck["weights"], strict=False).unexpected_keys
        assert not bad, f"--resume: weights the model doesn't have: {bad[:5]}"
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        log, best, since_best, first = ck["log"], ck["best"], ck["since_best"], ck["ep"] + 1
        random.setstate(ck["random"])
        torch.set_rng_state(ck["torch"])
        if ck.get("cuda") is not None and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(ck["cuda"])
        print(f"--resume: runs/{a.name} from pass {ck['ep']} of {ck['epochs']}"
              + (f", now {a.epochs}" if ck["epochs"] != a.epochs else ""), flush=True)

    def save_state(ep, done):
        """The whole training state, written then renamed, so a cut-off write leaves the last one."""
        if not (a.checkpoint or a.resume):
            return
        ck = {"same": same, "epochs": a.epochs, "decay_from": decay_from, "ep": ep, "done": done,
              "weights": weights(), "opt": opt.state_dict(), "sched": sched.state_dict(),
              "log": log, "best": best, "since_best": since_best, "random": random.getstate(),
              "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}
        torch.save(ck, out / "state.pt.tmp")
        os.replace(out / "state.pt.tmp", checkpoint)

    for ep in range(first, a.epochs + 1):
        if n_replay:  # a fresh draw each pass, mixed in by width with the rest
            by_width = sorted(train + random.sample(pool, n_replay), key=aspect)
        chunks = [by_width[k: k + a.batch_size] for k in range(0, len(by_width), a.batch_size)]
        random.shuffle(chunks)
        t0, total = time.time(), 0.0
        for chunk in chunks:
            x, mask, y_in, y_out = batch(chunk, vocab, augment=not a.overfit)
            x, mask, y_in, y_out = (t.to(a.device) for t in (x, mask, y_in, y_out))
            with autocast():
                logits = model.decode(model.encode(x), mask, y_in)
                loss = loss_fn(logits.reshape(-1, logits.shape[-1]).float(), y_out.reshape(-1))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            opt.step()
            sched.step()
            total += loss.item()
        secs = time.time() - t0
        last = ep == a.epochs or ep == a.stop_at
        if ep % a.eval_every and not last:
            print(f"epoch {ep:2}  loss {total / len(chunks):.3f}  {secs:5.0f} s", flush=True)
            save_state(ep, done=False)
            continue
        ser, exact, shown, ser_capped, runaway = score(model, dev_items, vocab, a.device)
        row = {"epoch": ep, "loss": total / len(chunks), "train_secs": secs, "dev_ser": ser, "dev_exact": exact,
               "dev_n": len(dev_items), "dev_ser_capped": ser_capped, "dev_runaway": runaway}
        log.append(row)
        print(f"epoch {ep:2}  loss {row['loss']:.3f}  {secs:5.0f} s  dev SER {ser:.3f}  exact {exact}/{len(dev_items)}"
              f"  (runaways {runaway}; SER cut at 2x {ser_capped:.3f})", flush=True)
        for name, want, got in shown:
            print(f"   {name}\n     want {want}\n     got  {got}", flush=True)
        (out / "log.json").write_text(json.dumps(log, indent=1))
        state = weights()
        torch.save(state, out / "reader.pt")
        stop = None
        if ser < best:
            best, since_best = ser, 0
            torch.save(state, out / "best.pt")
        else:
            since_best += 1
            if a.patience and since_best >= a.patience:
                stop = f"stopping: no better SER in {a.patience} scorings; best {best:.3f} kept in best.pt"
        if stop is None and ep == a.stop_at:
            stop = f"stopping at pass {ep} (--stop-at); reader.pt is this pass"
        # --stop-at leaves the run resumable; patience and the last pass finish it
        save_state(ep, done=ep == a.epochs or (stop is not None and ep != a.stop_at))
        if stop:
            print(stop, flush=True)
            break


if __name__ == "__main__":
    main()
