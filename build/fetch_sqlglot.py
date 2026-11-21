"""Docker build step: fetch the pinned sqlglot tree (with test fixtures) into DEST
and verify every packaged source file in index/source.json.gz matches it."""
import gzip, io, json, os, sys, tarfile, urllib.request

SHA = "eb11aec4be8cb2122afe713a4816662c3f0fb2fa"
dest, source_json = sys.argv[1], sys.argv[2]
url = f"https://codeload.github.com/tobymao/sqlglot/tar.gz/{SHA}"
data = None
for attempt in range(4):
    try:
        data = urllib.request.urlopen(url, timeout=120).read()
        break
    except Exception as e:  # retry transient network errors
        print("fetch failed:", e, file=sys.stderr)
if data is None:
    sys.exit("could not fetch pinned sqlglot")
os.makedirs(dest, exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
    for m in tf.getmembers():
        parts = m.name.split("/", 1)
        if len(parts) < 2 or not parts[1]:
            continue
        rel = parts[1]
        if rel.startswith("/") or ".." in rel.split("/"):
            continue
        if not (m.isfile() or m.isdir()):
            continue
        m.name = rel
        tf.extract(m, dest, filter="data")
src = json.load(gzip.open(source_json, "rt", encoding="utf-8"))
bad = [rel for rel, text in src.items()
       if open(os.path.join(dest, rel), encoding="utf-8", newline="").read() != text]
if bad:
    sys.exit(f"pinned tree mismatch: {bad[:5]}")
print(f"sqlglot {SHA[:12]} ok, {len(src)} files verified", file=sys.stderr)
