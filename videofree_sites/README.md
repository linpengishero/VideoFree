# VideoFree Studio 官网（videofreestudio.com）

VideoFree Studio 官方网站首页与中英双语教程站。默认中文（站点根路径），英文位于 `/en/`。
仅维护本目录内文件，不依赖主仓库其它目录的构建产物；品牌素材已复制到 `public/`。

## 技术栈

- [Astro](https://astro.build) 静态站点（零客户端 JS）
- 教程内容：`src/content/docs/{zh,en}/*.md`，同 slug 成对维护
- 页面文案：`src/components/*Page.astro` 内按 `lang` 取中/英字典
- 品牌样式：`src/styles/global.css`（沿用工作台深绿 + 薄荷绿 + 琥珀色）

## 本地开发

```powershell
npm install
npm run dev      # http://localhost:4321
npm run build    # 输出到 dist/
```

## 部署到 Cloudflare Pages

1. 将本目录推送到独立 GitHub 仓库（或本仓库的 Pages 构建根设为 `videofree_sites`）。
2. Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git。
3. 构建设置：
   - Framework preset: **Astro**
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Node version 环境变量：`NODE_VERSION=22`
4. 绑定自定义域名 `videofreestudio.com`（域名 DNS 接入 Cloudflare 后在 Pages → Custom domains 添加）。
5. `public/_redirects` 与 `public/_headers` 由 Cloudflare Pages 自动生效（语言路径规范化与安全头）。

也可用 wrangler 直接部署构建产物：

```powershell
npm run build
npx wrangler pages deploy dist --project-name videofree-site
```

## 维护约定

- 新增教程：在 `src/content/docs/zh/` 与 `en/` 各建同 slug 文件（frontmatter：`title`、`lead`、`order`），并在 `src/lib/i18n.js` 的 `guideOrder` 与 `guideNav` 中登记，否则不会出现在侧栏和上下篇。
- 备注块语法：段落用 `::note` 开头、`::` 结尾（单段，中间不空行）。
- 模型清单以主仓库各插件 `INSTALL.md` 为唯一事实来源；本站 `models.md` 只是索引，更新插件时同步索引行即可。
