---
name: sub-03-index
description: Appends embedded chunk records for one document to the pipeline's search index.
---

# Index embedded chunks

Add embedded chunks for one document to the pipeline's search index.

## Task

You receive via context: `filename` (string) and `embeddings_path` (string, path to the
embeddings JSON written by sub-02-embed).

Read the embeddings file. For each record, append an entry to
`output/step-02-process/index.jsonl` (one JSON object per line, append mode):

```json
{"filename": "...", "chunk_index": 1, "text": "...", "has_embedding": true}
```

Set `has_embedding` to false if the embedding list is empty.

Return a summary: filename, how many records were indexed.

## When things go wrong

If the embeddings file doesn't exist, note it and return an error result — don't write
partial index entries for a document with no data.
