---
name: step-03-validate
description: Checks that all processed chunk files exist and have content, then routes to output or partial-output.
---

# Validate output

Check that the processed chunks are present and sensible before producing final output.

## Context

The "processed" list from step-02 is essential — it tells you what was processed and how many chunks each document produced.
The "failed" list is important — check if it exists and what's in it.

## Task

For each document in the "processed" list:
1. Read a sample chunk file from output/step-02-process/ to confirm it exists and has content.
2. Check that the chunk count is reasonable (not zero).

Write a validation report to output/step-03-validate/report.md summarising:
- Total documents processed
- Total chunks written
- Any documents with zero chunks or missing files
- Overall pass/fail verdict

If validation passes (all processed documents have chunks):
- write_state key "validation": "passed"
- write_state key "handoff" with a brief summary
- Move to step-04-output

If validation fails (missing chunks or files):
- write_state key "validation": "failed"
- write_state key "handoff" with what went wrong
- Move to step-05-partial-output

## When things go wrong

If you can't read any chunk files at all, validation fails — move to step-05-partial-output.
