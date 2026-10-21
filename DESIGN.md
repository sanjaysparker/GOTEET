---
name: GOTEET
description: A quiet personal and team desktop for work, evidence and next steps.
colors:
  primary: "#ffab65"
  primary-hover: "#ffc08e"
  primary-ink: "#17191d"
  accent-mint: "#8cdbb1"
  accent-blue: "#8fb9ff"
  accent-lavender: "#c2b3ff"
  chart-track: "#303641"
  chart-lavender: "#b3b1ee"
  viewer-stage: "#101216"
  media-surface: "#20252c"
  background: "#17191d"
  rail: "#121417"
  surface: "#202329"
  elevated: "#282c33"
  border: "#353a43"
  text: "#f0f2f5"
  muted: "#b0b7c3"
  success: "#8cdbb1"
  warning: "#f6cb7b"
  danger: "#ff9a9a"
  field: "#1b1e23"
  menu: "#242830"
  menu-border: "#535d6b"
  menu-highlight: "#483526"
  menu-highlight-text: "#ffceaa"
  switch-off: "#4c535e"
  switch-on: "#a86e3f"
  switch-thumb: "#f8eee6"
typography:
  headline:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "29px"
    fontWeight: 620
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  title:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.015em"
  body:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "14px"
    lineHeight: 1.5
  label:
    fontFamily: "'Inter Variable', sans-serif"
    fontSize: "12px"
  mono:
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
rounded:
  chip: "4px"
  menu-item: "5px"
  control: "6px"
  table: "7px"
  surface: "8px"
  menu: "9px"
  dialog: "12px"
  switch: "15px"
  circular: "50%"
spacing:
  compact: "7px"
  control-gap: "9px"
  field: "10px"
  inset: "14px"
  row: "20px"
  section: "32px"
  media-column-gap: "18px"
  media-row-gap: "24px"
  chart-gap: "30px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  profile-menu:
    backgroundColor: "{colors.menu}"
    textColor: "{colors.text}"
    rounded: "{rounded.menu}"
    padding: "7px"
  permission-switch:
    backgroundColor: "{colors.switch-off}"
    rounded: "{rounded.switch}"
    padding: "2px"
    width: "39px"
    height: "23px"
  permission-switch-checked:
    backgroundColor: "{colors.switch-on}"
  media-thumbnail:
    backgroundColor: "{colors.media-surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.surface}"
    height: "135px"
  chart-ring:
    width: "150px"
    height: "150px"
  profile-photo:
    rounded: "{rounded.circular}"
    width: "80px"
    height: "80px"
---

# Design System: GOTEET

## Overview

**Creative North Star: "Evidence handoff"**

GOTEET is a quiet, dense personal and team desktop. Graphite surfaces, pale text, compact Inter typography and a default apricot accent keep evidence, work records and deliberate actions easy to scan. The expanded system preserves the original identity while accommodating user-selected mint, blue and lavender accents.

The shared shell places navigation, the active workspace and an optional assistant side by side. Flat rows and tonal boundaries carry the hierarchy. Charts, measured gauges, media thumbnails and linked project summaries bring richer information into the same restrained visual language; motion marks navigation and state changes.

**Key Characteristics:**
- Graphite tonal layers and restrained accent selection states.
- Compact Inter typography, flat rows and visible source context.
- Data graphics derived from records, with readable legends and empty states.
- Media-led previews and familiar native desktop actions.
- Profile and preferences anchored to the sidebar identity.

## Colors

The normative frontmatter preserves the graphite/apricot foundation and records the implemented extension palette.

### Primary
- **Warm Apricot:** the default primary accent for deliberate actions, focus and selected navigation.
- **Light Apricot:** the existing primary hover treatment.
- **Graphite Ink:** text on filled primary buttons, matching the final CSS override.

### Secondary
- **Preference Mint, Blue and Lavender:** optional user accent choices; these replace the runtime accent rather than recoloring every graphic or status token.
- **Chart Lavender:** paused-project and CPU differentiation; distinct from the preference lavender.

### Neutral
- **Workspace Graphite / Deep Rail:** the main canvas and sidebar.
- **Control Graphite / Raised Graphite / Field Graphite:** controls, open states and editable fields.
- **Slate Divider / Pale Text / Muted Slate:** boundaries, primary copy and secondary context.
- **Menu Slate / Menu Border:** account overlays and chart tooltip surfaces.
- **Warm Menu Highlight / Pale Apricot Text:** established highlighted account items.
- **Chart Track:** neutral rings, progress tracks and process bars.
- **Media Surface / Viewer Stage:** thumbnail placeholders and the darker preview canvas.

Success mint, warning gold and danger rose encode status. Permission switches retain their slate, warm brown and pale-thumb treatment. Some legacy hover, link, tab and chart colors remain fixed apricot; the accent preference is not a complete palette substitution.

**The Intentional Accent Rule.** Use the selected accent for navigation, focus and deliberate actions; preserve distinct status colors and readable neutral context.

## Typography

**Display Font:** Inter Variable, with sans-serif fallback.
**Body Font:** Inter Variable, with sans-serif fallback.
**Label/Mono Font:** ui-monospace, with monospace fallback, for paths, code and commit identifiers.

The compact hierarchy pairs tightly tracked page headings with quieter metadata. Shared roles are in the frontmatter. Contextual labels range from 9px footer metadata to 13px row titles; paragraphs generally use 12px type with generous local line height. Paragraphs cap at 72ch and introductions at 65ch. Headings reduce to 26px at the first desktop breakpoint. Project overview counts use 27px type; chart center totals use 28px and tabular figures support count comparisons.

## Layout

The default shell uses a 205px rail, a flexible workspace with a 480px minimum and a 330px assistant. The toolbar is 62px tall; independently scrolling main content uses 34px 30px 48px padding. Sections use the incumbent spacing rhythm. Hiding the assistant leaves the rail and workspace; no drag-resize behavior is established.

At 1250px, rail/assistant widths become 180px/300px and the workspace minimum becomes 440px. At 1050px they become 164px/280px with a 430px workspace minimum. Work charts collapse from two columns to one at 1250px. These source rules do not establish visual validation of small windows.

Media uses an auto-filling grid with a 170px minimum tile, a separate list mode, and wrapping tools for search, type, sort and view. Work charts pair a status ring and legend with project distribution; project summaries use four metric columns. System combines three resource gauges, CPU history and divided findings. Profile uses an 80px circular photo and a two-column field group capped at 680px. Comfortable density increases table vertical padding and navigation size; compact remains the default.

The existing account menu opens above the sidebar identity, start-aligned with a 12px offset. Settings uses horizontal tabs; ordinary fields cap at 390px. Preview dialogs fill the available desktop area with a header, content stage and footer.

## Elevation & Depth

The workspace is flat, with tonal layering and thin borders. Shadows separate the account menu (`0 12px 32px #0007`) and dialog (`0 20px 60px #0007`). Dialog backdrops dim the workspace; the media viewer uses a darker stage to center the asset. Data rings and 3D content convey information rather than adding decorative dashboard depth.

Motion uses a short route entry (opacity and 8px travel over 0.2s), project workspace entry, measured gauge/progress transitions and restrained thumbnail hover scale. Charts animate status/distribution over 550ms and development activity over 650ms. The About mark has a hover tilt. OS reduced motion disables CSS animation/transitions and suppresses route/chart entry; the in-app setting also quiets Motion/Recharts and applies the global short-duration override. These values are source-derived; animation timing was not visually validated.

## Shapes

Controls retain gently curved corners; tables and surfaces have slightly broader edges. Chips remain compact, menus have inset rounded items, and preview dialogs use the incumbent dialog corner. Profile images are circular; resource and status rings use circular geometry with open centers for values. Charts keep thin grid lines and compact legends. Exact reusable corner tokens remain in the frontmatter.

## Components

### Buttons

Compact controls pair primary fill with graphite ink and secondary graphite fill with a thin border. Hover lightens the fill; keyboard focus uses a 2px accent outline with 3px offset. Disabled controls use 0.48 opacity. The final button transition uses 0.16s for color/border/background and 0.12s for the 1px press translation.

### Chips

Small flat tags use compact padding, 10px type and a chip corner. Success and warning variants combine tinted graphite backgrounds with pale status text. Status remains legible alongside its written label.

### Cards / Containers

Flat rows carry evidence, permissions, models, skills and system findings. Tables use a thin border and sticky headings. Inline notes are tonal bordered containers. Media tiles separate thumbnail, filename and metadata with a bottom divider; they are not elevated cards. The linked project workspace uses divider boundaries, summary counts, a completion meter and destination actions.

### Inputs / Fields

Dark fields use the shared border and control corner, with accent focus and caret. Profile includes a local photo action and labelled role, organisation, optional location, website and bio fields. Preferences exposes accent, density, reduced motion, start view and timezone. Setup copy stays adjacent to its relevant control; do not hide unavailable authentication behind a successful-looking state.

### Navigation

Muted rail icons and labels gain a tonal hover. Active navigation now derives its text, tinted background and border from the selected accent. The identity trigger opens the existing Radix account menu. Settings extends the established tabs with About; “Made by SPARKER” belongs only there. Models uses familiar tabs and setup rows; Files uses places, a path field, a selection row and native action controls.

### Charts and measured health

Recharts status rings pair record totals with clickable legends that filter the current records. Task bars group saved tasks by project; development activity shows distinct captured default-branch commits over seven IST calendar days. Empty datasets keep an explicit empty state. System resource rings show measured memory, disk and CPU values with written context; process bars and CPU history support inspection. Chart colors retain semantic distinctions independently of the preference accent.

### Media and 3D preview

Thumbnail grid and list modes share search, filters, sorting and metadata. The full preview dialog supports content-specific controls and visible loading/error states. Native video/audio controls remain familiar. Supported 3D content loads in a lazy Three.js canvas with viewer tools and status messages. Document and image previews use their actual asset; a placeholder is not proof of successful rendering.

### Evidence handoff

Assistant answers and reviewed plans share an inspector. An explicit apply control separates a proposed plan from a committed change. Source context, measured values and setup status remain visible alongside work.

The review disposition is ship for the 11 captured Mac screens recorded in PRODUCT.md, including the Media grid capture from v0.3.0 and ten v0.3.1 captures. Alternate accents/density, motion timing, small windows and other operating systems remain visually unvalidated. Native video advancing two seconds and agent preview acknowledgement are targeted functional proof. Missing OAuth/provider credentials and update release source remain setup gaps, not visual defects.

## Do's and Don'ts

### Do:
- **Do** preserve graphite surfaces, compact Inter hierarchy and the default apricot identity.
- **Do** honor the selected accent while retaining distinct status and chart meanings.
- **Do** pair graphics with counts, labels, coverage and real empty states.
- **Do** keep keyboard focus and OS/app reduced-motion behavior consistent.
- **Do** extend established rows, tabs, fields, previews and account controls.

### Don't:
- **Don't** replace flat work rows with nested decorative cards.
- **Don't** copy illustrative preview content into evidence claims.
- **Don't** present source inspection or Mac captures as cross-platform visual validation.
- **Don't** use authentication or update setup gaps as evidence of visual defects.

## Reader and appearance extension — 0.5.0
Preserve GOTEET's compact Inter desktop workspace and apricot identity. Paper documents use a white reading surface independently of shell theme. New toolbars wrap but controls retain intrinsic widths. Mail uses a message-list/reading-pane layout. Navigation and reading transitions remain short and respect reduced motion. The assistant is a bounded flex column: only its body scrolls; composer stays visible.

Shell themes: Graphite (existing palette), Midnight (#111827 background, #0c1220 rail, #192235 surface, #24324b elevation, #394762 border, #f1f5fb text, #b6c3d7 muted), Paper (#f5f4f0 background, #eeede8 rail, #ffffff surface, #e5e7eb elevation, #c7cbd2 border, #202632 text, #505b6b muted). Custom accents are user choices. Preserve semantic danger/success colors. Existing global brand illustration/3D backgrounds remain intentionally dark. No flashing/decorative looping effects.
