// Plugin catalog shared by the plugins page and home page.
// Descriptions mirror each plugin's README / INSTALL.md in the repository.

export const plugins = [
  {
    group: { zh: '图像', en: 'Image' },
    items: [
      {
        id: 'krea2',
        name: { zh: 'Krea2 生图', en: 'Krea2 Image' },
        kind: 'local',
        desc: {
          zh: 'Krea 2 图片生成：文生图、人物四视图、分镜与超清动作，内置风格清单与预览图。',
          en: 'Krea 2 image generation: text-to-image, character turnarounds, storyboards, and hi-res actions with a built-in style catalog.',
        },
      },
      {
        id: 'qwen-image',
        name: { zh: 'Qwen Image 2.1 生图', en: 'Qwen Image 2.1' },
        kind: 'local',
        desc: {
          zh: 'Qwen Image 2.1 文生图与图生图：人物、场景与分镜模式，风格提示词随插件分发。',
          en: 'Qwen Image 2.1 text-to-image and image-to-image: character, scene, and storyboard modes with bundled style prompts.',
        },
      },
      {
        id: 'gpt-image',
        name: { zh: 'GPT-Image 云端生图', en: 'GPT-Image (cloud)' },
        kind: 'cloud',
        desc: {
          zh: '通过 GrisAI 云端接口运行 GPT-Image，无本地模型；在插件设置中配置 API Key。',
          en: 'GPT-Image through the GrisAI cloud API — no local models; configure an API key in plugin settings.',
        },
      },
    ],
  },
  {
    group: { zh: '视频', en: 'Video' },
    items: [
      {
        id: 'minimax-h3',
        name: { zh: 'MiniMax H3 视频', en: 'MiniMax H3 Video' },
        kind: 'local',
        desc: {
          zh: '文生视频、图生视频、首尾帧与参考生成，支持二采与 LTX 超清档位；导演协作可把大白话编译成 H3 执行稿。',
          en: 'Text-to-video, image-to-video, first/last-frame, and reference generation with second takes and LTX refine; director collaboration compiles plain language into H3 execution prompts.',
        },
      },
      {
        id: 'ltx-2.5',
        name: { zh: 'LTX 2.5 视频', en: 'LTX 2.5 Video' },
        kind: 'local',
        desc: {
          zh: 'Lightricks LTX-2.5 文生/图生视频，带音频模式、空间超清与多参考 LoRA。',
          en: 'Lightricks LTX-2.5 text/image-to-video with audio mode, spatial upscaling, and multi-reference LoRAs.',
        },
      },
    ],
  },
  {
    group: { zh: '声音与音乐', en: 'Speech & Music' },
    items: [
      {
        id: 'cosyvoice3',
        name: { zh: 'CosyVoice3 语音', en: 'CosyVoice3 Speech' },
        kind: 'local',
        desc: {
          zh: 'Fun-CosyVoice3-0.5B 指令合成与零样本克隆，预设音色随插件分发。',
          en: 'Fun-CosyVoice3-0.5B instruct synthesis and zero-shot cloning with bundled preset voices.',
        },
      },
      {
        id: 'qwen-tts',
        name: { zh: 'Qwen3-TTS 语音', en: 'Qwen3-TTS Speech' },
        kind: 'local',
        desc: {
          zh: 'Qwen3-TTS 声音设计、基础合成与音色克隆，模型由节点自动下载。',
          en: 'Qwen3-TTS voice design, base synthesis, and voice cloning; models auto-download via the node.',
        },
      },
      {
        id: 'ace-step',
        name: { zh: 'ACE-Step 1.5 音乐', en: 'ACE-Step 1.5 Music' },
        kind: 'local',
        desc: {
          zh: 'ACE-Step v1.5 turbo 音乐生成，仅需 ComfyUI 核心节点。',
          en: 'ACE-Step v1.5 turbo music generation using ComfyUI core nodes only.',
        },
      },
      {
        id: 'minimax-music',
        name: { zh: 'MiniMax Music 3', en: 'MiniMax Music 3' },
        kind: 'local',
        desc: {
          zh: 'MiniMax-Music3 创作模式与预设模式音乐生成。',
          en: 'MiniMax-Music3 generation in composition and preset modes.',
        },
      },
    ],
  },
  {
    group: { zh: '后期与成片', en: 'Post & Editing' },
    items: [
      {
        id: 'video-post',
        name: { zh: '视频后期处理', en: 'Video Post-processing' },
        kind: 'local',
        desc: {
          zh: 'RIFE 插帧与 LTX 超清、去模糊等资源动作，作用于已生成的素材。',
          en: 'RIFE frame interpolation plus LTX upscale and deblur resource actions on generated media.',
        },
      },
      {
        id: 'film-studio',
        name: { zh: '剪辑 film-studio', en: 'Editor film-studio' },
        kind: 'local',
        desc: {
          zh: '应用插件：六阶段成片流水线、FFmpeg 时间线引擎、自动字幕与波形混音；需系统安装 FFmpeg。',
          en: 'Application plugin: six-stage final-cut pipeline, FFmpeg timeline engine, auto subtitles and waveform mixing; needs system FFmpeg.',
        },
      },
      {
        id: 'image-split',
        name: { zh: '图片分割', en: 'Image Split' },
        kind: 'tool',
        desc: {
          zh: '原生执行器完成图片网格分割（四宫格、六宫格），无模型依赖。',
          en: 'Native image grid splitting (4/6 panels) with no model dependencies.',
        },
      },
    ],
  },
  {
    group: { zh: '项目工具', en: 'Project Tools' },
    items: [
      {
        id: 'project-archive',
        name: { zh: '创作档案', en: 'Project Archive' },
        kind: 'tool',
        desc: {
          zh: '在项目或分类中管理故事设定、本集信息、剧本定稿与分镜记录。',
          en: 'Manage story bible, episode info, final scripts, and shot records per project or category.',
        },
      },
      {
        id: 'ai-project-progress',
        name: { zh: 'AI 制作进度', en: 'AI Progress' },
        kind: 'tool',
        desc: {
          zh: 'AI 创建的项目中提供制作进度入口与文档存储。',
          en: 'Production progress entry and document storage for AI-created projects.',
        },
      },
    ],
  },
];
