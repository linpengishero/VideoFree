# ACE-Step Background Mode

Create one complete, directly executable English background-music prompt in `optimized_prompt`, with a faithful Chinese review version in `optimized_prompt_zh`.

The prompt should describe:

- the score's narrative or editing function;
- genre and period character;
- principal and supporting instruments;
- groove and rhythmic character, without duplicating numeric metadata;
- a time-aware structure across the requested duration;
- dynamics, transitions, climax placement, and ending;
- production texture and any important exclusions.

Use the requested duration as a hard arrangement boundary. For short cues, avoid long introductions and reach the musical idea immediately. Keep all lyrics and vocal content absent.

When ready, include these model values in `generation_payload`:

```json
{
  "capability_id": "music.ace_step.background",
  "music_model": "ace_step",
  "music_bpm": 100,
  "music_key": "C minor",
  "music_timesignature": "4",
  "lyrics": "[Instrumental]"
}
```

Choose `music_bpm`, `music_key`, and `music_timesignature` from explicit intent or conservative musical inference. Valid meter values are `2`, `3`, `4`, or `6`. Keep these values out of the natural-language caption. The JSON values above illustrate the required shape and are not defaults that must be copied.
