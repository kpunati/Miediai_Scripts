# Enrichment Examples

This folder will hold 1–2 worked input/output pairs that demonstrate the enrichment skill applied to a real transcript. These examples ground the instructions for both humans and LLMs.

## To populate

After the first hand-built transcript is produced (see [PROJECT_CONTEXT.md](../../../PROJECT_CONTEXT.md) → "Order of operations" → step 2):

1. Copy the raw `.md` file into this folder as `example_01_input.md`.
2. Run the `enrich` skill manually on a copy.
3. Save the enriched version as `example_01_output.md`.
4. Add a short note here explaining what about this example is instructive (e.g. "shows handling of a Whisper-transcribed file with several tickers").

Aim for 1–2 examples that cover the common cases:
- A clean manual-captions file with a clear single topic
- A Whisper-transcribed file with finance jargon (tests the flagging behavior)

More than 2 examples is overkill — the schema is the contract; examples are just illustration.
