#!/usr/bin/env bash
# Rebuild index/ from the pinned sqlglot commit (offline, NOT run in the judge image).
#   tools/trace_suite.sh /path/to/workdir
# Needs: git, uv (or python3.13 + pip), network for the one-time clone/install.
set -euo pipefail
WORK=${1:-$PWD/.indexbuild}
HERE=$(cd "$(dirname "$0")/.." && pwd)
SHA=eb11aec4be8cb2122afe713a4816662c3f0fb2fa
mkdir -p "$WORK"; cd "$WORK"
[ -d sqlglot ] || git clone -q https://github.com/tobymao/sqlglot sqlglot
git -C sqlglot checkout -q $SHA
[ -d venv ] || { uv venv -q -p 3.13 venv; . venv/bin/activate; uv pip install -q -r "$HERE/requirements.lock" coverage; }
. venv/bin/activate
cd sqlglot
# warm the bytecode cache so imports do not open .py sources (they would be
# traced as data-file reads); matches a checkout that has been imported once
python -m compileall -q sqlglot tests > /dev/null
export PYTHONPATH="$HERE/tools" SKIP_INTEGRATION=0
A="tests/test_optimizer.py tests/test_parser.py tests/dialects"
B=$(ls tests/test_*.py | grep -v -e test_optimizer.py -e test_parser.py | tr '\n' ' ')
rm -f ../cA ../cB
RWX_TRACE_OUT=../tA.json coverage run --rcfile="$HERE/tools/covrc" --data-file=../cA -m pytest -q -p no:cacheprovider -p rwx_trace $A > ../logA 2>&1 &
RWX_TRACE_OUT=../tB.json coverage run --rcfile="$HERE/tools/covrc" --data-file=../cB -m pytest -q -p no:cacheprovider -p rwx_trace $B > ../logB 2>&1 &
wait
tail -n 1 ../logA ../logB
cd ..
python "$HERE/tools/build_index.py" sqlglot "$HERE/sample/tests.json" "$HERE/index" cA cB -- tA.json tB.json
