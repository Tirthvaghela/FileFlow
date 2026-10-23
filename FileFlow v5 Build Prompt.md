# FileFlow v5 — Frontend Rebuild Master Prompt

Copy everything below the line into Claude Code (or your Claude extension) from the root of the FileFlow repo. Put `FileFlow v5.html` (the offline prototype) at `design/FileFlow v5.html` in the repo first; it is the visual source of truth.

---

You are rebuilding the FileFlow frontend (`frontend/src`, React) to match the approved design prototype at `design/FileFlow v5.html`. Open it in a browser and use it as the pixel reference for every screen and dialog. The prototype uses fake data; the real app must use real API data.

## 0. Hard rules

- Work on a new branch `ui/v5-sorting-office`. Do not commit or push without my approval.
- Do NOT change: backend, API request/response shapes, database, rule classification order, file move/undo logic, auth/token handling, agent commands, UiPath workflows.
- Keep every existing route, handler, dialog and feature working. Restyle and re-layout; never replace a real handler with a no-op.
- Never fabricate data. If an endpoint doesn't supply a number, don't show it. Distinguish three states everywhere: **loaded**, **empty** (real zero), **unavailable** (request failed → say so; never show 0).
- Don't add new npm packages unless one is truly required. Reuse what's installed.
- Before starting: run `git status`, read the router, list every page and dialog, and run the existing tests + build to get a baseline.

## 1. Concept

"Sorting office": files arrive in a tray, rules sort them, folders receive them. Paper, ink, manila folder tabs, rubber-stamp statuses, monospace file slips. Minimal and calm, not decorative.

## 2. Design tokens (CSS variables in one global stylesheet)

```css
:root{
  --paper:#EFE9DD; --sheet:#FBF9F4; --sheet-2:#F5F1E8; --tab:#E2DACA; --tab-h:#D9D0BD;
  --ink:#1C1B18; --ink-2:#45423B; --muted:#6B665B; --rule:#E1D9C9; --rule-2:#CDC2AC;
  --manila:#E9D49E; --manila-2:#D6BB78; --manila-ink:#3F310D;
  --stamp:#C23E26; --stamp-bg:#F7E1DA; --filed:#1E6A4B; --filed-bg:#DCEDE3;
  --warn:#8F5500; --warn-bg:#F6EACB; --mark:#F3E27A; --mark-ink:#1C1B18;
  --shade:rgba(60,45,15,.16);
  --ease:cubic-bezier(.2,.7,.2,1); --d1:120ms; --d2:220ms; --d3:380ms;
}
:root[data-theme="dark"]{
  --paper:#14120F; --sheet:#1D1A15; --sheet-2:#24201A; --tab:#27231C; --tab-h:#302B22;
  --ink:#EEE7D8; --ink-2:#CFC6B3; --muted:#A09784; --rule:#312C24; --rule-2:#433D32;
  --manila:#C7AA62; --manila-2:#A88C48; --manila-ink:#1D1606;
  --stamp:#F07256; --stamp-bg:#3A1D16; --filed:#6CC79B; --filed-bg:#16281E;
  --warn:#E7B45B; --warn-bg:#2E2413; --mark:#6D5F17; --mark-ink:#FFF6CC; --shade:rgba(0,0,0,.5);
}
/* forced-dark panel (dashboard "machine room") */
[data-ink]{ same values as dark theme }
body{ background-color:var(--paper);
  background-image:radial-gradient(var(--rule-2) .7px,transparent .7px); background-size:16px 16px; }
```

Color roles: ink = primary buttons/text; stamp red = attention, conflicts, "now", top-tier highlight; filed green = success/on switches; warn amber = warnings; manila = folder/destination tags; mark yellow = highlighted matched text in filenames.

Theme: toggle in header ("Night"/"Day"), set `data-theme` on `<html>`, persist in localStorage, default from `prefers-color-scheme`. Keep the existing theme logic if present.

## 3. Typography

- Load from Google Fonts: `Archivo:wdth,wght@62..125,400..900` and `JetBrains Mono:wght@400;500;600`.
- **Display / page titles:** Archivo 800, `font-stretch:112%`, letter-spacing -0.025em, `clamp(28px,3.4vw,40px)`.
- **Labels (kicker style):** Archivo 600, `font-stretch:125%`, 10.5px, letter-spacing .14em, uppercase, `--muted`. Usually followed by a flex-1 dashed rule line.
- **UI body:** Archivo 13.5px.
- **Mono:** JetBrains Mono for file names, paths, counts, tier numbers, hashes, timestamps.

## 4. Shared components (build these first)

- **Stamp:** inline-flex, height 20px, padding 0 7px, `1.5px solid currentColor`, radius 3px, Archivo 700 9.5px, stretch 120%, letter-spacing .1em, uppercase, `rotate(-2deg)`, nowrap. Colors: Filed (filed), Duplicate (warn), Archived (ink-2), Refiled (ink), Undone (muted), Error/Shadowed (stamp). New stamps animate with `ffStamp` (scale 1.6→1, fade in).
- **FileBadge:** 30–36×36–42px, radius `2px 8px 2px 2px` (folded corner), border rule-2, bg sheet-2, extension text (≤4 chars uppercase) bottom-centered, mono 8.5px.
- **FolderTag:** mono 12px, padding 2px 7px, bg manila, color manila-ink, radius 2px, may wrap (`overflow-wrap:anywhere`, `box-decoration-break:clone`). Never let flex shrink it so it clips.
- **Switch:** square-ish (radius 3px), 32–40×18–22, knob radius 2px; on = filed, off = rule-2. `role="switch"` + `aria-checked`.
- **Buttons:** primary = ink bg / paper text, radius 4px, 34–38px tall, weight 700. Secondary = 1px ink border, transparent. Tertiary = 1px rule-2 border, sheet bg. All `white-space:nowrap; flex:none`.
- **Segmented / radio chips:** selected = ink bg + paper text; unselected = sheet bg + rule-2 border.
- **Highlighted filename:** split the filename around the matched value; wrap the match in `<mark>` (bg `--mark`).
- **Dialog shell:** overlay `rgba(20,16,10,.55)`, panel width `min(100%,780px)`, radius `0 6px 6px 6px`, a folder **tab** sticking out above the top-left (28px tall, sheet bg, label + small red dot). Header has title (Archivo 800 24px) + sub + × button and a 2px ink bottom border. Body scrolls (`overflow-y:auto; overflow-x:hidden`). Optional footer (sheet-2 bg) with note + Cancel + primary. Esc and backdrop click close; trap focus; restore focus on close.
- **Toast:** bottom-center, ink bg, paper text, radius 4px, auto-hide ~2.8s.
- **Empty / unavailable blocks:** empty = bold Archivo 18px line + muted sub. Unavailable = red text or a dashed red box with a "No data" stamp and "Try again".

## 5. App shell

- **Header row** (max-width 1360, padding 18px 24px 0, flex-wrap):
  - Logo: small ink folder shape (13×6 tab + 30×19 body, radius 0 4 4 4) with a 7px red dot; wordmark "FILEFLOW" Archivo 800, stretch 125%, letter-spacing .06em.
  - "WATCHING" label + mono path chip (inset shadow, ellipsis), e.g. the real watched folder.
  - Right side: Auto-sort switch button (real monitoring toggle), agent status chip (real `agent_connected`), Day/Night theme button, "Downloads ▾" menu (existing simulate-download + agent installer actions), avatar initials + "Sign out".
- **Folder-tab nav** below header: horizontal row of trapezoid tabs (`clip-path:polygon(10px 0,calc(100% - 10px) 0,100% 100%,0 100%)`), 42px tall, uppercase Archivo stretch 116%, each prefixed with a mono number `01`…`07`. Active tab bg = `--sheet` (merges into the page sheet), inactive = `--tab`, hover `--tab-h`. Rules tab shows a red count badge of real conflicts. Overflow-x scrolls on mobile (no hamburger).
- **Page sheet:** sheet bg, radius `0 6px 6px 6px` on Dashboard (joins the first tab) else 6px, padding `clamp(18px,3vw,30px)`, soft shadow.
- **Page header** inside the sheet: kicker line (`01 · INTAKE DESK`), H1, one-line sub, 2px ink bottom border, 22px margin below.

## 6. Dashboard (match the prototype exactly)

Row 1 (flex-wrap, gap 22):

**A. Machine room panel** (`data-ink`, always dark, flex 1 1 640px, radius 6, padding 22):
- Top: status pill (dot + "Auto-sort on/off") and a manila date chip "THU · 22 OCT 2026".
- **Flip counter:** today's filed count, each digit its own tile 64×88, mono 700 64px, split-flap look (top half sheet-2, bottom half rule, 1px dark line across the middle). Beside it: "files filed today" (Archivo 800 22px) + "N waiting in Downloads · last one X min ago".
- **Today timeline:** 24-hour strip, hour ticks, one small manila square per file filed today at its time (latest one red), a red "now" line + dot, hour labels 00:00/06:00/12:00/18:00/now.
- Top-right: 2×2 ledger grid (filed this week + 7-day mini sparkline, in category folders, unclassified (amber), rule conflicts (red)). Each cell clickable (Reports / Categories / Suggestions dialog / Conflicts dialog).
- **"This week by rule tier"** list: one row per tier with >0 files: `01 Keyword` · thin 6px bar (width ∝ count, red for tier 1, ink-2 otherwise) · under the bar the destinations "Finance/Invoices 18 · Screenshots 6 · Documents 7" · count right-aligned. Footnote listing tiers that caught nothing. Only render with real per-tier/per-folder counts; if the API doesn't provide them, hide this block (don't invent).

**B. Right column** (flex 1 1 300px):
- "Organize existing files" as a **manila folder card**: darker manila tab on top-left, body manila, kicker "MANUAL SWEEP", title Archivo 800 24px, description, dashed divider, "Preview the plan →". Opens the existing Organization Preview dialog.
- "Needs you": items with 3px colored left border on sheet-2 (conflicts red, unclassified amber), big mono count, title + sub, arrow.
- Three square tool tiles: `01 / search` Search your files, `02 / dupes` Find duplicate files, `03 / health` Organization health. Must call the existing dialog handlers.

Row 2:
- **Latest slips** (receipt): sheet-2 bg with a perforated top edge (radial-gradient circles), 5 most recent activity entries: FileBadge, filename with matched term highlighted, "→ Destination" (nowrap) + "Tier N · Keyword invoice", stamp + time. "All activity" link.
- **This week** bar chart (7 days, value labels, latest day red) and **Pigeonholes** (3×N grid of folders with counts, inset shadow) — real data only.

Row 3: **How a file moves** strip: Detect → Classify → Explain → Move → Log (numbered circles, Classify filled ink), with the note that only "Organize existing files" stops at a preview and re-scans/re-plans on confirm.

A result banner (filed-bg, "Filed" stamp) appears after a confirmed organize run, from the real response.

## 7. Rules page

Toolbar: search input (filters by match text or folder) · "+ New rule" (primary) · "Generate with AI" (opens AI Rule Generator) · "Check conflicts" (spinner while running, then opens Rule Conflict dialog; label shows real count).

Three columns (flex-wrap):
1. **Tier index** (sticky, ~230px): "Priority order" label, "All tiers" item, then 9 tiers `01 Keyword … 09 Default` each with rule count and a 3px bar of files caught this week (if available). Selected = 3px red left border + sheet-2 bg. Clicking filters the middle column. Footnote: "A higher tier always wins."
2. **Tier groups**: heading = big mono tier number (28px) + uppercase tier name + description + "N rules · N files this week", 1.5px ink underline. Rules render as **index cards** in a grid (`minmax(210px,1fr)`): tier id `T01`, conflict stamp (after a check, clickable), switch (real enable/disable), condition in mono 15px, "→ FolderTag" (wraps, never clips), usage bar + "N this week". A red 1px ruled line across the card at 40px like an index card. Each editable tier ends with a dashed "+ Add a Keyword rule" card that opens the form preset to that tier. Tiers 7–9 show a note card (Category mapping / Automatic grouping state / Default category) with a link to Categories or Settings.
   - New-rule form (bordered ink box): Rule type select (tiers 1–6), match input (label/placeholder change per type), destination input with folder datalist, inline validation (empty, invalid regex), note "Joins tier N. Rules above it still win." Use the existing rule-form util/handlers.
3. **Precedence tester** (always dark `#1C1B18`, fixed literal colors, sticky): "Where would this file go?", sample files (invoice.pdf, IMG_20261021_184233.jpg, random_export.xyz), the 9 tiers listed with verdicts (no match / ✓ decides / would match .pdf / not reached), hit row manila and nudged right, result line `file → Destination` + explanation. Explanatory UI only — derive from the rules list, don't add a frontend rule engine beyond this display. Below it: a compact Conflicts list (stamp + "A vs B").

Required priority order to show everywhere: 1 Keyword, 2 Regex, 3 Content keyword, 4 Extension, 5 Large file, 6 File age, 7 Category, 8 Automatic extension, 9 Default.

## 8. Settings page

Two columns:
1. **Section nav** (sticky ~220px): `01 Monitoring`, `02 Sorting`, `03 Duplicates`, `04 Remote agent`, `05 Account`, each with its live state underneath (e.g. "Auto-sort on" green, "Rename", "2FA on"). Click smooth-scrolls to the card.
2. **Cards** (border rule-2, radius 4, header strip sheet-2 with mono number + uppercase title + description):
   - **Monitoring:** big title "Auto-sort is on/paused" + description + large 64×34 switch; dashed divider; "WATCHED FOLDER" + path chip.
   - **Sorting:** rows tagged `T08` (Automatic grouping switch) and `T09` (Default category select), then a live preview strip: `random_export.xyz → [T08 Automatic | T09 Default] → FolderTag`.
   - **Duplicates:** three radio cards Skip / Rename / Replace, each with description and a mini example ("Documents/report.pdf exists → Documents/report (1).pdf"). Note: identical content is always skipped.
   - **Remote agent:** status ring with green/grey dot, title, last-seen description, Download button.
   - **Account:** 2FA switch, Sign out (red outline). Rows must not wrap the control onto its own line (text block `flex:1 1 0; min-width:0`).
   - Sticky save bar at bottom: muted when clean, ink when dirty ("You have unsaved changes." + Save). Only include settings that already exist in the codebase; map each control to its real handler.

## 9. Other pages & dialogs (same system)

- **Activity:** search + filter chips (All/Filed/Duplicates/Archived/Undone). Rows: time, FileBadge, highlighted filename, "→ dest", stamp, `T01` tier chip, agent command status (moved on your PC / waiting / failed) when present, "Why here?" toggle, Undo. Expanded: 9-cell tier ladder (matched cell ink), facts grid (Match type, Matched value, Rule, Destination, Priority) and a one-line explanation; handle missing explanation and default-category cases. Rows wrap on mobile (keep the existing ActivityTable mobile fix).
- **History:** timeline grouped by day with a 2px ink spine and colored dots; checkbox selection + sticky "Undo selected" bar; per row "Refile to…" select (real reclassify) and Undo; undone rows faded with an "Undone" stamp.
- **Categories:** cabinet grid — each category a drawer: manila label holder, handle bar, mono count + size + share %, stacked file-type strip with legend (only if the API gives type breakdown). Hover lifts. **Category detail:** filter input, "Find duplicates", file list (badge, name, added, size).
- **Reports:** period segmented control, Export CSV/PDF (real handlers), KPI row, bar chart with real axis values (max/mid gridlines, peak bar red), "Which rule tier decided" horizontal bars.
- **Login / Register / Forgot / Reset / 2FA:** split screen — left dark panel with wordmark, headline "Every download, filed where it belongs.", and the 9 tiers as stacked staggered folder tabs (first one manila); right side the form (44px inputs, show/hide password, inline errors, 6-digit mono code input for 2FA). Keep auth behavior unchanged.
- **Dialogs:** Organization Preview (5 clickable count tiles Planned/Ready/Skip·duplicate/No match/Error, slip rows with stamps and reasons, confirm → spinner → result with "Filed" stamps animating only after the backend confirms), AI Rule Generator (textarea + example chips, loading, provider error state, proposal cards with Add rule/Discard and "Added" stamp), AI Unclassified Suggestions (cards with Ready/Low confidence/No suggestion stamps), Rule Conflicts (severity stamp, "WINS" ink box vs dashed losing rule, example file), Duplicate Groups (stapled stack cards with sha256 hash → detail view with red dashed spine, oldest copy tag; no delete), Natural Language Search (big underlined input, example chips, "Understood as" chips, results with highlighted match, provider-error ≠ empty), Organization Health (stamp per check OK/Attention/Action with action buttons; unavailable state never shows "healthy").

## 10. Motion

Keyframes: `ffIn` (opacity 0 + translateY 10px → none), `ffPop` (translateY 16 + scale .985), `ffFade`, `ffStamp`, `ffSlide` (translateX -14), `ffSpin`, `ffToast`. Page content enters with ffIn (--d3); lists stagger 40–60ms; dialogs fade backdrop + pop panel; stamps use ffStamp when they appear; hover lifts 2–4px; press `scale(.98)`. Use transform/opacity only. Respect reduced motion:

```css
@media (prefers-reduced-motion: reduce){*,*::before,*::after{animation-duration:1ms!important;animation-delay:0ms!important;transition-duration:1ms!important}}
```

Prefer the animation library already in the repo (Framer Motion if present) for route/dialog transitions; otherwise CSS.

## 11. Responsive & accessibility

Test at 1440, 1280, 1024, 768, 390, 360 px. No page-level horizontal scroll. Columns use `flex-wrap` with flex-basis (e.g. `flex:3 1 520px` / `flex:2 1 320px`) and `min-width:0`. Buttons never wrap text. Long filenames wrap (`overflow-wrap:anywhere`) or ellipsis with `title`. Sticky side columns become normal flow when stacked. Visible focus ring `2px solid var(--stamp)`. Text contrast ≥ 4.5:1 in both themes. Status never by color alone (stamps carry words).

## 12. Deliverables

1. Implement tokens + shared components, then shell, then Dashboard, Rules, Settings, then remaining pages and dialogs.
2. Run the app against the real API; compare each screen side by side with `design/FileFlow v5.html` in both themes.
3. Run `npx vitest run` and `npm run build` (plus lint). Don't edit tests just to pass.
4. Report: changed files, test counts, build output, screenshots of each screen (desktop + 390px, light + dark), anything that couldn't match because the API lacks the data.
