---
name: step-01-fetch-job
description: Fetches the job posting URL and extracts structured requirements, responsibilities, and tech stack.
---

# Fetch job posting

Retrieve the job posting from the URL provided as input and extract
the structured information needed for CV tailoring.

## Context

The job URL is in the input provided at pipeline start. Nothing in
state yet — this is the first step.

## Task

1. Fetch the page using the fetch_page tool.
2. Extract and save the following to state:

   - write_state key "job_url": the URL
   - write_state key "job_title": the role title
   - write_state key "company": company name
   - write_state key "job_description": the full cleaned text of the posting
   - write_state key "requirements": a structured list of requirements —
     split into "must_have" (explicit requirements) and "nice_to_have"
     (preferred/bonus). Each entry is a short phrase.
   - write_state key "responsibilities": list of key responsibilities
   - write_state key "tech_stack": list of specific technologies, languages,
     frameworks, tools mentioned
   - write_state key "handoff": one sentence summarising the role

## When things go wrong

If the page fails to load (network error or status >= 400): write what
you know to state and set job_description to the raw error. Don't stop
— the next step can work with partial info.

If the page loads but looks like a login wall or redirect rather than
a real job posting: note this in job_description and extract whatever
text is available.

## Notes

Be thorough when extracting requirements — these drive the whole
tailoring decision in later steps. If a requirement appears multiple
times or is emphasised, note it as a priority.
