"""mark_unenriched.py — flip selected files to enriched=false for re-enrichment.

STUB. See operations/re-enrich/INSTRUCTIONS.md for the canonical spec
(selector semantics, what to preserve).

Planned CLI:
  python scripts/mark_unenriched.py --all
  python scripts/mark_unenriched.py --channel <slug>
  python scripts/mark_unenriched.py --video <video_id>
  python scripts/mark_unenriched.py --enrichment-version 1
"""
from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError(
        "mark_unenriched.py is a stub. See operations/re-enrich/INSTRUCTIONS.md."
    )


if __name__ == "__main__":
    sys.exit(main())
