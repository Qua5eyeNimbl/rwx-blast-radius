# The scorer builds this on linux/amd64 and runs it with no network. The
# digest is the image we labeled every commit in: its Python and SQLite
# decide which sqlglot tests run, so keep it if your image runs them.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
# Test dependencies at the organizer's pinned versions: the selector runs
# candidate tests on the patched tree while it decides (allowed and charged).
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -q -r /app/requirements.lock
# index/ is derived only from the pinned sqlglot commit (see tools/ and INDEX.md)
COPY index/ /app/index/
# The pinned sqlglot tree with its test fixtures, verified file by file
# against index/source.json.gz, precompiled for fast imports.
COPY build/fetch_sqlglot.py /app/build/fetch_sqlglot.py
RUN python /app/build/fetch_sqlglot.py /app/sq /app/index/source.json.gz \
 && python -m compileall -q /app/sq/sqlglot /app/sq/tests
COPY selector.py runner.py replay.py /app/
# Precompile so the read-only runtime never tries to write bytecode
RUN python -m compileall -q /app/selector.py /app/runner.py /app/replay.py
# A fixed hash seed makes replayed optimizer plans reproducible (one TPC-DS
# plan depends on set iteration order); the pinned replay digests are made
# here, from the pinned tree, under the same seed.
ENV PYTHONHASHSEED=0
RUN SKIP_INTEGRATION=0 python /app/replay.py /app/sq /app/replay_expected.json
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/app/selector.py"]
