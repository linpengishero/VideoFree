# Development Agent Constraints

**English** · [中文](AGENTS.md)

These rules apply to the entire repository. Before changing code, every automated development agent must read this file and `ARCHITECTURE_EN.md` (the Chinese source is `ARCHITECTURE.md`). The goal is to preserve the modular-monolith structure and prevent root-directory sprawl, ownership violations, and duplicate implementations.

## Non-Negotiable Rules

1. Do not add temporary scripts, test output, workflow copies, downloaded files, `*_backup`, or `*.bak` files to the repository root.
2. Do not create a new top-level directory for a one-off change. Prove that existing directories cannot own the responsibility before adding one.
3. Do not put business logic in HTTP routes, startup scripts, or global utility modules.
4. Do not create an abstraction, interface, factory, or general utility with only one caller.
5. Do not keep old and new implementations side by side. A compatibility entry point may only delegate to the single implementation and must state when it can be removed.
6. Do not manually edit build artifacts, caches, or runtime data. Edit source files and regenerate them through the normal build or runtime process.

## File Ownership

| Content | Sole owner |
| --- | --- |
| Environment configuration, errors, logging, runtime context | `backend/core/` |
| SQLite data access | `backend/persistence/` |
| ComfyUI, model vendors, and external-service adapters | `backend/integrations/` |
| generation, collaboration, settings, presets, and other business logic | `backend/modules/<domain>/` |
| HTTP schemas, V1/V2 routes, and protocol conversion | `backend/interfaces/http/` |
| Startup, recovery, workers, and graceful shutdown | `backend/bootstrap.py`, `backend/lifecycle.py` |
| Framework frontend components, state, and style source | `frontend/src/` |
| Static frontend source assets | `frontend/public/` |
| Plugin workflows, dedicated compilers, and collaboration skills | `plugins/<plugin-id>/` |
| Application-plugin pages, business logic, and actions | `plugins/<plugin-id>/ui/` and the same plugin directory, registered by `plugin.json/application/actions` |
| Plugin capabilities, primary categories, and processing modes | `plugins/<plugin-id>/plugin.json`, the sole registration source |
| Director and capability skills | `.agents/skills/` or the corresponding plugin's `collaboration/skills/`; follow neighboring organization |
| Automated tests and fixed test assets | `tests/` |
| Runtime data, caches, jobs, and generated media | `data/`; never commit or manually edit as source |
| Frontend build output | `static/dist/`, generated only by the frontend build |

Keep the repository root for project entry points and repository-level files, such as `videofree.bat`, `videofree.sh`, `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, dependency manifests, and environment examples. Do not create a file whose ownership is unclear.

## Dependencies and Boundaries

The dependency direction must remain:

```text
interfaces/http -> modules -> integrations / persistence
                         -> core
bootstrap / lifecycle -> application modules
```

- `ApplicationContext` is the sole container for mutable runtime state. Do not add module-level mutable queues, locks, or task tables.
- HTTP handlers only validate protocol data, map errors, and call business services.
- Workflows live in their owning plugin and are registered in its `plugin.json`. Routes must not parse workflow nodes or read workflow files. See `docs/plugin-protocol.md`.
- Add director skills through skill files and registration metadata. Selection and orchestration belong to collaboration, not generation.
- Extract shared code only when at least two business domains actually reuse it. Keep single-domain helpers in their domain.
- Prefer existing repository implementations, standard Python/browser features, and installed dependencies. Avoid adding dependencies for small tasks.

## Change Process

1. Locate the single owner of the behavior and search all callers.
2. Inspect existing worktree changes. Preserve user changes and leave unrelated changes alone.
3. Fix the root cause with the fewest files; do not refactor unrelated code opportunistically.
4. Before adding a file, confirm its ownership in the table above and that it has a real caller.
5. Add the smallest executable test for non-trivial logic. For bug fixes, prefer a regression test.
6. Run verification appropriate to the change and ensure no root clutter, cache, or backup copy was added.
7. Report changed files, verification, and unverified risks. Do not treat “code written” as completion.

## Verification Baseline

For backend or cross-module changes:

```powershell
python -m compileall -q backend tests
python -m unittest discover -s tests -p 'test_*.py'
cmd /c "videofree.bat --check"
```

For frontend changes:

```powershell
cd frontend
npm run build
```

Smaller relevant tests are acceptable for narrow changes. Changes to shared contracts, task state, workflow registration, or release builds require corresponding full verification. Run test services on isolated ports and shut them down afterward; leave no background processes.

## Completion Checklist

- No temporary files or one-off scripts were added to the repository root.
- No duplicate peer implementation, unregistered workflow, or cross-layer import was introduced.
- Test processes, development servers, and temporary gateways are stopped.
- Documentation matches the actual directories, interfaces, and default behavior.
