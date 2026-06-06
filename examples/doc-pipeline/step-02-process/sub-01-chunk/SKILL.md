---
name: sub-01-chunk
description: Splits a single document into ~500-word chunks and writes them to output files.
---

# Chunk document

Split a single document into manageable pieces ready for embedding.

## Task

You receive a document via context: `filename` (string) and `content` (string).

Split the content into chunks of around 500 words each. Keep paragraphs together —
never split mid-paragraph. If a heading introduces a paragraph, keep them together.

Write each chunk to `output/step-02-process/<filename>-chunk-<n>.txt` using write_file,
where `<n>` starts at 1.

If the document is under 200 words, treat it as a single chunk.

Return a summary: how many chunks were created and the filename.

## When things go wrong

If write_file fails for a chunk, skip that chunk and note it in your result.
Don't stop — partial output is better than nothing.
