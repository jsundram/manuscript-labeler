# manuscript-labeler

Label scanned music manuscripts page by page: staves, bar lines, bar numbers,
and confusing marks. Output is a JSON description of each source, for a
synoptic edition and for proofreading an engraving against its sources.

Early stage: see [SPEC.md](SPEC.md) for the plan, what's known, and the open
questions.

- `detect.py`: automatic staff and bar-line proposals (numpy + Pillow).
- `prototypes/`: scratch reading aids from the first hand transcription.

Try the detector on one page:

```bash
pdftoppm -f 2 -l 2 -r 200 -png -singlefile some.pdf /tmp/p2
uv run --with pillow --with numpy python -c "
from PIL import Image; from detect import detect_page
for s in detect_page(Image.open('/tmp/p2.png')): print(round(s['top'],3), len(s['barlines']))"
```

## License

MIT. See [LICENSE](LICENSE).
