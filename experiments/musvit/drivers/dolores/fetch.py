import sys
from remotezip import RemoteZip
url = "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/fdf9ba56-1854-45fc-a8d2-311dfb3ad8c3/content"
names = sys.argv[2:]
with RemoteZip(url) as z:
    for n in names:
        z.extract(n, sys.argv[1])
        print("got", n, flush=True)
