---
name: sub-02-embed
description: Produces embedding records for a set of text chunks from one document.
---

# Embed chunks

Produce embeddings for a set of text chunks from one document.

## Task

You receive via context: `filename` (string) and `chunks` (list of strings).

For each chunk, produce a structured record:
- `filename`: source filename
- `chunk_index`: 1-based index
- `text`: the chunk text
- `embedding`: placeholder float list (if no embedding API is available, use an empty list
  and note "no embedding service configured" in your result)

Write all records as a JSON array to `output/step-02-process/<filename>-embeddings.json`.

Return a summary: filename, how many chunks were embedded, whether an embedding service was used.

## When things go wrong

If no embedding tool is available, produce the structured records with empty embeddings.
The downstream index step can still use the text for full-text search.
