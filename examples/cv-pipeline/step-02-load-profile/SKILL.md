---
name: step-02-load-profile
description: Reads all developer profile source files and saves a complete structured profile to state.
---

# Load developer profile

Read all the developer's source files and build a complete picture
of their background ready for tailoring.

## Context

The job requirements from step-01 are important — use them to know
what to look for when reading the profile files.
The tech_stack list is important.

## Task

Read each file in the input/ folder:
- profile.md — contact info, summary, identity
- experience.md — work history
- skills.md — technical skills and proficiency levels
- projects.md — notable projects and contributions
- education.md — degrees, certifications, courses

For each file, use read_file. Don't skip any — all may contain
relevant information.

Then write to state:
- write_state key "profile": full contact info and summary
- write_state key "experience": list of roles — each with company,
  title, dates, and bullet-point achievements
- write_state key "skills": full skills inventory
- write_state key "projects": list of projects with description and tech used
- write_state key "education": degrees and certifications
- write_state key "handoff": one sentence — how well does this developer
  match the job at first glance?

## When things go wrong

If a file doesn't exist, skip it and note the gap in the handoff.
Don't fail — work with what's there.

## Notes

Read everything faithfully. Don't summarise or editorialize yet —
that's the next step's job. Preserve specific details: company names,
dates, numbers, technology names. These details matter for the CV.
