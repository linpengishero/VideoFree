# 开发代理约束

本文件对整个仓库生效。任何自动化开发代理在修改代码前必须先阅读本文件和
`ARCHITECTURE.md`。目标是维持模块化单体结构，避免根目录膨胀、职责穿透和重复实现。

## 不可违反的规则

1. 根目录不得新增临时脚本、测试输出、工作流副本、下载文件或 `*_backup`、`*.bak` 文件。
2. 不得为了单次修改创建新的顶层目录。新增目录前必须证明现有目录无法承载该职责。
3. 不得把业务逻辑写入 HTTP 路由、启动脚本或全局工具模块。
4. 不得创建只有一个调用方的抽象层、接口、工厂或通用工具。
5. 不得保留新旧两套实现。兼容入口只能委托给唯一实现，并注明移除条件。
6. 不得手工修改构建产物、缓存和运行数据；应修改源文件后通过构建或运行流程生成。

## 文件归属

| 内容 | 唯一归属 |
| --- | --- |
| 环境配置、错误、日志、运行时上下文 | `backend/core/` |
| SQLite 数据访问 | `backend/persistence/` |
| ComfyUI、模型供应商和外部服务适配 | `backend/integrations/` |
| generation、collaboration、settings、presets 等业务逻辑 | `backend/modules/<domain>/` |
| HTTP schema、V1/V2 路由和协议转换 | `backend/interfaces/http/` |
| 启动、恢复、worker 和优雅关闭 | `backend/bootstrap.py`、`backend/lifecycle.py` |
| 框架前端组件、状态和样式源文件 | `frontend/src/` |
| 前端静态源资源 | `frontend/public/` |
| 插件工作流、专用编译和协作技能 | `plugins/<plugin-id>/` |
| 应用插件页面、业务逻辑与动作 | `plugins/<plugin-id>/ui/` 及同插件目录，由 `plugin.json.application/actions` 注册 |
| 插件能力、主分类、处理模式注册 | `plugins/<plugin-id>/plugin.json`，唯一注册来源 |
| 导演与能力技能 | `.agents/skills/` 或对应插件的 `collaboration/skills/`；沿用邻近文件的组织方式 |
| 自动化测试与固定测试素材 | `tests/` |
| 运行数据、缓存、任务和生成资源 | `data/`，不得作为源码提交或手工编辑 |
| 前端构建结果 | `static/dist/`，仅由前端构建生成 |

根目录只保留项目入口和仓库级文件，例如 `启动VideoFree.cmd`、`README.md`、
`ARCHITECTURE.md`、`AGENTS.md`、依赖清单和环境变量示例。无法明确归属的文件先不要创建。

## 依赖与实现边界

依赖方向必须保持：

```text
interfaces/http -> modules -> integrations / persistence
                         -> core
bootstrap / lifecycle -> application modules
```

- `ApplicationContext` 是运行期可变状态的唯一容器，禁止新增模块级可变队列、锁或任务表。
- HTTP handler 只负责协议校验、错误映射和调用业务服务。
- 工作流必须放在对应插件目录并注册到该插件的 `plugin.json`，路由不得解析节点或直接读取工作流文件。协议见 `docs/plugin-protocol.md`。
- 新导演技能通过技能文件和注册信息扩展；选择与编排属于 collaboration，不能侵入 generation。
- 共享代码只有在至少两个业务域真实复用时才能抽取；单域帮助函数留在所属模块。
- 优先复用仓库现有实现、Python/浏览器标准能力和已安装依赖，避免为小问题增加依赖。

## 修改流程

1. 先定位行为的唯一所有者，并搜索全部调用方。
2. 检查工作区已有改动，保留用户修改，不覆盖无关内容。
3. 以最少文件修复根因；不要顺手重构无关模块。
4. 新文件创建前，先确认上表中的明确归属和真实调用方。
5. 为非平凡逻辑补充最小可执行测试；修复缺陷时优先添加回归测试。
6. 运行与改动范围匹配的验证，确认没有新增根目录杂项、缓存或备份副本。
7. 交付时说明修改文件、验证结果和未验证风险，不以“代码已写”代替完成。

## 验证基线

后端或跨模块修改：

```powershell
python -m compileall -q backend tests
python -m unittest discover -s tests -p 'test_*.py'
cmd /c "启动VideoFree.cmd --check"
```

前端修改：

```powershell
cd frontend
npm run build
```

仅运行与变更相关的更小测试也可以，但涉及共享契约、任务状态、工作流注册或发布构建时，
必须运行对应的完整验证。测试服务使用独立端口，完成后必须关闭，不得遗留后台进程。

## 完成检查

- 根目录没有新增临时文件或一次性脚本。
- 没有新增平级重复实现、未注册工作流或跨层导入。
- 测试进程、开发服务器和临时网关均已关闭。
- 文档与实际目录、接口和默认行为一致。
