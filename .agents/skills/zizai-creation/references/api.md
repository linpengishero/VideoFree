# API contract

The helper prints JSON and exits nonzero on HTTP errors.
All HTTP routes begin with `/api/v2`; for example, health is
`http://127.0.0.1:8765/api/v2/health`, not `/v2/health`.

```powershell
python scripts/zizai_api.py health
python scripts/zizai_api.py projects
python scripts/zizai_api.py create-project "武侠短片" --description "武侠动作短片" --content-summary "男女剑客在竹林决斗"
python scripts/zizai_api.py select-project PROJECT_ID

`create-project` returns the new `project_id` but does not select it in the
workbench. Add that ID to the JSON body of every later `create` or
`collaborate` request as `project_id` to keep an AI's outputs isolated. Without
the field, the request uses the active project as before.
python scripts/zizai_api.py current-project
python scripts/zizai_api.py capabilities --kind video
python scripts/zizai_api.py capabilities --kind image --operation postprocess
python scripts/zizai_api.py upload C:\media\person.png
python scripts/zizai_api.py voices
python scripts/zizai_api.py music styles
python scripts/zizai_api.py image-styles
python scripts/zizai_api.py create request.json --idempotency-key task-001
python scripts/zizai_api.py collaborate collaboration.json  # legacy compatibility
python scripts/zizai_api.py reply COLLAB_ID "第一张是主角，第二张是反派"
python scripts/zizai_api.py collaboration COLLAB_ID
python scripts/zizai_api.py collaboration-progress COLLAB_ID
python scripts/zizai_api.py confirm COLLAB_ID 2 --execution-prompt-en-file final-en.txt --confirmed-prompt-zh-file final-zh.txt --idempotency-key task-002  # legacy compatibility
python scripts/zizai_api.py wait JOB_ID --timeout 60
python scripts/zizai_api.py artifacts JOB_ID
python scripts/zizai_api.py inputs JOB_ID
python scripts/zizai_api.py download JOB_ID C:\\media\\output
python scripts/zizai_api.py actions JOB_ID
python scripts/zizai_api.py run-action JOB_ID upscale
python scripts/zizai_api.py regenerate JOB_ID changes.json
python scripts/zizai_api.py cancel JOB_ID
Use the workbench settings UI for reusable preset configuration; the AI client
does not mutate preset catalogs.
```

Each `wait` call accepts `1-120` seconds. A timeout does not cancel or fail the
job; query the same job again. Uploaded IDs remain reusable until the upload
cache expires, and using one in a task does not consume it.

Project selection is workspace state, not a field repeated in each generation
request. The helper sends a stable `X-Workspace-Id`; override it with
`ZIZAI_WORKSPACE_ID` when several AI clients share the gateway. A task captures
its project at submission, while derived tasks inherit the parent project.
Completed media is stored under `data/projects/<project>/` by media type.

Directly split an uploaded four-panel grid into four image artifacts:

```json
{
  "capability_id": "image.split",
  "inputs": [
    {"type": "image", "upload_id": "UPLOAD_ID", "role": "reference"}
  ]
}
```

Submit this request with `create`, then use `wait` and `artifacts`. This direct
path accepts an image produced by any external generator; it does not require
an existing gateway job. To split a gateway job artifact, `actions JOB_ID`
followed by `run-action JOB_ID split` remains available.

For a six-panel 3x2 grid, use `capability_id: "image.split_6"` with the same
single image input. It returns six artifacts in row-major reading order. For a
completed gateway job, run the `split_6` post-processing action.

Create request:

```json
{
  "capability_id": "video.reference",
  "prompt": "Two characters run through rain at night.",
  "inputs": [
    {"type": "image", "upload_id": "UPLOAD_ID", "role": "reference"}
  ],
  "settings": {
    "ratio": "16:9",
    "resolution": "720P",
    "duration": 5,
    "variant": "fast_refine"
  }
}
```

For local `storyboard_4` capabilities, send exactly four nonempty descriptions
in `settings.shots`. The compatibility top-level `shots` field is also accepted,
but `settings.shots` is canonical. Intelligent collaboration supplies its
`optimized_shots` automatically when the result is confirmed.

Qwen example:

```json
{
  "capability_id": "image.qwen.storyboard_4",
  "prompt": "两名角色在雨夜车站相遇并发生冲突",
  "inputs": [
    {"type": "image", "upload_id": "SCENE_UPLOAD", "role": "scene"},
    {"type": "image", "upload_id": "CHARACTER_A_UPLOAD", "role": "character_a"},
    {"type": "image", "upload_id": "CHARACTER_B_UPLOAD", "role": "character_b"}
  ],
  "settings": {
    "ratio": "16:9",
    "resolution": "1K",
    "shots": [
      "雨夜车站全景，两名角色从画面两侧接近",
      "角色 A 停步警觉，视线锁定角色 B",
      "角色 B 抬手阻拦，双方形成紧张对峙",
      "列车灯光扫过，两人隔着雨幕相互凝视"
    ]
  }
}
```

Krea2 uses the same `settings.shots` contract but requires two image roles:
`context` followed by `subject`. Always trust the selected capability's live
`inputs` and `input_roles` response over examples.

Completed job responses expose prompt history as follows:

- `prompt`: exact source prompt submitted by the caller; always use this for a
  direct-generation task.
- `prompt_zh`: confirmed Chinese snapshot produced or supplied through
  collaboration; it may be empty for direct generation.
- `execution_prompt_en`: confirmed executable English snapshot; it may be empty
  for direct generation.

The source prompt is also persisted in the task package. Do not report it as
missing merely because one of the optional bilingual snapshot fields is empty.

GPT-Image capability family:

```text
image.gpt_image.text_to_image
image.gpt_image.image_to_image
image.gpt_image.character
image.gpt_image.scene
image.gpt_image.storyboard_4
image.gpt_image.storyboard_6
```

These are gateway-native cloud capabilities. They use the same persistent job,
artifact, regeneration, cancellation, and deletion APIs as ComfyUI-backed
capabilities, but do not require ComfyUI to be running.

Use the limits returned by `/api/v2/capabilities`. Image-to-image accepts 1-8
ordered references, character requires exactly one, scene accepts 0-8 optional
references, and either grid mode accepts 0-8. Submit generic references with role `reference`; fixed layout
rules are applied by the gateway and are not supplied by the calling AI.
The capability `models` field advertises the allowed native GPT-Image versions.
Set `settings.native_model` to one of those exact values; currently
`gpt-image-2` and `gpt-image-2.5` are available. Omit it to use the capability
default. Never invent an unadvertised provider model id.

GPT-Image ratios are mapped to the provider's supported aspect ratios. The
provider controls final pixel dimensions, so a requested `480P` does not
guarantee an exact 480-pixel edge. Read completed artifact metadata for the
actual dimensions.

## Intelligent collaboration

The preferred AI-facing contract is the single generation endpoint:

```json
{
  "capability_id": "video.reference",
  "prompt": "两名角色在雨夜街道持续交战，不增加剧情",
  "prompt_processing": "compile",
  "inputs": [],
  "settings": {"ratio": "16:9", "resolution": "720P", "duration": 8}
}
```

Use `direct` for an already executable prompt, `compile` for faithful model
formatting, and `director` when the request needs clarification or production
planning. If the gateway needs an answer, it returns a session/collaboration
identifier and questions. Continue through the same generation endpoint:

```json
{
  "session_id": "collab-xxxx",
  "answer": "Picture 1 是男主，Picture 2 是女主"
}
```

The gateway retains the original prompt, references, settings, project, and
conversation. Never call a separate translation endpoint and then submit the
translation as a new direct job.

The following collaboration routes are legacy compatibility routes. New AI
clients should use `/api/v2/generations` with `prompt_processing` and
`session_id`; use these routes only when integrating an older client:

- `POST /api/v2/collaborations`
- `GET /api/v2/collaborations/{id}`
- `POST /api/v2/collaborations/{id}/messages`
- `GET /api/v2/collaborations/{id}/progress`
- `POST /api/v2/collaborations/{id}/confirm`

AI clients cannot delete collaboration records. Cancel an active collaboration
through its supported cancel operation when necessary, then keep the record
for auditability.

Create a collaboration with the exact `model_id` and `mode_id` returned by the
selected capability. `inputs` and `settings` use the same schema as direct
generation. `prompt` may contain an existing draft and `lyrics` carries music
lyrics. Read `collaboration_modes` from the capability. MiniMax H3 advertises:

- `quick`: faithfully convert the supplied request into the active H3 format;
  no script development, shot redesign, questions, or AI final review.
- `director`: run the full producer, scene, shot, H3 compiler, and review
  pipeline; use this for incomplete or creatively underdeveloped requests.

Other collaborative models currently advertise only `director`. Omitting the
field defaults to `director` for backward compatibility.

```json
{
  "capability_id": "video.reference",
  "model_id": "minimax-h3",
  "mode_id": "reference",
  "collaboration_mode": "quick",
  "message": "忠实转换这段要求：两名角色在雨夜街道会合，不增加剧情",
  "inputs": [
    {"type": "image", "upload_id": "UPLOAD_1", "role": "reference"},
    {"type": "image", "upload_id": "UPLOAD_2", "role": "reference"}
  ],
  "settings": {"ratio": "16:9", "resolution": "720P", "duration": 8}
}
```

The legacy state sequence is `needs_input` (zero or more times), then
`awaiting_confirmation`, then `submitted`. Reply in natural language;
`questions` are hints rather than required answer fields. New clients should
continue a `needs_input` session through `/api/v2/generations` using its
`session_id` and `answer` fields. Legacy clients may confirm the bilingual
execution snapshot through the compatibility endpoint:

```json
{
  "revision": 2,
  "execution_prompt_en": "Final executable prompt...",
  "confirmed_prompt_zh": "对应的最终中文稿……",
  "idempotency_key": "task-002"
}
```

Omit both prompt fields to accept the agent-produced pair unchanged. Supplying
only one returns HTTP 422. A stale revision returns HTTP 409. API V2 collaboration
uses external-review mode: the calling AI is the final reviewer and should also
inspect the optional `review` object. No internal multi-supervisor or automatic
repair loop runs. Confirmation creates the standard generation job automatically.

For regeneration, use the same paired fields whenever changing a bilingual task:

```json
{
  "execution_prompt_en": "Revised executable prompt...",
  "confirmed_prompt_zh": "对应的修订中文稿……"
}
```

The new revision stores and executes the English version while preserving the
matching Chinese version. The original job is not changed.

MiniMax Music3 song requests use `music.create`, with `lyrics` plus
`music_style_id`, `singer_id`, and `voice_texture_id`. ACE-Step instrumental
score requests use `music.ace_step.background`, keep `lyrics` empty, and carry
tempo and meter controls in settings:

```json
{
  "capability_id": "music.ace_step.background",
  "prompt": "Tense instrumental pursuit score led by low strings and taiko, immediate pulse, rising intensity, a hard final hit, no vocals.",
  "lyrics": "",
  "inputs": [],
  "settings": {
    "duration": 30,
    "music_bpm": 128,
    "music_key": "D minor",
    "music_timesignature": "4"
  }
}
```

For AI-assisted score design, create a collaboration using the exact advertised
`model_id: "ace-step-1.5"`, `mode_id: "background"`, and
`collaboration_mode: "director"`. Speech preset mode uses `prompt` as spoken
text and `voice_id`.

AI speech generation uses these model-independent endpoints:

- `GET /api/v2/voices` lists `preset_id`, description, and `ready` status.
- `POST /api/v2/tts/preset` with `{ "preset_id": "warm_male", "text": "...", "speed": 1.0 }`; the server selects CosyVoice3 and the fixed preset sample.
- `POST /api/v2/tts/describe` with `{ "voice_description": "温暖自然的成年男声", "text": "...", "speed": 1.0 }`; the server selects Qwen3-TTS VoiceDesign.
- `POST /api/v2/tts/clone` with `{ "reference_upload_id": "<upload_id>", "text": "...", "speed": 1.0 }`; upload exactly one reference audio through `/api/v2/uploads` first, then the server selects CosyVoice3 cloning.

`speed` accepts `0.5-2.0`. For rough planning, normal Mandarin is about
`4-5 Chinese characters per second`; estimate duration as non-whitespace
character count divided by `4.5 * speed`. Punctuation, pauses, numbers, and
emotion can change the actual duration.

Do not pass model names, workflow names, or speaker presets to these AI-facing endpoints. Voice cloning accepts only the reusable `upload_id` returned by the upload endpoint, never a local path or raw workflow input.

Voice presets are managed only by the workbench's internal settings UI. The
AI-facing v2 API is read-only for voice presets: it exposes the catalog and
speech generation, but no create, update, delete, or sample-regeneration route.
Do not attempt to mutate voice presets through the AI API.

## Regression checks

When validating this API revision, cover these behaviors without deleting user
data:

1. Reuse one `upload_id` in two different generation requests.
2. Submit Qwen and Krea2 `storyboard_4` with four `settings.shots` entries.
3. Confirm a storyboard collaboration and verify its generated job receives the
   four optimized shots.
4. Run `image.split` directly on one uploaded grid and verify four artifacts.
5. Query a direct-generation job and verify its exact source text is returned in
   `prompt` even when bilingual fields are empty.
6. Use a UTF-8 BOM request JSON file and verify the helper accepts it.
