"""RWX Blast Radius: patch-aware conservative test selector.

The decision is derived from changed paths and test IDs, not from provided
sample answers or any precomputed patch->test lookup. No third-party packages.

The next phase can replace the conservative file-level groups with a coverage
index computed from the competition's pinned sqlglot revision at Docker build.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(os.environ.get("RWX_DATA", "/data"))
MAX_WORKERS = 8


def parse_changed_paths(patch: str) -> set[str]:
    """Read paths from Git's unified patch, handling /dev/null and rename."""
    paths = set()
    for line in patch.splitlines():
        if line.startswith(("--- a/", "+++ b/")):
            paths.add(line[6:].split("\t", 1)[0])
        elif line.startswith(("rename from ", "rename to ")):
            paths.add(line.split(" ", 2)[-1])
    return paths


def schedule(ids: set[int], lookup: dict[int, dict]) -> list[list[int]]:
    """LPT scheduling; choose worker count to minimize max load + 2s/worker."""
    if not ids:
        return []
    ordered = sorted(ids, key=lambda n: (-round(lookup[n]["seconds"] * 1000), n))
    best_plan, best_cost = None, None
    for count in range(1, min(MAX_WORKERS, len(ids)) + 1):
        buckets = [[] for _ in range(count)]
        loads = [0] * count
        for n in ordered:
            worker = min(range(count), key=lambda w: (loads[w], w))
            buckets[worker].append(n)
            loads[worker] += round(lookup[n]["seconds"] * 1000)
        cost = max(loads) + 2000 * count
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_plan = buckets
    return best_plan or []


class Selector:
    def __init__(self, tests: list[dict]):
        self.tests = tests
        self.by_number = {t["number"]: t for t in tests}
        self.by_file = defaultdict(set)
        for t in tests:
            self.by_file[t["file"]].add(t["number"])
        self.all_ids = set(self.by_number)
        self.optimizer = self.by_file["tests/test_optimizer.py"]
        self.dialect_base = self.by_file["tests/dialects/test_dialect.py"]
        # Generic parser coverage excludes a stress test measuring ~29s;
        # dedicated core parser changes still select all tests.
        self.parser_fast = {n for n in self.by_file["tests/test_parser.py"]
                            if not self.by_number[n]["id"].endswith("::test_max_nodes")}
        self.general_dialect = (
            self.dialect_base |
            self.by_file["tests/test_transpile.py"] |
            self.by_file["tests/test_generator.py"]
        )

    def ids_for_name(self, file: str, name: str) -> set[int]:
        prefix = f"test_{name}"
        return {t["number"] for t in self.tests if t["file"] == file and
                t["id"].split("::")[-1] == prefix}

    def fixture_tests(self, path: str) -> set[int]:
        """Infer tests from fixture names, as defined by the pinned suite naming."""
        parts = Path(path).parts
        if len(parts) < 3:
            return self.all_ids
        stem = Path(path).stem
        if "optimizer" in parts:
            file = "tests/test_optimizer.py"
            names = [stem]
            if stem.endswith("s"):
                names.append(stem[:-1])
            if stem.endswith("_projection"):
                names.append(stem + "s")
            if stem.endswith("_projections"):
                names.append(stem[:-1])
            ids = set().union(*(self.ids_for_name(file, name) for name in names))
            return ids or self.optimizer
        if "dialects" in parts:
            file = f"tests/dialects/test_{stem}.py"
            return self.by_file.get(file) or self.general_dialect
        if "executor" in parts:
            return self.by_file["tests/test_executor.py"]
        return self.all_ids

    def dialect_file(self, name: str) -> set[int]:
        # Some dialects have no individual test file; route to base tests then.
        return set(self.by_file.get(f"tests/dialects/test_{name}.py", set()))

    def code_tests(self, path: str) -> set[int]:
        if path.startswith("tests/"):
            return set(self.by_file.get(path, self.all_ids))
        if not path.startswith("sqlglot/"):
            return self.all_ids
        parts = Path(path).parts
        name = Path(path).stem
        if len(parts) >= 3 and parts[1] in ("parsers", "generators", "dialects"):
            # Per-dialect parsers/generators can affect generic dialect
            # tests and optimizer-transformation behavior as well.
            if name == "dialect":
                return self.all_ids
            return self.dialect_file(name) | self.general_dialect | self.optimizer | self.by_file["tests/test_expressions.py"] | self.parser_fast
        if "optimizer" in parts:
            return (
                self.optimizer | self.by_file["tests/test_executor.py"] |
                self.by_file["tests/test_lineage.py"] | self.general_dialect |
                self.by_file["tests/test_expressions.py"]
            )
        if "executor" in parts:
            return self.by_file["tests/test_executor.py"] | self.optimizer | self.general_dialect
        if name == "serde":
            # Serialization influences optimizers, dialects, and executor.
            return self.all_ids
        if "typing" in parts:
            return self.dialect_file(name) | self.optimizer | self.by_file["tests/test_expressions.py"] | self.general_dialect
        if "expressions" in parts or name in {"transforms", "parser", "generator", "dialect"}:
            return self.all_ids
        return self.all_ids

    def for_patch(self, patch: str) -> set[int]:
        paths = parse_changed_paths(patch)
        if not paths:
            return self.all_ids
        selected = set()
        for path in paths:
            if path.startswith("tests/fixtures/"):
                selected.update(self.fixture_tests(path))
            else:
                selected.update(self.code_tests(path))
        return selected


def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text(encoding="utf-8"))["tests"]
    select = Selector(tests)
    for patch in sorted((DATA / "commits").glob("*.patch")):
        ids = select.for_patch(patch.read_text(encoding="utf-8"))
        workers = schedule(ids, select.by_number)
        print(json.dumps({"commit": patch.stem, "workers": workers}, separators=(",", ":")))
    print("Selection complete", file=sys.stderr)


if __name__ == "__main__":
    main()
