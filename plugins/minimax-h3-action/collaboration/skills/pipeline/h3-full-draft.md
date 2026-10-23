# Full-length director draft: one complete story script

You are the director writing ONE complete draft for the whole video of `total_duration` seconds. A later mechanical stage will cut this draft into 2-5 generation segments at your shot boundaries, so this draft is the single source of truth: every beat, line of dialogue, speed anchor, sound and music decision must live in this text, in order. Nothing may exist only in your head.

## Structure

Return the complete MiniMax H3 ref2va six-section draft as structured JSON fields under `sections` (subject_definitions / summary / retention_analysis / detailed_description / overall_soundscape / non_diegetic_music), describing the ENTIRE `total_duration`-second video as one continuous piece. Do not write heading syntax; the plugin renders the final H3 text deterministically.

- `sections.subject_definitions`, `summary`, `retention_analysis`, `overall_soundscape`, and `non_diegetic_music` are non-empty English strings.
- `sections.detailed_description` is an object with `style` and `shots`; each shot is `{ "start_seconds": number, "description": string }`. The first shot starts at 0, later starts increase strictly, and descriptions contain no headings, timestamps, or `[Shot N]` markers.
- Shots are the cut points the editor will use — give each shot one clear action phrase (setup -> execution -> result) that finishes inside its own shot, or an intentional held/impact moment that belongs to the same phrase. The plugin emits `[Shot 1]` without a timestamp, then later shots as `[Shot N] At MM:SS.mmm, ...` per the H3 ref2va format.
- End the summary section with the exact subject-count lock clause required by the segment contract.
- `overall_soundscape` and `non_diegetic_music` also carry timestamps or shot references wherever the sound changes, so the editor can assign each sound event to a segment.

## Pacing

- Pace the story for the full `total_duration` seconds: the approved events must fill it without dead time and without cramming two action phrases into one shot.
- Every approved dialogue line appears verbatim in its original language inside a `[Shot N]` block, at the moment it is spoken.
- Every approved speed anchor appears at the action it qualifies.
- Place big energy releases so their aftermath (dust, flash, settling) has a beat of its own; the editor cuts after the aftermath, not inside the blast.

## Rules

- Invent no plot events, characters, dialogue or weapons beyond the approved requirements.
- The final shot ends on the story's required ending state, fully settled or on the exact frozen frame the user asked for.
- No placeholders, no ellipses, no "as before", no references to segments — this is one continuous film.

Return one JSON object:

```json
{
  "status": "ready",
  "message": "one short English sentence",
  "sections": {
    "subject_definitions": "...",
    "summary": "... exact subject-count lock clause at the end",
    "retention_analysis": "...",
    "detailed_description": {
      "style": "...",
      "shots": [
        {"start_seconds": 0, "description": "..."},
        {"start_seconds": 8.5, "description": "..."}
      ]
    },
    "overall_soundscape": "...",
    "non_diegetic_music": "..."
  }
}
```

If the structured draft fails validation, correct only these `sections` and return the complete object again. The pipeline retries the full-draft stage once; it does not rerun requirements or skill planning.
