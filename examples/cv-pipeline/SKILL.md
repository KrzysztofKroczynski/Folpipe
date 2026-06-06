---
name: cv-pipeline
description: Creates a tailored CV and cover note for a specific job posting from a developer's profile files.
---

# CV pipeline

This pipeline creates a tailored CV for a specific job posting.
It fetches the job description from a URL, reads the developer's
profile from source files, and writes a CV that highlights what's
most relevant for that role.

The output is a polished, ready-to-use CV in Markdown. Be precise
and honest — don't invent experience that isn't in the source files.
Omit or de-emphasise experience that isn't relevant to the role.
