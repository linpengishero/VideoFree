export const musicStyleOptions = [
  {
    value: "pop",
    label: "流行",
    prompt:
      "Contemporary pop with a memorable chorus, polished production, balanced verse-chorus structure, and clear emotional progression.",
  },
  {
    value: "chinese",
    label: "国风",
    prompt:
      "Modern Chinese-style pop blending guzheng, bamboo flute, and cinematic strings with an elegant pentatonic melody.",
  },
  {
    value: "rock",
    label: "摇滚",
    prompt:
      "Modern rock with driving live drums, energetic electric guitars, strong dynamics, and an anthemic chorus.",
  },
  {
    value: "folk",
    label: "民谣",
    prompt:
      "Intimate acoustic folk with natural guitar, restrained percussion, warm storytelling, and an organic live-room feel.",
  },
  {
    value: "rnb",
    label: "R&B",
    prompt:
      "Contemporary R&B with a smooth groove, expressive melodic phrasing, rich harmony, and tasteful atmospheric production.",
  },
  {
    value: "electronic",
    label: "电子",
    prompt:
      "Modern electronic pop with precise synth layers, a controlled dance pulse, evolving texture, and a powerful hook.",
  },
  {
    value: "rap",
    label: "说唱",
    prompt:
      "Modern hip-hop with a confident rhythmic flow, punchy drums, deep bass, clear lyrical delivery, and a strong recurring hook.",
  },
  {
    value: "jazz",
    label: "爵士",
    prompt:
      "Contemporary jazz with expressive piano, upright bass, brushed drums, sophisticated harmony, and relaxed live interplay.",
  },
  {
    value: "cinematic",
    label: "电影感",
    prompt:
      "Cinematic song arrangement with evolving orchestration, emotional strings, deep percussion, and a dramatic narrative arc.",
  },
  {
    value: "healing",
    label: "治愈",
    prompt:
      "Gentle healing pop with soft piano, acoustic textures, subtle percussion, and a calm uplifting emotional tone.",
  },
];

export const singerOptions = [
  {
    value: "female",
    label: "女声",
    prompt:
      "Lead vocal: adult female singer with controlled expression, natural pronunciation, and stable pitch.",
  },
  {
    value: "male",
    label: "男声",
    prompt:
      "Lead vocal: adult male singer with controlled expression, natural pronunciation, and stable pitch.",
  },
];

export const voiceTextureOptions = [
  {
    value: "natural",
    label: "自然",
    prompt:
      "Natural, balanced vocal timbre with minimal affectation and clear diction.",
  },
  {
    value: "smoky",
    label: "烟嗓",
    prompt:
      "A textured smoky voice with tasteful rasp, emotional weight, and clear intelligibility; never harsh or damaged.",
  },
  {
    value: "clear",
    label: "清亮",
    prompt:
      "A bright, clear vocal timbre with clean upper harmonics, agile phrasing, and crisp diction.",
  },
  {
    value: "magnetic",
    label: "磁性",
    prompt:
      "A warm magnetic mid-low voice with rich resonance, confident phrasing, and intimate presence.",
  },
  {
    value: "sweet",
    label: "甜美",
    prompt:
      "A youthful sweet vocal color with a gentle smile, light delivery, and no exaggerated childish tone.",
  },
  {
    value: "deep",
    label: "低沉",
    prompt:
      "A deep, grounded vocal timbre with restrained emotion, full chest resonance, and clear articulation.",
  },
  {
    value: "powerful",
    label: "力量感",
    prompt:
      "A powerful vocal performance with firm breath support, strong projection, and controlled climactic intensity.",
  },
  {
    value: "ethereal",
    label: "空灵",
    prompt:
      "An airy ethereal vocal timbre with soft resonance, spacious phrasing, and a dreamlike but intelligible presence.",
  },
  {
    value: "warm",
    label: "温暖",
    prompt:
      "A warm, gentle vocal timbre with rounded tone, sincere emotion, and close conversational presence.",
  },
];

function promptFor(options, value) {
  return (
    options.find((option) => option.value === value)?.prompt ||
    options[0].prompt
  );
}

export function buildMusicPresetPrompt(style, singer, texture, catalog = {}) {
  const styles = catalog.styles || musicStyleOptions;
  const singers = catalog.singers || singerOptions;
  const textures = catalog.voiceTextures || voiceTextureOptions;
  return [
    promptFor(styles, style),
    promptFor(singers, singer),
    promptFor(textures, texture),
    "Produce a complete song around the supplied lyrics. Keep the lyrics intelligible and preserve their original language and wording.",
  ].join(" ");
}
