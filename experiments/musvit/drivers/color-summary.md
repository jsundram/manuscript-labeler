dataL: 726 staves in colour from 78 pages -> /Users/jsundram/.cache/manuscript-labeler/zeus/dataL-color
dataM: 2444 staves in colour from 500 pages -> /Users/jsundram/.cache/manuscript-labeler/zeus/dataM-color
dataT: 372 staves in colour from 68 pages -> /Users/jsundram/.cache/manuscript-labeler/zeus/dataT-color
uv run experiments/musvit/color_staves.py ~/Dropbox/Code/boccherini-opus-48    7560.05s user 73.05s system 664% cpu 19:08.21 total
tail -5  0.00s user 0.00s system 0% cpu 19:08.21 total

[exited with code 0]
D1c-tf8-M-color: 2892 training staves; practice exam by pass: 3 0.221, 6 0.230, 9 0.197, 12 0.191, 15 0.208, 18 0.207, 21 0.213; best 0.191 at pass 12 (D1 grey: 0.189 at pass 24)
D1c-tf8-M-color clean test (colour): bars exact 260/347 (75%), right in rhythm 291/347 (84%), right in pitch 288/347 (83%) (D1 grey: 263/347 on Modal)
