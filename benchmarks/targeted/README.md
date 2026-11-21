Targeted holdout for v4's narrowing rules: 77 patches, each labelled by running the
complete pinned suite serially (`tools/ground_truth.py`, `GT_WORKERS=1`, Python 3.13,
`requirements.lock`). Generated from the pinned source only by
`tools/target_mutants.py` (seeds 21–24), plus two hand-made template edits (`t25_*`).
Only patches where v4 and v3 select differently were kept, so this set measures the
new rules, not the selector as a whole. `what.json` says what each patch changes.

| kind | n | what |
|---|---:|---|
| `dictval` | 17 | one literal inside a value of a dict-literal class attribute (keys unchanged) |
| `delattr` | 24 | a one-line call-free class attribute removed |
| `insattr` | 12 | a base-class bool flag overridden in a subclass that did not set it |
| `docstr`  | 10 | a word added to a module/class/function docstring |
| `defarg`  | 12 | a bool parameter default flipped |
| `tmpl`    | 2  | the SQL text DuckDBGenerator parses at import: made unparseable / changed |

Result (v4 `selector.py` vs v3 `3999bb3`), same scorer as `tools/eval_holdout.py`:

| | total | misses |
|---|---:|---:|
| best possible | 196.5 s | – |
| v4 | 496.3 s | 0 |
| v3 | 2,062.2 s | 2 (`t24_defarg_001`, `t25_tmpl_000`) |

Both v3 misses are import-time failures that break collection of every
`tests/dialects` file; v4 adds every test of each file whose collection imports the
broken module (static import graph of the pinned source).

Evaluate:

```bash
mkdir -p /tmp/tg && cp sample/tests.json /tmp/tg && cp -r benchmarks/targeted/commits /tmp/tg/
RWX_DATA=/tmp/tg python selector.py > tg.jsonl && python tools/eval_holdout.py /tmp/tg tg.jsonl benchmarks/targeted/labels.json
```

Never packaged in the image (`benchmarks` is in `.dockerignore`).
