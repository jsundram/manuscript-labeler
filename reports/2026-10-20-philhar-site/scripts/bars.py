import re,sys,pathlib
from fractions import Fraction as F
def dur(tok):
    m=re.fullmatch(r"s(\d+)(\.*)(?:\*(\d+)(?:/(\d+))?)?",tok)
    if not m: return None
    d=F(1,int(m.group(1))); dots=len(m.group(2)); t=d
    for i in range(dots): d/=2; t+=d
    n=int(m.group(3) or 1); k=int(m.group(4) or 1)
    return t*n/k
for f in sorted(pathlib.Path(sys.argv[1]).glob("*.ily")):
    txt=re.sub(r"%.*","",f.read_text(errors="replace"))
    parts=re.split(r"\\tag\s*#'mvt",txt)[1:]
    tot=0; per=[]
    for p in parts:
        ts=re.search(r"\\time\s+(\d+)/(\d+)",p)
        meas=F(int(ts.group(1)),int(ts.group(2))) if ts else F(1)
        total=sum((dur(t) or 0) for t in re.findall(r"s\d+\.*(?:\*\d+(?:/\d+)?)?",p))
        b=round(total/meas); per.append(b); tot+=b
    print(f"{f.stem[:60]:60} mvts={len(parts)} bars={tot} {per}")
