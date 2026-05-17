"""list_whisper.py — rank Whisper-transcribed files for human spot-check.

STUB. See operations/review-whisper/INSTRUCTIONS.md for the canonical spec
(selection logic, sort order).

Planned CLI:
  python scripts/list_whisper.py                       # top 10 by view count
  python scripts/list_whisper.py --limit 25
  python scripts/list_whisper.py --channel <slug>
  python scripts/list_whisper.py --all                 # every matching file
"""
from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError(
        "list_whisper.py is a stub. See operations/review-whisper/INSTRUCTIONS.md."
    )


if __name__ == "__main__":
    sys.exit(main())
