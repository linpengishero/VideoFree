# L2VA Last-Frame Skill

Use this mode when one picture is the exact final frame and the model must infer a plausible preceding state.

Treat `<Picture 1>` as the required terminal composition. Design motion and camera behavior that arrive naturally at it. Ask if the image appears intended as a subject reference rather than the final frame.

The ready prompt must begin with:

For the target video, at the final frame of the target video, <Picture 1> is fully referenced.

Then use:

integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
