---
name: step-05-partial-output
description: Produces output for documents that succeeded when some failed processing.
---

# Write partial output

Some documents failed to process. Produce output for what succeeded.

## Context

The "processed" list is essential — some entries may have failed.
The "failed" list is essential.
The "validation" status is important.

## Task

Write output/partial-index.md documenting:
- What succeeded (documents and chunk counts)
- What failed and why (from the failed list and handoff notes)
- Recommendation for next steps (re-run with --from step-02-process, or investigate failures)

Also write output/partial-index.json with the structured data.

Leave a handoff note summarising what was saved and what was lost.

## Notes

This is the terminal step for partial runs.
Be clear about what is and isn't in the output so the next human knows what to do.
