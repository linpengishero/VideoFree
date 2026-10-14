# Qwen Four Panel Storyboard

Convert the request into exactly four sequential shots arranged as one strict 2x2 grid: two columns and two rows, four equal-sized panels, read left-to-right then top-to-bottom. Each panel contains exactly one shot, one action, one camera intention, and a clear continuity link. Preserve the supplied scene and character references, assign their roles explicitly, and avoid embedding captions or panel labels. Unless the user explicitly requests a stylized look, use realistic cinematic lighting, anatomy, materials, sharp details, clean focus, and high-resolution image quality. Never create an 8-panel layout, nested mini-panels, contact-sheet subdivisions, extra thumbnails, alternate views, or a second grid inside any panel.

Return exactly four complete English entries in optimized_shots, one per panel. Keep optimized_prompt as a short overall storyboard summary.
