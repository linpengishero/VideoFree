"""Project-scoped film plans, timeline editing and independent renders."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from urllib.parse import quote
import uuid

from . import render
from .asr import ComfyWhisper
from .schemas import FilmWrite, MAX_AUDIO, MAX_MAIN, MAX_OVERLAY

STAGES = (
    ("writing", "文案定稿"), ("assets", "公共资产准备"),
    ("generation", "分镜与素材生成"), ("review", "审核与增强"),
    ("composition", "剪辑合成"), ("acceptance", "成片验收"),
)
ACTIVE = {"queued", "running"}
MAX_RENDER_HISTORY = 20
PLAN_KEYS = ('name', 'clips', 'overlay_clips', 'audio_clips', 'captions', 'texts', 'bgm_job_id', 'volume',
             'width', 'height', 'fps', 'fit', 'timeline_version')


class CompositionService:
    def __init__(self, runtime, plugin_runtime=None):
        self.runtime = runtime
        self.plugin_runtime = plugin_runtime

    def references(self, film: dict) -> list:
        ids = []
        for key in ('clips', 'overlay_clips', 'audio_clips'):
            ids += [clip['job_id'] for clip in film.get(key) or [] if clip.get('job_id')]
        if film.get('bgm_job_id'):
            ids.append(film['bgm_job_id'])
        return ids

    def persist(self, film, selected_job_id=None):
        self.runtime.save(film, self.references(film), self._active(film), selected_job_id)

    @staticmethod
    def _active(film: dict) -> bool:
        return any(film.get(key, {}).get('status') in ACTIVE for key in ('render', 'preview', 'transcribe'))

    def _cancel_marker(self, project_id: str, film_id: str, quality: str) -> Path:
        return self.runtime.directory(project_id) / 'films' / film_id / f'.cancel-{quality}'

    def project(self, project_id: str) -> dict:
        project = self.runtime.project(project_id)
        if not project:
            raise ValueError("项目不存在")
        return project

    def get(self, project_id: str, film_id: str) -> dict:
        self.project(project_id)
        film = self.runtime.document(project_id, film_id)
        if not film:
            raise ValueError("成片不存在")
        return self.reconcile(film, project_id)

    def alive(self, clip: dict) -> bool:
        if clip.get('kind', 'clip') == 'blank':
            return True
        if clip.get('library_path'):
            try:
                self.runtime.resolve_library_path(clip.get('project_id') or self.runtime.project_id,
                                                  clip['library_path'])
                return True
            except (ValueError, OSError):
                return False
        return bool(self.runtime.job(clip.get('job_id')))

    def reconcile(self, film, project_id):
        if self._active(film):
            return film
        clips = [c for c in film['clips'] if self.alive({**c, 'project_id': project_id})]
        overlays = [c for c in film.get('overlay_clips', []) if self.alive({**c, 'project_id': project_id})]
        audios = [c for c in film.get('audio_clips', []) if self.alive({**c, 'project_id': project_id})]
        bgm = film.get('bgm_job_id')
        if (len(clips) != len(film['clips']) or len(overlays) != len(film.get('overlay_clips', [])) or
                len(audios) != len(film.get('audio_clips', [])) or (bgm and not self.runtime.job(bgm))):
            film['clips'] = clips
            film['overlay_clips'] = overlays
            film['audio_clips'] = audios
            film['bgm_job_id'] = bgm if bgm and self.runtime.job(bgm) else None
            film['render'] = {'status': 'draft', 'progress': 0}
            for stage in ('composition', 'acceptance'):
                film['stages'][stage].update(status='pending', note='源素材已删除，请重新确认')
            self.persist(film)
        return film

    def list(self, project_id: str) -> list:
        self.project(project_id)
        return [self.reconcile(film, project_id) for film in self.runtime.documents(project_id)]

    def selected(self, project_id: str) -> list:
        self.project(project_id)
        return [job for job in self.runtime.jobs(project_id)
                if job['kind'] == 'video' and job['status'] == 'completed' and job['id'] in self.runtime.selected()]

    IMPORT_KIND = {'video': {'.mp4', '.mov', '.webm', '.mkv'},
                   'audio': {'.wav', '.mp3', '.flac', '.ogg', '.m4a'},
                   'image': {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}}

    def import_asset(self, project_id: str, upload_id: str, name: str = '') -> dict:
        """Copy a browser-uploaded media file into the project's plugin import folder."""
        self.project(project_id)
        source = self.runtime.upload_file(upload_id)
        suffix = source.suffix.lower()
        kind = next((k for k, exts in self.IMPORT_KIND.items() if suffix in exts), None)
        if not kind:
            raise ValueError('不支持的素材文件类型')
        imports = self.runtime.directory(project_id) / 'imports'
        imports.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[^\w.\- ]+', '', Path(str(name or '')).stem).strip() or source.stem or 'asset'
        target = imports / f'{stem}{suffix}'
        counter = 1
        while target.exists():
            target = imports / f'{stem}-{counter}{suffix}'
            counter += 1
        shutil.copy2(source, target)
        relative = target.relative_to(self.runtime.projects_root).as_posix()
        return {'path': relative, 'name': target.name, 'type': kind, 'managed': True,
                'url': f'/v1/library/files/{quote(relative)}'}

    def imported_assets(self, project_id: str) -> list[dict]:
        self.project(project_id)
        directory = self.runtime.directory(project_id) / 'imports'
        result = []
        for path in sorted(directory.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True) if directory.is_dir() else []:
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            kind = next((value for value, extensions in self.IMPORT_KIND.items() if suffix in extensions), None)
            if not kind:
                continue
            relative = path.relative_to(self.runtime.projects_root).as_posix()
            result.append({'path': relative, 'name': path.name, 'type': kind, 'managed': True,
                           'url': f'/v1/library/files/{quote(relative)}'})
        return result

    def delete_asset(self, project_id: str, library_path: str) -> dict:
        self.project(project_id)
        imports = (self.runtime.directory(project_id) / 'imports').resolve()
        path = self.runtime.resolve_library_path(project_id, library_path)
        if imports not in path.parents:
            raise ValueError('只能删除成片插件导入的素材')
        for film in self.list(project_id):
            if self._active(film):
                raise RuntimeError('成片任务进行中，暂时不能删除导入素材')
            for key in ('clips', 'overlay_clips', 'audio_clips'):
                if any(item.get('library_path') == library_path for item in film.get(key) or []):
                    raise RuntimeError('素材正在被成片方案使用，请先从时间线移除')
        path.unlink()
        self.runtime.invalidate_library()
        return {'deleted': True, 'library_path': library_path}

    def select(self, job_id: str, selected: bool) -> dict:
        job = self.runtime.job(job_id)
        if not job or job['kind'] != 'video' or job['status'] != 'completed':
            raise ValueError("只有已完成的视频可以加入成片")
        project_id = job['project_id']
        if not selected and any(self._active(f) and
                                any(c.get('job_id') == job_id for c in f['clips']) for f in self.list(project_id)):
            raise RuntimeError("该视频正在合成中，暂时不能撤回")
        self.runtime.mark(job_id, selected)
        return {"job_id": job_id, "film_selected": selected, "project_id": project_id}

    def source(self, project_id: str, job_id: str, index: int = 0, video: bool = True, *, require_selected: bool = True,
               allow_image: bool = False) -> Path:
        video_suffixes = {'.mp4', '.mov', '.webm', '.mkv'}
        if allow_image:
            video_suffixes |= {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
        if isinstance(job_id, dict):
            clip = job_id
            path = self.runtime.resolve_library_path(
                project_id, clip.get('library_path'),
                video_suffixes if video else {'.wav', '.mp3', '.flac', '.ogg', '.m4a'})
            return path
        job = self.runtime.job(job_id)
        if not job or job.get('project_id') != project_id or job['status'] != 'completed':
            raise ValueError("素材不存在、尚未完成或不属于当前项目")
        if video and (job['kind'] != 'video' or (require_selected and job_id not in self.runtime.selected())):
            raise ValueError("视频尚未在编辑页面加入成片，或已撤回")
        if not video and job['kind'] not in {'tts', 'music'}:
            raise ValueError("背景音轨必须是声音或音乐")
        artifacts = job.get('artifacts') or []
        if index < 0 or index >= len(artifacts):
            raise ValueError("素材产物索引无效")
        relative = artifacts[index].get('project_path', '')
        root = (self.runtime.projects_root / str(self.runtime.project(project_id)['output_subdir'])).resolve()
        path = (self.runtime.projects_root / relative).resolve()
        if not relative or root not in path.parents or not path.is_file():
            raise ValueError("项目素材文件不存在，请重新生成或恢复文件")
        if path.suffix.lower() not in (video_suffixes if video else {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}):
            raise ValueError("素材文件类型不符合用途")
        return path

    def save(self, project_id: str, body: dict, film_id: str | None = None, *,
             selected_job_id: str | None = None, expected_revision: int | None = None) -> dict:
        self.project(project_id)
        previous = self.get(project_id, film_id) if film_id else None
        if previous and expected_revision is not None and previous.get('revision', 0) != expected_revision:
            raise RuntimeError('成片方案已被修改，请刷新后重试')
        if previous and self._active(previous):
            raise RuntimeError("成片任务进行中，请完成后再编辑")
        # Updates may omit unchanged fields. Validate the effective plan so canvas-dependent
        # rules never run against schema defaults that differ from the stored film.
        effective = {key: previous[key] for key in PLAN_KEYS if previous and key in previous}
        effective.update(body)
        effective = FilmWrite.model_validate(effective).model_dump(by_alias=True)
        video_jobs = set()
        for clip in effective.get('clips') or []:
            if clip.get('kind') != 'blank':
                self.source(project_id, clip if clip.get('library_path') else clip['job_id'], clip.get('artifact_index', 0),
                            require_selected=False, allow_image=True)
                if clip.get('job_id'):
                    video_jobs.add(clip['job_id'])
        for clip in effective.get('overlay_clips') or []:
            self.source(project_id, clip if clip.get('library_path') else clip['job_id'], clip.get('artifact_index', 0), require_selected=False, allow_image=True)
            if clip.get('job_id'):
                video_jobs.add(clip['job_id'])
        for clip in effective.get('audio_clips') or []:
            self.source(project_id, clip if clip.get('library_path') else clip['job_id'], clip.get('artifact_index', 0), video=False)
        if effective.get('bgm_job_id'):
            self.source(project_id, effective['bgm_job_id'], video=False)
        plan = {key: effective[key] for key in PLAN_KEYS if key in effective}
        stale_preview_id = (previous or {}).get('preview', {}).get('id')
        film = {**(previous or {}), **plan, 'id': film_id or f"film-{uuid.uuid4().hex[:12]}",
                'project_id': project_id, 'updated_at': time.time(),
                'revision': (previous or {}).get('revision', 0) + 1}
        film.setdefault('stages', {key: {'label': label, 'status': 'pending', 'note': '', 'updated_at': time.time()} for key, label in STAGES})
        film.setdefault('renders', [])
        film.pop('preview', None)
        film['render'] = {'status': 'draft', 'progress': 0}
        film['stages']['composition'].update(status='pending', note='')
        film['stages']['acceptance'].update(status='pending', note='')
        self.persist(film, selected_job_id)
        if stale_preview_id:
            shutil.rmtree(self.runtime.directory(project_id) / 'films' / film['id'] / stale_preview_id,
                          ignore_errors=True)
        for job_id in video_jobs:
            self.runtime.mark(job_id, True)
        return film

    def add_clip(self, project_id: str, film_id: str, clip: dict) -> dict:
        film = self.get(project_id, film_id)
        if self._active(film):
            raise RuntimeError('目标成片任务正在进行，请完成后再添加')
        self.source(project_id, clip if clip.get('library_path') else clip['job_id'], clip.get('artifact_index', 0), require_selected=False, allow_image=True)
        if clip.get('out', 0) <= clip.get('in', 0):
            raise ValueError('裁剪终点必须大于起点')
        if any((c.get('job_id') and c.get('job_id') == clip.get('job_id') or
                c.get('library_path') and c.get('library_path') == clip.get('library_path')) and
               c.get('artifact_index', 0) == clip.get('artifact_index', 0) for c in film['clips']):
            return film
        if len(film['clips']) >= MAX_MAIN:
            raise ValueError(f'每部成片最多添加{MAX_MAIN}个镜头')
        body = {key: film[key] for key in PLAN_KEYS if key in film}
        body['clips'] = [*film['clips'], clip]
        return self.save(project_id, body, film_id, selected_job_id=clip.get('job_id'))

    def progress(self, project_id: str, film_id: str, stage: str, status: str, note: str) -> dict:
        film = self.get(project_id, film_id)
        if stage not in film['stages'] or stage == 'composition':
            raise ValueError("阶段无效；剪辑合成状态由真实渲染任务维护")
        if stage == 'acceptance' and status == 'completed' and film['render']['status'] != 'completed':
            raise ValueError("真实合成成功后才能验收")
        film['stages'][stage].update(status=status, note=note, updated_at=time.time())
        stale_preview_id = film.get('preview', {}).get('id')
        film['updated_at'] = time.time()
        self.persist(film)
        if stale_preview_id:
            shutil.rmtree(self.runtime.directory(project_id) / 'films' / film_id / stale_preview_id,
                          ignore_errors=True)
        return film

    def delete(self, project_id: str, film_id: str) -> None:
        film = self.get(project_id, film_id)
        if self._active(film):
            raise RuntimeError("成片任务进行中，暂时不能删除")
        directory = self.runtime.directory(project_id) / 'films' / film_id
        if directory.is_dir():
            shutil.rmtree(directory)
        self.runtime.delete(project_id, film_id)
        self.runtime.invalidate_library()

    def recover(self) -> None:
        for project in self.runtime.projects():
            for film in self.runtime.documents(project['id']):
                changed = False
                for key in ('render', 'preview'):
                    if film.get(key, {}).get('status') in ACTIVE:
                        film[key] = {**film[key], 'status': 'failed', 'error': '网关重启中断了合成，请重新提交'}
                        film['stages']['composition'].update(status='failed', note='网关重启中断了合成', updated_at=time.time())
                        changed = True
                if film.get('transcribe', {}).get('status') in ACTIVE:
                    film['transcribe'] = {'status': 'failed', 'progress': 0,
                                          'error': '网关重启中断了字幕识别，请重新识别',
                                          'updated_at': time.time()}
                    changed = True
                if changed:
                    self.persist(film)

    def plan_for(self, project_id: str, film: dict, quality: str) -> dict:
        """Resolve the stored plan into the engine's timeline plan."""
        def entry(clip: dict, *, absolute: bool = False, audio: bool = False) -> dict:
            item = {'kind': clip.get('kind', 'clip'), 'in': float(clip.get('in', 0)), 'out': float(clip['out']),
                    'original': bool(clip.get('original', True)), 'volume': int(clip.get('volume', 100)),
                    'fade_in': float(clip.get('fade_in', 0)), 'fade_out': float(clip.get('fade_out', 0))}
            if item['kind'] != 'blank':
                path = self.source(project_id, clip if clip.get('library_path') else clip['job_id'], clip.get('artifact_index', 0),
                                   video=not audio, require_selected=False, allow_image=not audio)
                item.update({'job_id': clip.get('job_id'), 'library_path': clip.get('library_path'), 'source': str(path),
                             'stamp': f'{path.stat().st_mtime_ns}:{path.stat().st_size}',
                             'still': path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}})
            if clip.get('transition'):
                item['transition'] = dict(clip['transition'])
            if absolute:
                item['start'] = float(clip.get('start', 0))
                item['duration'] = round(item['out'] - item['in'], 6)
                if clip.get('rect'):
                    item['rect'] = dict(clip['rect'])
            return item

        return {
            'quality': quality,
            'main': [entry(clip) for clip in film['clips']],
            'overlays': [entry(clip, absolute=True) for clip in film.get('overlay_clips') or []],
            'audios': [entry(clip, absolute=True, audio=True) for clip in film.get('audio_clips') or []],
            'captions': [dict(item) for item in film.get('captions') or []],
            'texts': [dict(item) for item in film.get('texts') or []],
            'bgm_path': str(self.source(project_id, film['bgm_job_id'], video=False)) if film.get('bgm_job_id') else None,
            'volume': int(film.get('volume', 18)),
            'width': int(film['width']), 'height': int(film['height']), 'fps': int(film['fps']), 'fit': film['fit'],
        }

    async def transcribe(self, project_id: str, film_id: str,
                         language: str = 'zh', model: str = 'large-v3-turbo') -> dict:
        if not self.plugin_runtime:
            raise RuntimeError('字幕识别运行时不可用')
        film = self.get(project_id, film_id)
        revision = film.get('revision', 0)
        plan = self.plan_for(project_id, film, 'preview')
        temporary = self.runtime.directory(project_id) / 'films' / film_id / f'.asr-{uuid.uuid4().hex}.wav'
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            duration = await render.dialogue_audio(plan, temporary)
            from .asr import transcription_prompt
            prompt = transcription_prompt(language)
            raw = await ComfyWhisper(self.plugin_runtime).transcribe(
                temporary, language=language, model=model, prompt=prompt, seek=0, duration=duration)
        finally:
            temporary.unlink(missing_ok=True)
        latest = self.get(project_id, film_id)
        if latest.get('revision', 0) != revision:
            raise RuntimeError('字幕识别期间方案已修改，请重新识别')
        film = latest
        generated = []
        from .asr import normalize_text
        for item in raw:
            start = max(0.0, item['start'])
            end = min(duration, max(0.0, item['end']))
            if end > start:
                generated.append({'text': normalize_text(item['text'], language),
                                  'start': round(start, 3), 'end': round(end, 3)})
        film['captions'] = generated
        film['updated_at'] = time.time()
        film['revision'] = revision + 1
        film['render'] = {'status': 'draft', 'progress': 0}
        film.pop('preview', None)
        self.persist(film)
        return film

    async def queue_transcribe(self, project_id: str, film_id: str,
                               language: str = 'zh', model: str = 'large-v3-turbo') -> dict:
        """Start recognition in the plugin-owned application task manager."""
        film = self.get(project_id, film_id)
        state = film.get('transcribe') or {}
        if state.get('status') in ACTIVE:
            return film
        film['transcribe'] = {'status': 'queued', 'progress': 0, 'error': '',
                              'updated_at': time.time()}
        self.persist(film)
        key = f'transcribe:{film_id}'

        async def run():
            current = self.get(project_id, film_id)
            current['transcribe'] = {'status': 'running', 'progress': 5, 'error': '',
                                     'updated_at': time.time()}
            self.persist(current)
            try:
                result = await self.transcribe(project_id, film_id, language, model)
                result['transcribe'] = {'status': 'completed', 'progress': 100, 'error': '',
                                        'updated_at': time.time()}
                self.persist(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failed = self.get(project_id, film_id)
                failed['transcribe'] = {'status': 'failed', 'progress': 0,
                                        'error': str(exc), 'updated_at': time.time()}
                self.persist(failed)

        try:
            self.runtime.start(key, run())
        except Exception as exc:
            film['transcribe'] = {'status': 'failed', 'progress': 0, 'error': str(exc),
                                  'updated_at': time.time()}
            self.persist(film)
            raise
        return film

    async def preflight(self, project_id: str, plan: dict) -> None:
        """Probe every source before anything is queued."""
        _, ffprobe = render.toolkit()
        probed: dict[str, dict] = {}
        for item in plan['main']:
            if item['kind'] == 'blank':
                continue
            if item['source'] not in probed:
                probed[item['source']] = await render.probe(ffprobe, Path(item['source']))
            if item.get('still'):
                probed[item['source']]['duration'] = item['out'] - item['in']
                probed[item['source']]['has_video'] = True
            render.validate(item, probed[item['source']])
        for item in plan['overlays']:
            media = await render.probe(ffprobe, Path(item['source']))
            if item.get('still'):
                media['duration'] = item['out'] - item['in']
                media['has_video'] = True
            render.validate(item, media)
        for item in plan['audios']:
            media = await render.probe(ffprobe, Path(item['source']))
            render.validate_audio(item, media)
        if plan['bgm_path']:
            await render.probe(ffprobe, Path(plan['bgm_path']))

    async def validate(self, project_id: str, film_id: str) -> dict:
        """Return an AI-friendly read-only preflight result without queueing a render."""
        film = self.get(project_id, film_id)
        issues = []
        if not film.get('clips'):
            issues.append('主轨没有素材')
        else:
            try:
                await self.preflight(project_id, self.plan_for(project_id, film, 'preview'))
            except (ValueError, RuntimeError, OSError) as exc:
                issues.append(str(exc))
        return {
            'film_id': film_id,
            'revision': film.get('revision', 0),
            'valid': not issues,
            'issues': issues,
            'summary': {
                'clips': len(film.get('clips') or []),
                'overlays': len(film.get('overlay_clips') or []),
                'audio_clips': len(film.get('audio_clips') or []),
                'captions': len(film.get('captions') or []),
                'output': f"{film.get('width')}x{film.get('height')}@{film.get('fps')}fps",
                'fit': film.get('fit'),
            },
        }

    async def submit(self, project_id: str, film_id: str, quality: str = 'final') -> dict:
        film = self.get(project_id, film_id)
        if film.get('transcribe', {}).get('status') in ACTIVE:
            raise RuntimeError('字幕识别进行中，请完成后再导出')
        key = 'preview' if quality == 'preview' else 'render'
        if self._active(film):
            raise RuntimeError("该成片已经在合成队列中")
        if not film['clips']:
            raise ValueError("请先添加入选视频")
        plan = self.plan_for(project_id, film, quality)
        await self.preflight(project_id, plan)
        task_id = uuid.uuid4().hex[:12]
        previous = film.get('preview', {}) if quality == 'preview' else {}
        previous_id = previous.get('previous_id') or previous.get('id')
        if previous.get('status') in {'failed', 'cancelled'} and previous.get('id') != previous_id:
            shutil.rmtree(self.runtime.directory(project_id) / 'films' / film_id / previous['id'],
                          ignore_errors=True)
        film[key] = {'id': task_id, 'status': 'queued', 'progress': 0, 'error': '',
                     **({'previous_id': previous_id} if previous_id else {})}
        self._cancel_marker(project_id, film_id, quality).unlink(missing_ok=True)
        if quality != 'preview':
            film['stages']['composition'].update(status='running', note='等待合成', updated_at=time.time())
        self.persist(film)
        self.runtime.start(film_id if quality != 'preview' else f'{film_id}#preview',
                           self._render(project_id, film_id, quality, plan, task_id))
        return film

    def cancel(self, project_id: str, film_id: str, quality: str = 'final') -> dict:
        if quality not in {'final', 'preview'}:
            raise ValueError('合成类型无效')
        film = self.get(project_id, film_id)
        key = 'preview' if quality == 'preview' else 'render'
        if film.get(key, {}).get('status') not in ACTIVE:
            raise RuntimeError('当前没有正在运行或排队的成片任务，无需取消')
        marker = self._cancel_marker(project_id, film_id, quality)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('cancelled', encoding='utf-8')
        film[key] = {**film.get(key, {}), 'status': 'cancelled', 'error': '用户取消合成'}
        if quality != 'preview':
            film['stages']['composition'].update(status='pending', note='用户取消合成', updated_at=time.time())
        self.persist(film)
        self.runtime.cancel(film_id if quality != 'preview' else f'{film_id}#preview')
        return film

    async def _render(self, project_id: str, film_id: str, quality: str, plan: dict, task_id: str) -> None:
        key = 'preview' if quality == 'preview' else 'render'
        directory = None
        try:
            async with self.runtime.semaphore():
                film = self.get(project_id, film_id)
                if (self._cancel_marker(project_id, film_id, quality).exists() or
                        film.get(key, {}).get('id') != task_id or film.get(key, {}).get('status') not in ACTIVE):
                    raise asyncio.CancelledError()
                film[key].update(status='running', progress=1)
                self.persist(film)
                root = self.runtime.directory(project_id)
                directory = root / 'films' / film_id / film[key]['id']
                directory.mkdir(parents=True, exist_ok=False)
                plan['output'] = str(directory / ('preview.mp4' if quality == 'preview' else 'final.partial.seg'))
                plan['cache_dir'] = str(root / 'films' / film_id / '_cache')
                plan['captions_path'] = str(directory / 'captions.ass')
                (directory / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')

                def report(progress: int) -> None:
                    if self._cancel_marker(project_id, film_id, quality).exists():
                        raise asyncio.CancelledError()
                    current = self.runtime.document(project_id, film_id)
                    if not current:
                        return
                    current[key]['progress'] = max(1, min(99, int(progress)))
                    self.persist(current)

                await render.compose(plan, report, directory / 'render.log')
                if self._cancel_marker(project_id, film_id, quality).exists():
                    raise asyncio.CancelledError()
                partial = directory / Path(plan['output']).name
                if not partial.is_file():
                    raise ValueError('合成未产出成片文件，请查看该次合成的 render.log')
                if quality == 'preview':
                    film = self.get(project_id, film_id)
                    previous_id = film.get('preview', {}).get('previous_id')
                    relative = (directory / 'preview.mp4').relative_to(self.runtime.projects_root).as_posix()
                    film['preview'] = {**film['preview'], 'status': 'completed', 'progress': 100, 'error': '',
                                       'url': f'/v1/library/files/{quote(relative)}', 'completed_at': time.time(),
                                       'duration': plan.get('timeline_duration')}
                    film['preview'].pop('previous_id', None)
                    self.persist(film)
                    if previous_id and previous_id != task_id:
                        shutil.rmtree(directory.parent / previous_id, ignore_errors=True)
                    return
                partial.replace(directory / 'final.mp4')
                film = self.get(project_id, film_id)
                relative = (directory / 'final.mp4').relative_to(self.runtime.projects_root).as_posix()
                film['render'].update(status='completed', progress=100, url=f'/v1/library/files/{quote(relative)}',
                                      completed_at=time.time(), duration=plan.get('timeline_duration'))
                film['renders'].append({**film['render'], 'plan': {item: film[item] for item in
                                                                  ('name', 'clips', 'overlay_clips', 'audio_clips', 'captions', 'texts',
                                                                   'bgm_job_id', 'width', 'height', 'fps', 'fit', 'volume')
                                                                  if item in film}})
                expired = film['renders'][:-MAX_RENDER_HISTORY]
                film['renders'] = film['renders'][-MAX_RENDER_HISTORY:]
                film['stages']['composition'].update(status='completed', note='合成成功', updated_at=time.time())
                self.persist(film)
                for item in expired:
                    old_id = item.get('id')
                    if old_id and old_id != task_id:
                        shutil.rmtree(directory.parent / old_id, ignore_errors=True)
                self.runtime.invalidate_library()
        except asyncio.CancelledError:
            current = self.runtime.document(project_id, film_id)
            cancelled = self._cancel_marker(project_id, film_id, quality).exists()
            if cancelled:
                self._fail(project_id, film_id, quality, '用户取消合成', status='cancelled')
                self._cancel_marker(project_id, film_id, quality).unlink(missing_ok=True)
            else:
                self._fail(project_id, film_id, quality, '网关关闭中断了合成，请重新提交')
            return
        except Exception as exc:
            self._fail(project_id, film_id, quality, str(exc))
        finally:
            if directory and (self.runtime.document(project_id, film_id) or {}).get(key, {}).get('status') != 'completed':
                self._clean(directory)

    def _fail(self, project_id: str, film_id: str, quality: str, message: str, status: str = 'failed') -> None:
        key = 'preview' if quality == 'preview' else 'render'
        film = self.runtime.document(project_id, film_id)
        if not film:
            return
        film[key] = {**film.get(key, {}), 'status': status, 'error': message}
        if quality != 'preview':
            film['stages']['composition'].update(status='pending' if status == 'cancelled' else 'failed',
                                                 note=message[:200], updated_at=time.time())
        self.persist(film)

    @staticmethod
    def _clean(directory: Path) -> None:
        """Drop media and intermediate files, keep the plan snapshot and the log."""
        for pattern in ('*.mp4', '*.seg'):
            for path in directory.rglob(pattern):
                path.unlink(missing_ok=True)
        for path in directory.glob('concat.txt'):
            path.unlink(missing_ok=True)

    async def proxies(self, project_id: str, job_id: str | None = None, artifact_index: int = 0,
                      library_path: str | None = None) -> dict:
        """Build the thumbnail strip and waveform a timeline needs for one source."""
        if not job_id and not library_path:
            raise ValueError('必须指定素材')
        clip = {'library_path': library_path} if library_path else job_id
        path = self.source(project_id, clip, artifact_index, video=not bool(library_path and
                            Path(library_path).suffix.lower() in {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}),
                           require_selected=False, allow_image=True)
        ffmpeg, ffprobe = render.toolkit()
        media = await render.probe(ffprobe, path)
        key = job_id or hashlib.sha1(str(library_path).encode()).hexdigest()[:16]
        stamp = hashlib.sha1(f'{path.stat().st_mtime_ns}:{path.stat().st_size}'.encode()).hexdigest()[:16]
        directory = self.runtime.directory(project_id) / '_proxies' / f'{key}-{artifact_index}-{stamp}'
        cached = (directory / ('thumbs.dat' if media['has_video'] else 'wave.dat')).is_file()
        directory.mkdir(parents=True, exist_ok=True)
        if media['has_video']:
            await render.proxies(ffmpeg, path, directory, media['duration'] or 0, with_wave=bool(media['has_audio']))
        elif media['has_audio']:
            await render.waveform(ffmpeg, path, directory)
        def data_url(name: str) -> str | None:
            image = directory / name
            if not image.is_file():
                return None
            return 'data:image/png;base64,' + base64.b64encode(image.read_bytes()).decode()
        return {'thumbnails_url': data_url('thumbs.dat'), 'waveform_url': data_url('wave.dat'),
                'duration': media['duration'], 'cached': cached}
