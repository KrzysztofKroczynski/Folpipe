---
name: step-04-output
description: Writes the final index of all processed chunks as both Markdown and JSON.
---

# Write final output

Produce the final pipeline output — a clean index of all processed chunks.

## Context

The "processed" list is essential.
The "validation" status from step-03 is important.
The handoff note tells you what succeeded.

## Task

Write a final index file to output/index.md containing:
- Pipeline run summary (how many documents, how many chunks)
- A table listing each document: filename, chunk count, status
- The path to each document's chunk files

Also write output/index.json with the same data as structured JSON.

Leave a handoff note confirming completion.

## Notes

This is the terminal step — write clean, human-readable output.
