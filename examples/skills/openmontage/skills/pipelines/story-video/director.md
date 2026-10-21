# Portable story video director

Integration addition, not an upstream pipeline rewrite. This pipeline supports general
story-driven long videos. Genre, cast, scene structure, action, dialogue, narration and
sound design are derived from the user's story; no dialogue/explainer format is assumed.
Other OpenMontage pipelines are unchanged.

Resolve the installed `story-video-skill` directory from the caller or user configuration.
Read its SKILL.md, references/openmontage.md and the current stage's reference below.
Missing caller or dependencies is BLOCKED, never a fallback to pk-dialogue-story.

| Stage | Caller guidance | Canonical artifact |
| --- | --- | --- |
| research | references/preproduction.md | research_brief |
| proposal | references/install.md, references/preproduction.md | proposal_packet, decision_log |
| script | references/preproduction.md | script |
| scene_plan | references/preproduction.md, references/subagents.md | scene_plan |
| assets | references/generation.md, references/subagents.md | asset_manifest |
| edit | references/compose.md | edit_decisions |
| compose | references/compose.md, references/subagents.md | render_report |
| publish | references/compose.md | publish_log |

Use each original `schemas/artifacts/<name>.schema.json` before writing an artifact.
Complete the caller's ten-document final package and independent preproduction review
before any media generation; see references/final-package.md. Generation executes those
final documents, rather than assigning another round of whole-film planning.
The caller's production.json is an automatically built document/hash index and execution
ledger, NOT a script snapshot or a substitute for canonical OpenMontage artifacts.
Canonical artifacts project the final documents into the original schemas; never maintain
a second independently authored script or mislabel the index as script/scene_plan.
Record source claims honestly; fictional work is explicitly fictional, not fabricated research.
Read meta/reviewer.md and meta/checkpoint-protocol.md; independent QA is governed by the
caller protocol, not replaced by producer self-review.

Media generation, composition and post-processing are exclusively the caller producer's authorized
videofree MCP tools. OpenMontage's vendor adapters are not a second generation route.
The caller discovers the gateway capabilities, including film-studio composition actions; the local
registry only discovers analysis capabilities. Neither can substitute for the other.

All recurring subject identities are derived from the story; the pipeline ships no fixed cast.
Voice references are created only for characters whose voices must remain consistent. The
caller requires Qwen Image 2.1 for new drafts, identity/scene references and four-panel
storyboards, in that order with QA.
Split and review each panel before H3 compile; direct video submissions are forbidden.
Read the caller's evidence gate contract and require --production for completed media
checkpoints. Long shots may be refined according to real
capabilities. Do not hardcode eight seconds, 736x1312 or obsolete
zizai_video/zizai_video_post tools. After exhausted retries, an unqualified best attempt
is still FAIL/BLOCKED. Do not silently change approved audio or narrative content.

Before entering a stage, persist in_progress. Before completing it, require current QA
and canonical schema validation. Save checkpoints using the caller's bridge, which
delegates to lib.checkpoint; no parallel homemade checkpoint store. Resuming queries
get_next_stage and the existing gateway ledger, never re-submits completed jobs.
Gateway-side ai-project-progress and project-archive are the caller's project-management
channel for human-visible stages and manuscripts; OpenMontage checkpoints remain the
authoritative local stage state. Neither substitutes for the other.
When revising upstream work, invalidate downstream checkpoints by marking them in_progress
before continuing; old reports cannot approve changed inputs.

At kickoff, record one project-scoped authorization covering the approved story revision,
budget, retry/refinement limits, H3 draft review and confirmation, QA mode and local export.
Within that scope, progress through stages and confirm each conforming H3 draft after review
without asking again per shot or checkpoint. If independent QA agents are unavailable,
continue with frame-based visual review and audio/technical checks only when the user has
authorized a disclosed `self_review` fallback. Without automatic authorization, use the
bridge's `--require-approval` and stop at `awaiting_human`. Pause for overspend, material
ambiguity, scope changes, missing required capability or unrecoverable failure. External
publishing is never included in local-export authorization.
All caller submissions and confirmations use guarded_mcp.py; reference input receipts
include actual upload IDs and hashes for every required visible subject and scene reference.
Video QA reviews the real clip by playback or a timestamped sequence of extracted frames
covering the start, key action beats and end; add samples around cuts and complex motion.
Final QA samples the rendered timeline similarly and checks audio separately. A cover frame
alone is never sufficient. Attach voice references only to dialogue shots that need them. The selected
gate covers reviewed refinements; the final gate binds selected media, compose inputs
and the reviewed rendered file. Unchanged artifact specifications may reuse their QA.

All editing, audio mixing and rendering run gateway-side through the caller's film-studio
plugin actions (film.save/add-clip/film.validate/film.preview/film.render/film.get) per
references/compose.md. Do not use OpenMontage video_compose or audio_mixer for this pipeline,
and do not write a caller-side FFmpeg composer. edit_decisions and render_report project the
film plan and render receipts into the original schemas; the final gate binds the downloaded
rendered file. Honest gaps (no automatic ducking, no motion-graphics runtime, enumerated
output sizes, overwritten final.mp4 requiring immediate versioned download) are recorded,
never faked. Board startup is optional and requires permission to start a service; it is
never a prerequisite for production.

Publish means local export unless the user explicitly authorizes external publishing.
Check final file hashes, narrative, action continuity, native dimensions, and the
audio/dialogue designed for the story; deliver checkpoints,
canonical artifacts, ten final documents, execution index, source media, ledger and final report together.
