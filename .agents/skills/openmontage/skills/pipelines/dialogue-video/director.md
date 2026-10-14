# Portable dialogue video director

Integration addition, not an upstream pipeline rewrite. This director applies only to
`dialogue-video`; all other OpenMontage pipelines keep their original behavior.

Resolve the installed `dialogue-video-skill` directory from the caller or user configuration.
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

Media generation and post-processing are exclusively the caller producer's authorized
videofree MCP tools. OpenMontage's vendor adapters are not a second generation route.
The caller discovers the gateway capabilities; the local registry discovers composition
and analysis capabilities. Neither can substitute for the other.

Keep fixed host identities and voice assets. The caller requires Qwen Image 2.1 for all
new drafts, identity/scene references and four-panel storyboards, in that order with QA.
Split and review each panel before H3 compile; direct video submissions are forbidden.
Read the caller's evidence gate contract and require --production for completed media
checkpoints. Long shots may be refined according to real
capabilities. Do not hardcode eight seconds, 736x1312 or obsolete
zizai_video/zizai_video_post tools. After exhausted retries, an unqualified best attempt
is still FAIL/BLOCKED. Do not silently regenerate voices or strip dialogue audio.

Before entering a stage, persist in_progress. Before completing it, require current QA
and canonical schema validation. Save checkpoints using the caller's bridge, which
delegates to lib.checkpoint; no parallel homemade checkpoint store. Resuming queries
get_next_stage and the existing gateway ledger, never re-submits completed jobs.
When revising upstream work, invalidate downstream checkpoints by marking them in_progress
before continuing; old reports cannot approve changed inputs.

The manifest permits automatic stage progression ONLY within the user's recorded content,
budget, runtime and review authorization. Without that authorization, use the bridge's
--require-approval and stop at awaiting_human; --approved requires a real user approval.
Gateway confirmation defaults to explicit user approval. Only a user's recorded,
shot-scoped delegation of H3 review AND confirmation permits the producer to confirm
after reviewing the actual draft. General automatic-progression permission is not that delegation.
All caller submissions and confirmations use guarded_mcp.py; reference input receipts
include actual upload IDs and hashes, including fixed hosts in grids. The selected
gate covers reviewed refinements; the final gate binds selected media, compose inputs
and the reviewed rendered file. Unchanged artifact specifications may reuse their QA.

Select the composition runtime at proposal and preserve it at edit. All composition,
audio mixing and rendering use native video_compose and audio_mixer tools; do not write
a caller-side FFmpeg composer. Read each tool's usage_location and agent_skills, preserving original
Remotion/HyperFrames features and schema. Present available runtime alternatives before
choosing; failures do not authorize runtime substitution. Board startup is optional and
requires permission to start a service; it is never a prerequisite for production.

Publish means local export unless the user explicitly authorizes external publishing.
Check final file hashes, dialogue, native dimensions, audio and QA; deliver checkpoints,
canonical artifacts, ten final documents, execution index, source media, ledger and final report together.
