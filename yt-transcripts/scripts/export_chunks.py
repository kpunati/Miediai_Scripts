"""export_chunks.py — chunk the corpus into JSONL ready for vector embedding.

STUB. See operations/export-for-embedding/INSTRUCTIONS.md for the canonical spec
(chunk strategy, JSONL row format, what to include/exclude).

This script makes ZERO LLM or embedding-provider calls. It only produces
input for a future Layer 3 pipeline.

Planned CLI:
  python scripts/export_chunks.py --dry-run               # stats only, no file written
  python scripts/export_chunks.py                          # writes output/chunks.jsonl
  python scripts/export_chunks.py --output path/to.jsonl
  python scripts/export_chunks.py --include-unenriched     # also chunk files with enriched=false
"""
from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError(
        "export_chunks.py is a stub. See operations/export-for-embedding/INSTRUCTIONS.md."
    )


if __name__ == "__main__":
    sys.exit(main())
