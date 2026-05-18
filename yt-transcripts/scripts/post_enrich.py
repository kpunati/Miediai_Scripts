"""post_enrich.py — run after every enrichment batch.

Wraps the three things that must happen after enrichment so they can't be
forgotten:
  1. validate_corpus  — schema/timestamp/length checks (must PASS to proceed)
  2. build_index      — refresh output/index.csv from frontmatter
  3. corpus_status    — print the current dashboard

Exit codes:
  0  all three steps OK
  1  validate failed (index not rebuilt; fix errors and re-run)
  2  build_index failed
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(label: str, args: list[str]) -> int:
    print(f"\n=== {label} ===")
    sys.stdout.flush()
    return subprocess.call([PY, *args], cwd=REPO_ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run validate → build_index → status after an enrichment batch.")
    ap.add_argument("--channel", help="restrict validate to one channel")
    ap.add_argument("--skip-status", action="store_true", help="skip the status dashboard at the end")
    args = ap.parse_args()

    validate_args = ["scripts/validate_corpus.py"]
    if args.channel:
        validate_args += ["--channel", args.channel]
    rc = run("validate_corpus", validate_args)
    if rc != 0:
        print("\nvalidate_corpus FAILED — fix errors before rebuilding the index.")
        return 1

    rc = run("build_index", ["scripts/build_index.py"])
    if rc != 0:
        print("\nbuild_index FAILED.")
        return 2

    if not args.skip_status:
        run("corpus_status", ["scripts/corpus_status.py"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
