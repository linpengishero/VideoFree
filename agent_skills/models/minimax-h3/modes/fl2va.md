# FL2VA First-and-Last-Frame Skill

Use this mode when `<Picture 1>` is the exact first frame and `<Picture 2>` is the exact final frame.

Prefer one continuous shot and describe a physically plausible transition between the two frames. Preserve subject identity and scene continuity. Ask when the pictures appear unrelated or when their intended order is ambiguous.

The ready prompt must begin and end with these alignment constraints, adapted to the selected duration:

For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
For the target video, at the final frame of the target video, <Picture 2> is fully referenced.

Then use:

integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
