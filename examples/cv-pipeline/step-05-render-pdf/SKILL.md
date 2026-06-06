---
name: step-05-render-pdf
description: Designs a polished two-column HTML CV and renders it to PDF via headless browser.
---

# Design and render CV as PDF

Design a polished, visually distinctive CV as a self-contained HTML
document, then render it to PDF using the render_pdf tool.
The renderer is a real browser (Edge/Chrome headless) — full modern
CSS works: flexbox, grid, gradients, Google Fonts, CSS variables.

## Context

Read the finished CV from output/cv.md — that is the content source.
The profile state has the developer's name and contact info.

## Task

### 1. Read the content
Use read_file to read output/cv.md.

### 2. Design the HTML document

Write a complete, self-contained HTML file. Make real design decisions —
this should look like a professional designed it, not a browser default.

**Layout — two-column:**
- Left sidebar (~28% width): name block at top, then contact, then skills
  by category, then education. Sidebar has a solid dark background
  (e.g. #1a1a2e or #2d3436 or deep teal) with light text.
- Right main area (~72% width): summary paragraph, then experience,
  then projects. White or very light grey background.
- Use CSS flexbox or grid for the two-column split.

**Typography:**
- Import two Google Fonts via @import at the top of the <style> block:
  one for headings (e.g. Raleway, Montserrat, or Playfair Display),
  one for body (e.g. Inter, Source Sans Pro, or Lato).
- Name: large (2.2–2.8rem), font-weight 700, in the sidebar top block.
- Section headings: 0.7rem uppercase letter-spaced label style in the
  sidebar; 1rem bold with a coloured left border (4px) in the main area.
- Body text: 0.85rem, line-height 1.6.

**Accent colour:**
- Pick one accent colour that ties the design together. Use it for:
  the sidebar background (darkened), section heading borders in the
  main area, skill pill backgrounds (lighter tint), link colour.
- Good choices: #0f4c75 (navy), #1b4332 (forest), #3d405b (slate),
  #6b2737 (wine), #2d6a4f (emerald). Choose one, commit to it.

**Skills:**
- Display as pill/tag elements: small rounded rectangles with the
  accent colour as background (at ~15% opacity) and the accent as text.
- Group by category with a small uppercase label above each group.

**Experience entries:**
- Role title bold, company name + date range on the same line
  separated by a dot or dash, in a lighter colour.
- Achievement bullets with a custom bullet: a small coloured square
  or the accent colour circle instead of the default disc.

**Projects:**
- Name bold, one-line description, tech stack as small mono-font tags.

**Contact info in sidebar:**
- Each item as an icon-like prefix symbol (▸ or → or a unicode icon)
  followed by the value. Keep it compact.

**Page setup:**
- @page { size: A4; margin: 0; } — let the HTML control all spacing.
- The outermost div is 210mm × 297mm (or min-height: 297mm) so it
  maps cleanly to A4.
- Use cm/mm units for margins inside the layout.

### 3. Call render_pdf
Pass the complete HTML as the `html` argument and `output_path` as
`"output/cv.pdf"`. Also save the same HTML to `output/cv.html` using
write_file so the user can open it in a browser.

### 4. Save handoff
write_state key "handoff": confirm both files are written, note the
renderer used, note the colour scheme chosen.

## When things go wrong

If render_pdf returns an error about the browser not being found:
still write output/cv.html — the user can open it and print to PDF.
Report the fallback in the handoff.

If the HTML is very long and the model needs to shorten it:
compress the skills section first (one line per category), then
truncate older experience to one bullet each.

## Notes

The browser renders this — write CSS you'd write for a real website.
Flexbox and Grid both work. Google Fonts load via @import.
print_background: true is set, so background colours render in the PDF.

Do not use JavaScript. Do not reference external images.
Keep all CSS inside the <style> block.
