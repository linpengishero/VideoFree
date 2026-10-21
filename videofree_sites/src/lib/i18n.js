// Site i18n: Chinese is the default locale served at the site root;
// English lives under /en/. This module holds UI chrome strings and
// path helpers shared by every page.

export const locales = ['zh', 'en'];
export const defaultLocale = 'zh';

export const guideOrder = ['install', 'plugin-install', 'plugin-dev', 'mcp', 'narrow-mcp', 'demo-skills', 'skill-dev', 'faq'];

export const ui = {
  zh: {
    siteName: 'VideoFree Studio',
    tagline: '本地 AI 视频创作平台',
    nav: { home: '首页', plugins: '插件', canvas: '无限画布', guide: '教程', download: '下载', license: '许可' },
    github: '代码仓库',
    skip: '跳到主要内容',
    guideNavTitle: '教程',
    guideNav: {
      install: '01 安装部署',
      'plugin-install': '02 插件安装',
      'plugin-dev': '03 插件开发',
      mcp: '04 MCP 接入',
      'narrow-mcp': '05 窄 MCP 封装',
      'demo-skills': '06 演示技能',
      'skill-dev': '07 长视频技能开发',
      faq: '08 常见问题',
    },
    prev: '上一篇',
    next: '下一篇',
    footer: {
      slogan: '让创作更自由，让技术真正落地。',
      copyright: '© 2026 AI老林 · VideoFree Studio',
      license: '源代码基于 AGPL-3.0 发布',
      commercial: '商业授权',
      arsenal: 'AI军火库',
    },
  },
  en: {
    siteName: 'VideoFree Studio',
    tagline: 'Local AI Video Creation Platform',
    nav: { home: 'Home', plugins: 'Plugins', canvas: 'Canvas', guide: 'Docs', download: 'Download', license: 'License' },
    github: 'GitHub',
    skip: 'Skip to main content',
    guideNavTitle: 'Docs',
    guideNav: {
      install: '01 Installation',
      'plugin-install': '02 Install Plugins',
      'plugin-dev': '03 Build Plugins',
      mcp: '04 MCP Setup',
      'narrow-mcp': '05 Narrow MCP',
      'demo-skills': '06 Demo Skills',
      'skill-dev': '07 Long-Video Skill Dev',
      faq: '08 FAQ',
    },
    prev: 'Previous',
    next: 'Next',
    footer: {
      slogan: 'Freer creation. Technology that actually ships.',
      copyright: '© 2026 AI老林 · VideoFree Studio',
      license: 'Source code released under AGPL-3.0',
      commercial: 'Commercial License',
      arsenal: 'AI Arsenal',
    },
  },
};

export function t(lang) {
  return ui[lang] ?? ui[defaultLocale];
}

/** Path of a site page in the given locale. `page` is one of the logical keys below. */
export function path(lang, page = 'home', slug) {
  const prefix = lang === 'en' ? '/en' : '';
  switch (page) {
    case 'home': return `${prefix}/`;
    case 'plugins': return `${prefix}/plugins/`;
    case 'canvas': return `${prefix}/canvas/`;
    case 'download': return `${prefix}/download/`;
    case 'license': return `${prefix}/license/`;
    case 'guide': return `${prefix}/guide/${slug ?? 'install'}/`;
    default: return `${prefix}/`;
  }
}

/** Map a built URL back to the same page in another locale (for the language switch). */
export function switchPath(currentPath, targetLang) {
  const p = currentPath.replace(/index\.html$/, '');
  const enPrefix = '/en';
  const zhPath = p.startsWith(enPrefix) ? (p.slice(enPrefix.length) || '/') : p;
  const target = targetLang === 'en' ? (enPrefix + (zhPath === '/' ? '/' : zhPath)) : zhPath;
  return target || '/';
}
