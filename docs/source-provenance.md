# VideoFree Studio Source Provenance and Release Evidence

**English** · [中文](#中文说明)

## Scope and Source

VideoFree Studio is an independently maintained personal project. Its public source and
history are available at:

- https://github.com/linpengishero/VideoFreeStudio
- https://gitee.com/heroofgod_admin/videofreestudio

See [LICENSE](../LICENSE), [NOTICE](../NOTICE), the
[commercial licensing notice](../COMMERCIAL_LICENSE.md), and
[third-party notices](../THIRD_PARTY_NOTICES.md). This document records maintenance
practices; it does not change those licenses, grant commercial rights, prohibit
lawful rebranding, or impose additional restrictions on AGPL recipients.

Source markers and matching hashes can support provenance investigation. They do
not prevent removal, prove infringement on their own, or establish ownership of
third-party material. There is no telemetry, license check, hidden callback, or
remote-disable mechanism added by this documentation change.

## Attribution Practice

- Preserve applicable copyright and license notices when copying or modifying
  covered files, as required by their licenses. Do not replace another author's
  attribution with VideoFree Studio attribution.
- For future file-header work, check each file's authorship, imported portions,
  and existing license first. Use the actual rights holder and an SPDX identifier
  matching the license grant; do not guess between `AGPL-3.0-only` and
  `AGPL-3.0-or-later`. A repository license text alone is not a file-by-file rights
  audit.
- The legal identity of the individual licensor must be recorded in signed
  commercial contracts. Do not invent a company or treat a project name as proof
  of ownership. Do not publish identity documents or customer information here.
- This change does not insert source-file headers or modify runtime version
  endpoints, UI attribution, builds, or executable code.

## Release Evidence Procedure

For each actual release, the maintainer should:

1. Verify the release in a clean checkout. Commit the complete release inputs and
   record the full Git commit ID. A dirty checkout cannot be identified completely
   by its current HEAD. Do not label an incomplete or documentation-only commit as
   a tested product release.
2. Create an annotated release tag after verification; use a signed tag when a
   configured signing key is available. Never silently move an existing published
   tag. Publish the same release commit and tag to both repositories.
3. Build the final distribution, then calculate SHA-256 for each exact downloadable
   archive. Record filename, size, SHA-256, version, full commit ID, tag, build and
   verification commands, results, and UTC release time in the release notes.
4. Preserve the exact published archives, release notes, test results, notices, and
   checksum records outside the development checkout. Git archives or platform
   generated ZIP files may differ from installation packages; identify each
   artifact separately. Never include `.env`, credentials, customer files, or
   project data in public evidence.
5. For important versions, optionally obtain an independent trusted timestamp or
   appropriate legal evidence preservation. Git dates and self-generated hashes
   alone do not prove the date of creation or legal ownership.

Read-only examples, with placeholders replaced by actual release values:

```powershell
git status --short
git rev-parse HEAD
git show --no-patch --format=fuller <release-tag>
Get-FileHash -Algorithm SHA256 -LiteralPath '<release-archive>'
```

On Linux, use `sha256sum <release-archive>` for the archive checksum. Do not create
a new release tag just to add this documentation. This change does not create a
product release, sign a tag, or obtain an independent timestamp.

## Commercial Delivery Record

When delivering to a paying customer, keep a private record with:

- A unique delivery identifier and the signed contract reference.
- Licensor and licensee legal identities, authorized uses, white-label rights,
  deployment and distribution limits, term, support scope, and third-party exclusions.
- Exact source commit, package filenames, SHA-256 checksums, delivery date, and
  customer acceptance record.
- An inventory of licensed files and evidence that the licensor owns or can
  commercially relicense them; retain third-party notices separately.

Provide the customer with an agreed delivery manifest identifying the package and
contract. Keep customer-specific records outside the public repository. An optional
delivery identifier is a disclosed tracking aid, not a secret watermark, activation
system, ownership claim, or replacement for a signed agreement. No delivery record
is created until there is an actual customer and agreement.

## Contributor Authorization

Before merging outside contributions intended for commercial relicensing, the
maintainer must verify the contributor's authority and obtain the completed
[Contributor License Agreement](contributor-license-agreement.md). Record its scope,
effective date, and corresponding pull request/commit privately. Merely submitting
a pull request or reading the template does not sign the agreement. Existing
contributions require a separate rights review; the template is not retroactive.
If proprietary relicensing rights are unavailable, exclude that material from the
commercial grant or obtain permission first. Do not claim that an unsigned template
has cleared third-party rights. Obtain qualified legal review for binding contracts.

---

# 中文说明

## 范围与来源

VideoFree Studio 是个人维护的独立项目，公开源码和历史位于：

- https://github.com/linpengishero/VideoFreeStudio
- https://gitee.com/heroofgod_admin/videofreestudio

适用文件为 [LICENSE](../LICENSE)、[NOTICE](../NOTICE)、
[商业授权说明](../COMMERCIAL_LICENSE_ZH.md)及[第三方声明](../THIRD_PARTY_NOTICES_ZH.md)。
本文件只规定维护和留证流程，不修改许可证、不授予商业授权、不禁止合法改名，也不对
AGPL 接收者附加限制。

来源标识和哈希可辅助调查，但不能防止移除、单独证明侵权或证明第三方内容属于作者。
本次仅修改文档，没有增加遥测、授权校验、隐藏回连或远程停用机制。

## 版权标识规范

- 复制、修改相关文件时，按适用许可证保留必要的版权和许可声明，不把第三方署名替换成 VideoFree Studio。
- 后续补源码版权头前，逐文件核查作者、引用代码和既有许可。使用真实权利人和与许可授权一致的
  SPDX 标识，不擅自选择 `AGPL-3.0-only` 或 `AGPL-3.0-or-later`。
  根目录的许可证文本不能替代逐文件权属审计。
- 商业合同写明个人许可方的法定身份，不虚构公司，不把项目名当作权属证明；身份证明和客户资料不公开入库。
- 本次不批量插入源码版权头，不修改版本接口、界面署名、构建流程或可执行代码。

## 发布留证流程

1. 真正发布前，在干净检出中验证，提交完整发布输入并记录完整 Git 提交号。
   脏工作区不能只用 HEAD 标识；不把不完整或仅文档提交标为已验收的产品版本。
2. 验证后创建附注发布标签，已有签名密钥时优先签名；不偷偷移动已公开标签。
   GitHub 与 Gitee 发布相同提交和标签。
3. 最终发行包生成后，对每个实际下载文件计算 SHA-256。在发布说明记录文件名、大小、哈希、
   版本、完整提交号、标签、构建及验证命令、结果和 UTC 发布时间。
4. 将实际发行包、发布说明、测试结果、版权声明和校验记录保存在开发工作区之外。
   平台自动生成的源码 ZIP 与安装包分别记录；不公开 `.env`、密钥、客户文件或项目数据。
5. 重要版本可办理独立可信时间戳或适当的法律证据保全。Git 日期与自行计算的哈希不能单独证明
   创作时间或法律权属。

上方英文部分提供只读核查命令；用真实标签和发行包路径替换占位符。
不要为了增加本文件就创建产品发布标签。本次未创建产品发布、签名标签或办理独立时间戳。

## 商业交付记录

有真实客户并签署协议后，在公开仓库之外保存唯一交付编号、合同编号、双方主体、授权范围、
改名权利、部署及分发数量、期限、支持范围和第三方排除项。记录源码提交、交付文件名及哈希、
日期和验收凭证，并保留授权文件清单及自有或可再许可的权利证据。

向客户提供双方约定的交付清单。交付编号应明确告知，只辅助追溯，不是秘密水印、激活系统、
权属证明或合同替代品；没有实际客户和协议时不虚构记录。

## 贡献者授权流程

拟用于商业再许可的外部贡献，合并前核实提交者的授权资格，签署完整的
[贡献者许可协议](contributor-license-agreement.md)，并私下保存适用范围、生效日期及对应 PR/提交。
提交 PR 或阅读模板不等于签署。既有贡献单独核查，模板不会自动追溯。
无法取得闭源再许可权的内容，应先取得许可或排除在商业授权范围外。
不得宣称未签署的模板已完成权利清理；正式合同应请合格法律专业人士审阅。
