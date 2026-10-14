---
name: zizai-creation
description: Use the local videofree gateway to discover AI media capabilities and read presets, upload references, generate images/videos/speech/music, wait for jobs, regenerate, or run supported post-processing. Use when the user asks to create media through videofree; do not modify presets or call ComfyUI workflows directly.
---

# videofree

This skill supports two connection styles. Keep the direct REST client below
for scripts and deterministic media operations. For an AI client that supports
MCP, use the LAN MCP endpoint described in
[references/mcp.md](references/mcp.md); MCP is an additional adapter and does
not replace this REST capability.

For a standalone document to share with another AI or its administrator, use
[MCP installation and usage](references/mcp-install.md).

MCP also supports the unified generation contract, read-only presets, all three
speech operations (including cloning and speed), regeneration and advertised
job actions. Its tools delegate to the same v2 API; see the MCP reference for
tool names. Never automatically confirm a collaboration or mutate presets.

Use `scripts/zizai_api.py` for gateway operations. The default URL is
`http://127.0.0.1:8765`; override it with `ZIZAI_API_URL`. If the gateway uses a
token, set `ZIZAI_API_TOKEN`. `ZIZAI_API_URL` is the gateway origin, not an API
path; both `http://127.0.0.1:8765` and a value ending in `/api/v2` are accepted.

## Workflow

Before generation, run `projects` and either use the active project or create a
dedicated project. `create-project` returns a `project_id` and does not change
the workbench's active project. For AI isolation, keep that ID and include it
in every later generation or collaboration request as `project_id`. If
`project_id` is omitted, the gateway preserves the old behavior and files the
request under the active project for that AI workspace. An invalid or archived
project ID is rejected; it never silently falls back to another project. If no
project is selected, the gateway uses `未归档项目`.

1. Run `health`, then `capabilities`. For an uploaded file that needs direct
   post-processing, also run `capabilities --operation postprocess`. Never guess
   a model, mode, variant, input count, ratio, or resolution.
2. Query the relevant presets before generation:
   - tts: `voices` (capability filtering uses `--kind tts`, not `speech`). AI speech uses three dedicated operations: `POST /api/v2/tts/preset` with `preset_id`, `text`, and optional `speed` (server selects CosyVoice3); `POST /api/v2/tts/describe` with `voice_description`, `text`, and optional `speed` (server selects Qwen3-TTS); or `POST /api/v2/tts/clone` with an uploaded audio's `reference_upload_id`, `text`, and optional `speed` (server selects CosyVoice3). `speed` accepts `0.5-2.0`; normal Mandarin speech is roughly `4-5 Chinese characters per second`, so estimate duration as character count divided by `4.5 * speed`. Do not send model or workflow parameters; use a preset only when its `ready` field is true.
   - music: `music styles`, `music singers`, and `music voice-textures`
   - images: `image-styles`
   For cloud GPT-Image, select one of the advertised `image.gpt_image.*`
   capabilities. GPT-Image is a gateway-native cloud ability and does not
   require ComfyUI. The gateway applies its fixed character, scene, and grid
   rules; callers never invoke prompt-packaging nodes. Choose only a native
   model advertised in the capability `models` list and send it as
   `settings.native_model`.
   For music, choose by intent: use `music.create` with MiniMax Music3 for
   songs, singers, or supplied lyrics; use `music.ace_step.background` for an
   instrumental background score. ACE-Step does not use singer or voice-texture
   presets and its `lyrics` value must remain empty.
3. Upload every local reference with `upload`. Use only returned `upload_id`
   values in generation requests. An upload is reusable until cache expiry;
   successful submission does not consume or invalidate its `upload_id`.
4. Use one generation submission path. `create` executes the prompt directly;
   to let the gateway inspect and compile it, include
   `prompt_processing: "compile"` (faithful model formatting) or
   `prompt_processing: "director"` (full clarification and direction). If the
   response returns `status: "needs_input"` or a collaboration session, send
   the user's answer back to the same `create` operation with its
   `session_id` and `answer`; do not start a second generation request. The
   older `collaborate` endpoint remains for compatibility only.
5. Poll the returned session when processing is requested. If it reaches
   `needs_input`, answer through the same `generations` contract. If it reaches
   `awaiting_confirmation`, show the generated bilingual plan to the user and
   only continue after explicit approval; do not submit a second direct job.
6. Do not send workflow filenames, ComfyUI node IDs, raw width/height, or model
   paths. Use `wait` until status is `completed`, `failed`, or `cancelled`. Each
   wait call accepts at most 120 seconds. A timeout means the job is still
   active, not failed; call `wait` again.
7. Return every artifact. Use `actions` and `run-action` to process an existing
   job artifact. To process an external file directly, upload it and call
   `create` with the advertised post-processing capability. For a four-panel
   grid image, use the gateway-native `image.split` with exactly one image input;
   it does not require a ComfyUI split node. Use `regenerate` to create a new
   revision without deleting the original. When changing an existing bilingual
   execution prompt, send both `execution_prompt_en` and its matching
   `confirmed_prompt_zh`; never update only one snapshot. Direct generation
   never silently rewrites the caller's prompt.
   For a six-panel 3x2 grid image, use `image.split_6` with exactly one image
   input; it returns six independent image artifacts in row-major order.

Use a unique `--idempotency-key` for create requests so retries do not create
duplicate jobs. Never cancel, delete, create, edit, or regenerate a reusable
preset. Voice presets are workbench-owned configuration and the AI-facing API
is intentionally read-only for them.

CLI equivalents are `voices`, `speech-preset <preset_id> <text> [--speed 1.0]`,
`speech-describe <voice_description> <text> [--speed 1.0]`, and
`speech-clone <reference_audio> <text> [--speed 1.0]`. The clone command uploads the
reference audio before submitting the speech job. The generic `create` command
remains for compatibility, but AI callers should use the dedicated speech
operations so model selection stays server-side.

The gateway owns the project media library under `data/projects/<project>/`.
Every completed output is published into `images`, `videos`, `audio`, or
`music`, including every output produced by four-panel and six-panel splitting.
Do not scan or synchronize the ComfyUI output directory for project assets.

For local Qwen or Krea2 `storyboard_4`, always send exactly four nonempty shot
descriptions in `settings.shots`. A combined story in `prompt` does not replace
that array. Collaboration confirmation carries agent-produced shots into the
generation automatically.

Job prompt fields have distinct meanings: `prompt` is the exact source prompt
submitted by the caller, `prompt_zh` is the confirmed Chinese snapshot when one
exists, and `execution_prompt_en` is the confirmed executable English snapshot
when one exists. Empty bilingual snapshot fields on a direct-generation job do
not mean the source prompt was lost; read `prompt`.

GPT-Image reference contracts:

- `image.gpt_image.text_to_image`: no reference image.
- `image.gpt_image.image_to_image`: 1-8 ordered reference images.
- `image.gpt_image.character`: exactly 1 character reference.
- `image.gpt_image.scene`: 0-8 optional scene references; with no reference it
  is text-to-image scene generation.
- `image.gpt_image.storyboard_4` and `storyboard_6`: 0-8 ordered references.

ACE-Step background-score contract:

- discover and use `music.ace_step.background` rather than guessing a workflow;
- write `prompt` as a production-ready instrumental score brief covering
  dramatic function, instruments, rhythm, intensity curve, transitions, and
  ending across the requested duration;
- send `lyrics: ""` and set `music_bpm`, `music_key`, and
  `music_timesignature` in `settings`;
- use collaboration mode `director` when the user's scene or story must first
  be translated into a musical plan.

Read [references/api.md](references/api.md) for request shapes and
[references/modes.md](references/modes.md) when selecting media roles.
