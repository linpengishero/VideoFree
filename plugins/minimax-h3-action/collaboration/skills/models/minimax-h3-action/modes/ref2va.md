# Ref2VA Full-Reference Skill

Use this mode when pictures, videos, or audio are semantic references for identity, appearance, environment, visual style, motion, voice timbre, sound, or music.

## Clarification rules

- Assign every supplied asset a stable label based on connection order: `<Picture 1..9>`, `<Video 1..3>`, `<Audio 1..3>`.
- Vision can identify what a picture contains, but not the user's intended use. When multiple roles are plausible, propose a mapping and ask for one grouped confirmation.
- Character identity, outfit transfer, scene/style reference, motion imitation, and voice-to-character ownership are critical relationships.
- If dialogue is requested, collect the exact words and bind the speaker to a stable subject ID such as `(S1)`.
- Audio used as a voice reference must identify the speaking subject. Do not assume ownership when multiple people are present.

The ready prompt must use this exact six-section order:

subject_definitions:
<Subject 1> is ...
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary:
...

retention_analysis:
<Subject 1>: fully_preserved - ...
<Picture 1>: reference - ...

detailed_description:
Visual style sentence.
[Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...

Use retention values deliberately: visual relationships may be `fully_preserved`, `partially_preserved`, `attribute_transfer`, or `weak_reference`; audio may be `fully_copy`, `partially_copy`, `reference`, or `weak_reference`.
