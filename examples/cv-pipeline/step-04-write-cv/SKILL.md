---
name: step-04-write-cv
description: Writes the tailored CV (cv.md) and cover note (cover-note.md) using the tailoring plan.
---

# Write CV

Write the final CV using the tailoring plan from step-03.
This is the deliverable — make it polished and ready to send.

## Context

The profile (contact info) is essential.
The cv_summary, cv_experience, cv_skills, cv_projects, cv_education are essential.
The cv_gaps and job_title are important — use them to write the cover note.
You don't need the raw job_description or the untailored experience.

## Task

Write two files:

**1. output/cv.md** — the tailored CV in clean Markdown:

```
# [Full Name]
[Email] | [Phone] | [Location] | [LinkedIn/GitHub if present]

## Summary
[cv_summary]

## Experience
[Each role from cv_experience, formatted consistently:
**Job Title** — Company Name | Date range
- Achievement bullet
- Achievement bullet]

## Skills
[cv_skills, organised in categories]

## Projects
[cv_projects — each with name, one-line description, tech used]

## Education
[cv_education]
```

**2. output/cover-note.md** — a short cover note (3 paragraphs):
- Para 1: why this role, what draws them to this company/problem
- Para 2: the two or three strongest reasons they're a good fit
- Para 3: brief honest acknowledgement of the biggest gap from cv_gaps
  and why it's not a blocker (or how they'd address it)

Then write_state key "handoff" confirming both files are written.

## When things go wrong

If cv_experience is empty or very thin, write what's there and note
in the cover note that the developer is earlier in their career.

## Notes

Tone: professional but direct. Not corporate filler.
No "results-driven professional" or "passionate about technology."
Say what they did and why it matters for this role.

The cover note is short on purpose — hiring managers skim them.
Three tight paragraphs beat a page of enthusiasm.
