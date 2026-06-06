---
name: doc-pipeline
description: Ingests documents, chunks and embeds them, and produces a searchable index.
---

# Document processing pipeline

This pipeline ingests a set of documents, breaks them into searchable
chunks, embeds them, and produces an indexed output ready for search.

All output should be precise and well-structured. When in doubt about
a document's content, note the uncertainty rather than guessing.

The `send_slack` tool is available for notifying the team when something
needs attention — use it for failures that need human eyes, not for
routine progress updates.
