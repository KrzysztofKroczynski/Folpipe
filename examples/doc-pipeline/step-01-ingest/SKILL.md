---
name: step-01-ingest
description: Reads documents from the input folder and collects them into a list for processing.
---

# Ingest documents

Read the documents from the input folder and prepare them for processing.
The next step will work through each document one at a time.

## Context

The input folder contains the files to process. There may be PDFs,
Word documents, plain text files, or a mix. Start fresh — there's
nothing in state yet.

## Task

Look at what's in the input folder. For each file, read it and pull
out the text content. Note the filename, the type, and any metadata
you can find (title, author, date if present).

Collect all the documents into a list, ready to be handed off.
Save the list to state using write_state with key "documents" — each
entry should have: filename, type, and content.

If any file can't be read, note it and move on — don't let one
bad file block the rest.

Before finishing, leave a brief handoff note (write_state key "handoff")
explaining what was ingested and what the next step will receive.

## When things go wrong

If the input folder is empty, stop and leave a clear note explaining
that no input was found. Don't proceed to the next step.

If a file type is unreadable, note the filename and skip it.
If more than half the files are unreadable, stop and flag it
for human attention before continuing.

## Notes

Preserve the original filename — it's useful for attribution later.
Don't try to interpret or summarize the content yet. Just extract
the text cleanly and pass it on.

The input folder is at: input/
