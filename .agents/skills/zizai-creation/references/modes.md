# Media roles

Always use the `input_roles` returned by the selected capability.

- `first_last_frame`: `first_frame`, then `last_frame`
- `image_to_video`: `first_frame`
- Qwen `storyboard_4`: `scene`, `character_a`, `character_b`
- Krea2 `storyboard_4`: `context`, `subject`
- GPT-Image image-to-image and storyboard modes: repeat `reference` in upload order; no semantic role mapping is required.
- GPT-Image character mode: one `reference` image; scene mode: 0-8 optional
  `reference` images, or no image for text-to-image scene generation.
- `multi_reference`: `subject_1`, `subject_2`, `subject_3`
- General reference modes: use `reference`; the submitted order is preserved.

The gateway converts ratios and named resolutions to legal workflow dimensions,
binds assets, chooses the registered workflow and output nodes, and stores the
exact task inputs. Do not reproduce those details in the client.

Both local `storyboard_4` modes additionally require four nonempty strings in
`settings.shots`. Roles describe reference-image meaning; shots describe the
four output panels. They are separate requirements.
