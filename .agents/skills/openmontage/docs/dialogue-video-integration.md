# dialogue-video integration additions

This source distribution preserves OpenMontage's original name, source, README,
copyright notices and GNU AGPL v3 LICENSE. The following local additions integrate
the independently installed dialogue-video-skill, and are not upstream official releases:

- SKILL.md: discoverable skill entry.
- pipeline_defs/dialogue-video.yaml: portable dialogue pipeline.
- skills/pipelines/dialogue-video/director.md: caller-specific stage guidance.
  The caller now requires Qwen-only new imagery, four-panel split storyboards,
  H3 compile sessions and cumulative file/hash/QA evidence gates in its bridge.
  Guarded submissions persist requests and receipts; fixed host reference uploads
  are required in grids. Selected-media and final gates bind refinement parent
  receipts, composition inputs and reviewed output hashes. Scoped explicit user
  delegation is distinct from default manual H3 confirmation.
  All ten final documents and independent preproduction QA precede media generation.
  production.json is an automatically built source/hash index with execution records;
  canonical artifacts are projections of the final package, not a second authored script.
  Generation requests derive final asset, four-panel and H3 prompts from their respective
  documents, binding actual uploads without replanning the film during generation.
- This integration notice.

Original pk-dialogue-story remains available for its original environment. New callers
must not use it as the portable pipeline. OpenMontage checkpoint persistence, canonical
artifact schemas, tool registry and optional composition runtimes remain the actual
implementation, not a copy or renamed replacement.

Distribute the complete source and LICENSE with these additions. Review upstream and
third-party licensing for any further redistribution or deployed modified service.
