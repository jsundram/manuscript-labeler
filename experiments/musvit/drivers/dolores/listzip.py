import sys, collections
from remotezip import RemoteZip
url = "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/fdf9ba56-1854-45fc-a8d2-311dfb3ad8c3/content"
with RemoteZip(url) as z:
    infos = z.infolist()
    print(len(infos), "entries")
    ext = collections.Counter((i.filename.rsplit(".", 1)[-1] if "." in i.filename.split("/")[-1] else "<dir>") for i in infos)
    print(ext.most_common(20))
    size = collections.defaultdict(int)
    for i in infos: size["/".join(i.filename.split("/")[:2])] += i.file_size
    print(dict(size))
    for i in infos[:40]: print(i.filename, i.file_size)
    open(sys.argv[1], "w").write("\n".join(f"{i.filename}\t{i.file_size}\t{i.compress_size}" for i in infos))
