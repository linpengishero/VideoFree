# Reference mode: multi-segment continuation

The user supplies a story brief plus reference images (optionally one video and one audio). The requested duration is the whole-video total: up to 15 seconds it is one single clip; above 15 seconds the director first writes ONE complete six-section draft for the whole video, an editor stage then cuts that draft into 2-5 generation segments at shot-level breathing points, and each cut is converted into a standalone MiniMax H3 ref2va execution draft. The first segment starts from the reference images; every later segment continues from the previous segment's ending state, guided by its final frames.

## Ready contract

When `status` is `ready`:

- `optimized_prompt`: the complete English ref2va execution draft for **segment 1** (for a single-clip production, the only draft), in the exact six-section order required by the Ref2VA Full-Reference Skill (`subject_definitions:` / `summary:` / `retention_analysis:` / `detailed_description:` / `overall_soundscape:` / `non_diegetic_music:`).
- `optimized_prompt_zh`: the full Chinese confirmation. Multi-segment productions format it as 【第一段·X秒】…\n【第二段·Y秒】… with one paragraph per segment plus one final line listing every segment's duration and the total; a single-clip production is one paragraph with no headers.
- `generation_payload.parameters`:
  - `"segments"`: integer 1-5.
  - `"prompt_2"` … `"prompt_N"`: the complete English ref2va six-section execution draft for each continuation segment (exactly `segments - 1` entries, no `prompt_1`, no entries beyond `segments`; none at all for a single clip).
  - `"durations"`: a comma-separated string of `segments` numbers (1-15 seconds each), e.g. `"12.5,12.5,12.5,12.5"`; segment lengths may differ.
- `generation_payload.settings` (optional):
  - `"duration"`: must equal the user's selected whole-video total (1-75 seconds), never a segment's duration. Allocate segment timings only through `parameters.durations`, whose sum must equal this total. The user already chose the aspect ratio and resolution in the submit form; never propose `ratio` or `resolution` overrides.

## Segment rules

- A production of 15 seconds or less is one clip: no splitting, no continuation sentence, no merge.
- Every segment draft is self-contained and follows the full ref2va format: exact dialogue stays in its original language inside `<d>[Language] ...</d>`; speakers keep stable `(S1)` IDs; camera movement uses clear H3 vocabulary; `overall_soundscape` and `non_diegetic_music` are always present.
- `<Picture 1>` remains the appearance authority in every segment: the same reference images are supplied to each one. Keep reference-backed appearance delegated to the labels; never restate invented appearance details.
- Continuation segments open by continuing the previous segment's ending pose, prop ownership, positions and screen direction — never replay the previous beat and never reset to a neutral stance.
- Segment boundaries fall at shot-level breathing points: a completed action phrase, a landing, a settled pose, a continuable held moment. No ellipses, "same as above", or references to another segment's text.

Record your cut-point reasoning, per-segment duration list, and any default overrides in `decisions`.
