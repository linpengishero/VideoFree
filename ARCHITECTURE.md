# 架构说明

项目采用模块化单体。所有能力运行在一个 FastAPI 进程内，但代码按业务所有权隔离，避免通过全局工具函数互相穿透。

## 依赖方向

```text
interfaces/http -> modules -> integrations / persistence
                         -> core
bootstrap / lifecycle -> all application modules
```

- `backend/core/`：环境配置、运行时上下文、错误和日志，不依赖业务模块。
- `backend/persistence/`：SQLite 持久化，只提供数据访问。
- `backend/integrations/`：ComfyUI 与原生供应商适配，不包含 HTTP 路由。
- `backend/modules/`：generation、collaboration、settings、presets 等业务模块。
- `backend/interfaces/http/`：V1/V2 请求模型、能力映射和路由适配。
- `backend/lifecycle.py`：启动恢复、worker 创建、缓存清理和优雅关闭。

## 关键所有权

- `ApplicationContext` 是运行期可变状态的唯一容器；禁止新增模块级可变队列、锁或任务表。
- `TaskStore` 负责可恢复任务包和 manifest；ComfyUI 执行器不直接设计磁盘结构。
- `WorkflowRegistry` 负责工作流 allowlist、路径校验和画布加载；HTTP 层不读取工作流文件。
- generation 按注册表中的执行面调度：本地 ComfyUI 能力进入受控队列，声明
  `execution_plane: cloud` 的供应商能力直接并发提交；两者共用任务状态、持久化和项目归档。
- collaboration 的 `progress`、`media`、`prompts`、`analysis` 和 `service` 分别负责进度投影、素材适配、固定提示词、确定性检查和导演编排。
- projects 负责工作区当前项目、任务归属和 `data/projects/` 项目素材库。生成任务完成后由该域发布全部最终产物；资源面板不扫描 ComfyUI 输出目录。
- V1 路由按 system、assets、generation、collaboration 分组；V2 的 schema 与 capability 映射独立于路由组装。

## 扩展规则

1. 新模型先在 `workflows/registry.json` 注册，再在对应 integration 中实现差异，禁止在路由里判断节点。
   云端供应商必须显式声明 `execution_plane: cloud`，本地能力保持默认的 `local`。
2. 新导演技能只增加技能文件和注册信息；选择逻辑进入 collaboration，不修改 generation。
3. 跨模块复用的方法只有在两个业务域真实使用时才进入 shared；单域帮助函数留在本域。
4. HTTP handler 只做协议校验、错误映射和调用编排，不直接访问外部服务文件格式。
5. 保留 `backend.app` 和 `legacy_exports.py` 仅为 1.0 兼容；新代码必须从实际所有者导入。

## 验证

```powershell
python -m compileall -q backend tests
python -m unittest discover -s tests -p 'test_*.py'
cd frontend
npm ci
npm run build
cd ..
cmd /c start_gateway.cmd --check
```
