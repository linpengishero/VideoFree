# MiniMax H3 Local Model Skill

The target is the local open-weight MiniMax H3 workflow in ComfyUI. There is no hosted Context-IR stage, so when ready you must produce the complete English structured prompt required by the selected mode.

## Model limits

- Gateway duration: use the user's exact selection from 1 to 15 seconds. This local rule overrides any older 4-second minimum stated in the upstream prompt-writing snapshot.
- Frame rate: 24 FPS.
- Reference mode supports at most 9 pictures, 3 videos, and 3 audio clips.
- Reference videos total at most 15 seconds. Reference audio total at most 15 seconds.
- Mixed reference inputs total at most 12 files.
- Audio cannot be the only reference input.
- Exact dialogue stays in its original language and uses `<d>[Chinese] ...</d>` or the appropriate language tag.

## Production rules

- Establish the essential subjects and situation early enough for the requested action to read, without a fixed opening-time quota.
- Treat each request as one user-timed clip for later external editing. Follow the approved camera structure and shot plan. Shot count is chosen from the script's dramatic beats, dialogue ownership, action readability, exact duration and generation reliability, never from a fixed duration table. Every cut must add necessary information and every shot must have enough screen time to remain legible.
- Lock the visual style explicitly. Infer it from references when possible; otherwise default to live-action cinematic.
- Distinguish camera movement from a shot cut. Use clear terms such as Push In, Pull Out, Pan, Tilt, Tracking Shot, Arc Shot, Static Shot, or POV.
- Separate diegetic environment/action/nonverbal sound into `overall_soundscape`.
- Put audience-only music in `non_diegetic_music`; use `N/A` when it is unnecessary.
- Background music requires the explicit user choice carried in `audio_plan.background_music.choice`; genre or emotion alone never authorizes it.
- Express subject speed with concrete movement and consequences. Preserve user-supplied measurable speed anchors and approved producer-proposed local speed anchors; do not invent additional numbers in later stages. Ordinary motion needs no numeric cue. Keep subject speed separate from camera and playback speed.
- Never manufacture reference relationships. Map every asset to an explicit purpose.
- For `non_diegetic_music`, never use emotion words such as tense, sad, epic, or hopeful; describe only instruments, tempo, intensity, and arrangement. Use `N/A` when no audience-only music is requested.

The final prompt must obey the exact field order required by the active mode skill.
