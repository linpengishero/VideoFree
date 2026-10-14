# T2VA Text-to-Video Skill

Use this mode when the user supplies text only and no frame or semantic reference assets.

Resolve the subject, action, setting, style, camera, timing, soundscape, and optional music. Ask only when exact dialogue is implied but missing, or when two interpretations would create substantially different videos.

The ready prompt must use this exact structure:

integrated_multimodal_description: [Shot 1] ... [Shot 2] At 00:SS.mmm, the camera cuts to ...

overall_soundscape: ...

non_diegetic_music: ...

Do not emit reference labels in T2VA.
