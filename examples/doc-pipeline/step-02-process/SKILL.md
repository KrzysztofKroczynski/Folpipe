---
name: step-02-process
description: Chunks, embeds, and indexes each document using parallel sub-step dispatch.
---

# Process documents

Break each document into chunks, embed them, and index the results.
The previous step collected the documents; the next step will validate the results.

## Context

The "documents" list from step-01 is essential — read it in full.
Each entry has: filename, type, content.

You don't need anything else from state.

## Task

Work through each document in the list. For each document, run the three sub-steps
in sequence using dispatch_task with the `substep` parameter:

1. `substep: "sub-01-chunk"` — splits the document into ~500-word chunks and writes
   them to output files. Pass `filename` and `content` in context.

2. `substep: "sub-02-embed"` — produces embedding records for the chunks. Pass
   `filename` and `chunks` (the text of each chunk) in context.

3. `substep: "sub-03-index"` — adds the embedded records to the search index. Pass
   `filename` and `embeddings_path` in context.

You can process multiple documents in parallel — dispatch all the sub-01-chunk calls
at once, collect the results, then dispatch all sub-02-embed calls, and so on.

When all documents are processed, save to state:
- write_state key "processed": list of {filename, chunks, status}
- write_state key "failed": list of filenames that failed
- write_state key "handoff": summary of what was done

Move to step-03-validate when done.
Move to step-05-partial-output if more than a third of documents failed.

## When things go wrong

If a sub-step returns an error for a document, mark that document as failed and
continue with the others. Don't let one bad document block the rest.

If more than a third of documents fail: move to step-05-partial-output.

## Notes

Keep paragraphs with any heading that introduces them — pass this guidance in the
context you send to sub-01-chunk.

If a document's content is very short (under 200 words), one chunk is fine.
