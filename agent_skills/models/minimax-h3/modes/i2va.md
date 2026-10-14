# I2VA First-Frame Image-to-Video Skill

Use this mode when one picture is the actual first frame of the generated video, not merely a semantic character or style reference.

`<Picture 1>` must be treated as the exact visual state at 0.00 seconds. Preserve identity, composition, clothing, geometry, lighting continuity, and scene layout unless the user explicitly requests a transformation. Ask if the uploaded picture appears intended as a reusable subject reference rather than the first frame.

The ready prompt must use this exact structure:

For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
