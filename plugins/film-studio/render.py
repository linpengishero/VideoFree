"""Self-contained FFmpeg timeline engine for the editing plugin.

FFmpeg and FFprobe are external system dependencies resolved from ``PATH``. The
plugin owns the timeline logic but does not redistribute platform binaries.

A plan is a resolved timeline:

``main``      ordered main-track items (``clip`` or ``blank``); array order is time order
``overlays``  picture-in-picture clips placed at an absolute ``start``
``audios``    extra audio clips placed at an absolute ``start``
``bgm_path``  background music mixed under everything

Every external program is started with an argument array.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

TOOLS = ('ffmpeg', 'ffprobe')

CUT_TOLERANCE = 0.05
PROBE_TIMEOUT = 120
SEGMENT_TIMEOUT = 1800
MIX_TIMEOUT = 3600
SAMPLE_RATE = 48000
VIDEO_PRESET = 'veryfast'
VIDEO_CRF = '20'
AUDIO_BITRATE = '192k'
PRESET = {'final': VIDEO_PRESET, 'preview': 'ultrafast'}
CRF = {'final': VIDEO_CRF, 'preview': '32'}
CACHE_LIMIT = 40
# Intermediate files use a non-media suffix on purpose: the project library indexes
# files by extension, so process files must never look like media.
SEG_SUFFIX = '.seg'
TRANSITIONS = frozenset({'fade', 'wipeleft', 'wiperight', 'slideleft', 'slideright', 'slideup', 'slidedown', 'circleopen', 'circleclose'})


def toolkit() -> tuple[Path, Path]:
    """Resolve ffmpeg and ffprobe from PATH, or explain how to install them."""
    resolved = {name: shutil.which(name) for name in TOOLS}
    missing = [name for name, path in resolved.items() if not path]
    if missing:
        raise ValueError(
            f'剪辑插件找不到 {"、".join(missing)}。请安装 FFmpeg，并确保 ffmpeg 和 ffprobe '
            '可从系统 PATH 执行，然后重启 VideoFree。安装说明见 plugins/film-studio/INSTALL.md。')
    return Path(resolved['ffmpeg']), Path(resolved['ffprobe'])


def _kill_flags() -> dict:
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}


async def _terminate(process: asyncio.subprocess.Process) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 10)
    except asyncio.TimeoutError:
        pass


def _tail(path: Path | None, limit: int = 2000) -> str:
    if not path or not path.is_file():
        return ''
    text = path.read_text(encoding='utf-8', errors='replace').strip()
    return text[-limit:]


async def _run(args: list, *, log_path: Path | None, timeout: int, action: str, capture: bool = False) -> str:
    """Run one tool, stream stderr to the run log and return captured stdout."""
    flags = _kill_flags()
    handle = log_path.open('ab') if log_path else subprocess.PIPE
    try:
        process = await asyncio.create_subprocess_exec(
            *[str(item) for item in args],
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=handle, **flags)
    finally:
        if log_path:
            handle.close()
    captured_stdout = b''
    captured_stderr = b''
    try:
        captured_stdout, captured_stderr = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        await _terminate(process)
        raise ValueError(f'{action}超时（超过 {timeout} 秒），已终止')
    except asyncio.CancelledError:
        await _terminate(process)
        raise
    if process.returncode:
        detail = (captured_stderr or b'').decode('utf-8', 'replace').strip() or _tail(log_path)
        raise ValueError(f'{action}失败（FFmpeg 退出码 {process.returncode}）：{detail[-2000:]}')
    return (captured_stdout or b'').decode('utf-8', 'replace')


def _seconds(value: Any) -> float | None:
    try:
        if value in (None, 'N/A', ''):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def probe(ffprobe: Path, path: Path, log_path: Path | None = None) -> dict:
    """Read duration, video and audio presence of one media file."""
    raw = await _run([ffprobe, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path],
                     log_path=log_path, timeout=PROBE_TIMEOUT, action=f'读取素材信息 {path.name}', capture=True)
    data = json.loads(raw or '{}')
    streams = data.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video' and s.get('disposition', {}).get('attached_pic') != 1]
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    duration = _seconds(data.get('format', {}).get('duration'))
    if duration is None:
        duration = max((_seconds(s.get('duration')) or 0 for s in videos), default=None) or None
    first = videos[0] if videos else (audios[0] if audios else {})
    return {'path': str(path), 'duration': duration, 'width': int(first.get('width') or 0),
            'height': int(first.get('height') or 0), 'has_video': bool(videos), 'has_audio': bool(audios)}


def validate(clip: dict, media: dict) -> None:
    """Reject dead sources and out-of-range cuts before any encoding starts."""
    label = Path(clip.get('source', '')).name or clip.get('job_id', '素材')
    if not media['has_video']:
        raise ValueError(f'素材没有视频轨，无法作为镜头：{label}')
    duration = media['duration']
    if duration is None:
        raise ValueError(f'无法读取素材时长，请重新生成或修复文件：{label}')
    if clip['in'] >= duration - CUT_TOLERANCE:
        raise ValueError(f'裁剪起点 {clip["in"]:.2f}s 已超过素材时长 {duration:.2f}s：{label}')
    if clip['out'] > duration + CUT_TOLERANCE:
        raise ValueError(f'裁剪终点 {clip["out"]:.2f}s 超过素材实际时长 {duration:.2f}s：{label}')


def validate_audio(clip: dict, media: dict) -> None:
    label = Path(clip.get('source', '')).name or clip.get('job_id', '音轨')
    if not media['has_audio']:
        raise ValueError(f'素材没有音频轨，无法作为音轨使用：{label}')
    duration = media['duration']
    if duration is None:
        raise ValueError(f'无法读取音轨时长，请重新生成或修复文件：{label}')
    if clip['in'] >= duration - CUT_TOLERANCE:
        raise ValueError(f'音轨裁剪起点 {clip["in"]:.2f}s 已超过素材时长 {duration:.2f}s：{label}')
    if clip['out'] > duration + CUT_TOLERANCE:
        raise ValueError(f'音轨裁剪终点 {clip["out"]:.2f}s 超过素材实际时长 {duration:.2f}s：{label}')


def quality_dimensions(plan: dict) -> tuple[int, int, int]:
    """Return the (width, height, fps) actually encoded for this plan's quality."""
    width, height, fps = int(plan['width']), int(plan['height']), int(plan['fps'])
    if plan.get('quality') == 'preview':
        scale = min(1.0, 480 / max(1, height))
        width, height = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
        fps = min(fps, 15)
    return width, height, fps


def _video_filter(plan: dict) -> str:
    width, height, _ = quality_dimensions(plan)
    if plan.get('fit') == 'cover':
        return f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1'
    return (f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1')


def _fade_chain(prefix: str, item: dict, duration: float, *, video: bool) -> str:
    """Fade in/out for one segment; transitions are handled separately by xfade."""
    fade_in = float(item.get('fade_in') or 0)
    fade_out = float(item.get('fade_out') or 0)
    parts = []
    if fade_in > 0:
        parts.append(f'fade=t=in:st=0:d={fade_in:.6f}' if video else f'afade=t=in:st=0:d={fade_in:.6f}')
    if fade_out > 0:
        start = max(0.0, duration - fade_out)
        parts.append(f'fade=t=out:st={start:.6f}:d={fade_out:.6f}' if video else f'afade=t=out:st={start:.6f}:d={fade_out:.6f}')
    return ''.join(f',{part}' for part in parts)


def _audio_chain(item: dict, duration: float) -> str:
    volume = int(item.get('volume', 100))
    chain = f'volume={volume / 100:.4f},aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo'
    return chain + _fade_chain('', item, duration, video=False)


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f'{hours}:{minutes:02d}:{whole:02d}.{centis:02d}'


def _ass_text(value: str) -> str:
    return str(value).replace('\\', r'\\').replace('{', r'\\{').replace('}', r'\\}').replace('\n', r'\\N')


def write_ass(path: Path, captions: list[dict], texts: list[dict] | None = None, *,
              width: int = 1920, height: int = 1080, font_size: int = 48,
              primary: str = '&H00FFFFFF', outline: str = '&H00000000') -> None:
    """Write a UTF-8 ASS subtitle file owned by the film plugin."""
    lines = [
        '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
        '', '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding',
        f'Style: Default,Microsoft YaHei,{int(font_size)},{primary},&H000000FF,{outline},&H90000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,48,1',
        '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    for item in captions:
        try:
            start, end = float(item['start']), float(item['end'])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        lines.append(f'Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{_ass_text(item.get("text", ""))}')
    for item in texts or []:
        try:
            start, end = float(item['start']), float(item['end'])
            x, y = int(item['x']), int(item['y'])
            size = int(item.get('font_size', 64))
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        color = str(item.get('color', '#FFFFFF')).lstrip('#')
        if len(color) != 6:
            color = 'FFFFFF'
        ass_color = f'&H00{color[4:6]}{color[2:4]}{color[0:2]}&'
        override = rf'{{\an5\pos({x},{y})\fs{size}\1c{ass_color}}}'
        lines.append(f'Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{override}{_ass_text(item.get("text", ""))}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')


def _filter_path(path: Path) -> str:
    return path.as_posix().replace('\\', '/').replace(':', r'\:').replace("'", r"\'")


def _subtitle_command(ffmpeg: Path, source: Path, ass_path: Path, plan: dict, target: Path) -> list:
    preset, crf = PRESET.get(plan.get('quality'), VIDEO_PRESET), CRF.get(plan.get('quality'), VIDEO_CRF)
    return [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-i', source,
            '-vf', f"ass='{_filter_path(ass_path)}'", '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', preset, '-crf', crf, '-profile:v', 'high', '-pix_fmt', 'yuv420p',
            '-c:a', 'copy', '-movflags', '+faststart', '-f', 'mp4', target]


def segment_key(item: dict, plan: dict) -> str:
    """Stable cache key for one normalised segment."""
    width, height, fps = quality_dimensions(plan)
    payload = [item.get('kind'), item.get('source'), item.get('in'), item.get('out'), item.get('original'),
               item.get('volume'), item.get('fade_in'), item.get('fade_out'), plan.get('fit'),
               width, height, fps, plan.get('quality'), item.get('stamp')]
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()[:24]


def _segment_command(ffmpeg: Path, item: dict, plan: dict, target: Path, duration: float, media: dict | None) -> list:
    width, height, fps = quality_dimensions(plan)
    preset, crf = PRESET.get(plan.get('quality'), VIDEO_PRESET), CRF.get(plan.get('quality'), VIDEO_CRF)
    if item.get('kind', 'clip') == 'blank':
        inputs = ['-f', 'lavfi', '-i', f'color=black:s={width}x{height}:r={fps}:d={duration:.6f}',
                  '-f', 'lavfi', '-t', f'{duration:.6f}', '-i', f'anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}']
        video = f'[0:v]fps={fps},format=yuv420p[v]'
        audio = f'[1:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo[a]'
    else:
        keep_audio = bool(item.get('original', True)) and bool(media and media['has_audio'])
        if item.get('still'):
            inputs = ['-loop', '1', '-t', f'{duration:.6f}', '-i', item['source']]
        else:
            inputs = ['-ss', f"{item['in']:.6f}", '-t', f'{duration:.6f}', '-i', item['source']]
        if not keep_audio:
            inputs += ['-f', 'lavfi', '-t', f'{duration:.6f}', '-i',
                       f'anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}']
        video = f'[0:v]{_video_filter(plan)},fps={fps},format=yuv420p{_fade_chain("", item, duration, video=True)}[v]'
        audio = f"[{0 if keep_audio else 1}:a]{_audio_chain(item, duration)}[a]"
    return [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *inputs,
            '-filter_complex', f'{video};{audio}', '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', preset, '-crf', crf, '-profile:v', 'high',
            '-pix_fmt', 'yuv420p', '-video_track_timescale', '90000',
            '-c:a', 'aac', '-ar', str(SAMPLE_RATE), '-ac', '2', '-b:a', AUDIO_BITRATE,
            '-t', f'{duration:.6f}', '-f', 'mp4', target]


def _concat_line(path: Path) -> str:
    escaped = path.as_posix().replace("'", "\\'")
    return f"file '{escaped}'"


def _assemble_graph(ffmpeg: Path, segments: list[Path], joins: list[dict | None],
                    plan: dict, target: Path) -> list:
    """Fold segments with xfade/acrossfade using measured durations for the offsets."""
    preset, crf = PRESET.get(plan.get('quality'), VIDEO_PRESET), CRF.get(plan.get('quality'), VIDEO_CRF)
    inputs: list[str] = []
    for segment in segments:
        inputs += ['-i', segment]
    parts = []
    for index in range(len(segments)):
        parts.append(f'[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[vsrc{index}]')
        parts.append(f'[{index}:a]asetpts=PTS-STARTPTS[asrc{index}]')
    acc_v, acc_a = 'vsrc0', 'asrc0'
    for index in range(1, len(segments)):
        join = joins[index]
        next_v, next_a = f'vsrc{index}', f'asrc{index}'
        out_v, out_a = f'v{index}', f'a{index}'
        if join:
            parts.append(f'[{acc_v}][{next_v}]xfade=transition={join["type"]}:duration={join["duration"]:.6f}:'
                         f'offset={join["offset"]:.6f}[{out_v}]')
            parts.append(f'[{acc_a}][{next_a}]acrossfade=d={join["duration"]:.6f}[{out_a}]')
        else:
            parts.append(f'[{acc_v}][{next_v}]concat=n=2:v=1:a=0[{out_v}]')
            parts.append(f'[{acc_a}][{next_a}]concat=n=2:v=0:a=1[{out_a}]')
        acc_v, acc_a = out_v, out_a
    return [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *inputs,
            '-filter_complex', ';'.join(parts), '-map', f'[{acc_v}]', '-map', f'[{acc_a}]',
            '-c:v', 'libx264', '-preset', preset, '-crf', crf, '-profile:v', 'high', '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '90000', '-c:a', 'aac', '-ar', str(SAMPLE_RATE), '-ac', '2',
            '-b:a', AUDIO_BITRATE, '-f', 'mp4', target]


def _span(item: dict) -> float:
    """Length of a placed clip, derived from its cut so callers send less state."""
    return round(float(item['out']) - float(item['in']), 6)


def _overlay_command(ffmpeg: Path, base: Path, overlays: list[dict], plan: dict, target: Path) -> list:
    """Composite picture-in-picture overlays onto the assembled main track."""
    preset, crf = PRESET.get(plan.get('quality'), VIDEO_PRESET), CRF.get(plan.get('quality'), VIDEO_CRF)
    inputs: list[str] = ['-i', base]
    for overlay in overlays:
        if overlay.get('still'):
            inputs += ['-loop', '1', '-t', f'{_span(overlay):.6f}', '-i', overlay['source']]
        else:
            inputs += ['-ss', f"{overlay['in']:.6f}", '-t', f'{_span(overlay):.6f}', '-i', overlay['source']]
    parts = []
    label = '0:v'
    output_width, output_height, _ = quality_dimensions(plan)
    scale_x = output_width / int(plan['width'])
    scale_y = output_height / int(plan['height'])
    for index, overlay in enumerate(overlays, start=1):
        rect = overlay['rect']
        # yuv420p compositing needs even box sizes; odd ones are rounded down.
        width = max(2, int(round(rect['w'] * scale_x)) // 2 * 2)
        height = max(2, int(round(rect['h'] * scale_y)) // 2 * 2)
        x, y = int(round(rect['x'] * scale_x)), int(round(rect['y'] * scale_y))
        opacity = int(rect.get('opacity', 100))
        chain = (f'[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,'
                 f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1,format=yuva420p')
        if opacity < 100:
            chain += f',colorchannelmixer=aa={opacity / 100:.4f}'
        chain += f',setpts=PTS-STARTPTS+{overlay["start"]:.6f}/TB[p{index}]'
        parts.append(chain)
        out = f'v{index}'
        parts.append(f'[{label}][p{index}]overlay=x={x}:y={y}:eof_action=pass[{out}]')
        label = out
    return [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *inputs,
            '-filter_complex', ';'.join(parts), '-map', f'[{label}]', '-map', '0:a:0',
            '-c:v', 'libx264', '-preset', preset, '-crf', crf, '-profile:v', 'high', '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '90000', '-c:a', 'copy', '-f', 'mp4', target]


def _sound_command(ffmpeg: Path, base: Path, audios: list[dict], bgm: str | None, volume: int,
                   total: float, plan: dict, target: Path) -> list:
    """Mix extra audio tracks and background music under the main track's own audio."""
    inputs: list[str] = ['-i', base]
    for audio in audios:
        inputs += ['-ss', f"{audio['in']:.6f}", '-t', f'{_span(audio):.6f}', '-i', audio['source']]
    if bgm:
        inputs += ['-stream_loop', '-1', '-i', bgm]
    parts = ['[0:a]aformat=sample_rates=%d:channel_layouts=stereo[base]' % SAMPLE_RATE]
    labels = ['base']
    for index, audio in enumerate(audios, start=1):
        delay = int(round(audio['start'] * 1000))
        parts.append(f'[{index}:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo,'
                     f'{_audio_chain(audio, _span(audio))},adelay={delay}|{delay}[a{index}]')
        labels.append(f'a{index}')
    if bgm:
        parts.append(f'[{len(audios) + 1}:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo,'
                     f'volume={volume / 100:.4f},atrim=0:{total:.6f},asetpts=PTS-STARTPTS[bg]')
        labels.append('bg')
    mixed = f'{len(labels) - 1}'
    parts.append(''.join(f'[{label}]' for label in labels) +
                 f'amix=inputs={len(labels)}:duration=first:normalize=0[{mixed}]')
    return [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *inputs,
            '-filter_complex', ';'.join(parts), '-map', '0:v:0', '-map', f'[{mixed}]',
            '-c:v', 'copy', '-c:a', 'aac', '-ar', str(SAMPLE_RATE), '-ac', '2', '-b:a', AUDIO_BITRATE,
            '-t', f'{total:.6f}', '-movflags', '+faststart', '-f', 'mp4', target]


PROXY_TILES = (6, 4)
PROXY_THUMB = (160, 90)


async def proxies(ffmpeg: Path, source: Path, directory: Path, duration: float, *, with_wave: bool = True) -> None:
    """Generate the thumbnail strip and waveform a timeline needs for one source.

    The images are PNG bytes stored under a non-media suffix so the project library
    never lists them; the caller hands them to the browser as data URLs.
    """
    thumbs, wave = directory / 'thumbs.dat', directory / 'wave.dat'
    if thumbs.is_file() and (wave.is_file() or not with_wave):
        return
    tiles = PROXY_TILES[0] * PROXY_TILES[1]
    rate = max(0.1, min(2.0, tiles / max(1.0, duration or 1.0)))
    await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-i', source, '-frames:v', '1', '-vf',
                f'fps={rate:.4f},scale={PROXY_THUMB[0]}:{PROXY_THUMB[1]},'
                f'tile={PROXY_TILES[0]}x{PROXY_TILES[1]}', '-f', 'image2', '-c:v', 'png', thumbs],
               log_path=None, timeout=SEGMENT_TIMEOUT, action='生成时间线缩略图')
    if with_wave and not wave.is_file():
        await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-i', source, '-frames:v', '1',
                    '-filter_complex', f'showwavespic=s={tiles * PROXY_THUMB[0] // PROXY_TILES[1]}x160:colors=#7fd0ff',
                    '-f', 'image2', '-c:v', 'png', wave],
                   log_path=None, timeout=SEGMENT_TIMEOUT, action='生成时间线波形')


async def waveform(ffmpeg: Path, source: Path, directory: Path) -> None:
    """Generate only an audio waveform for audio-only timeline sources."""
    wave = directory / 'wave.dat'
    if wave.is_file():
        return
    await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-i', source,
                '-frames:v', '1', '-filter_complex', 'showwavespic=s=960x160:colors=#7fd0ff',
                '-f', 'image2', '-c:v', 'png', wave],
               log_path=None, timeout=SEGMENT_TIMEOUT, action='生成音频波形')


def _prune_cache(cache: Path) -> None:
    if not cache.is_dir():
        return
    files = sorted(cache.glob(f'*{SEG_SUFFIX}'), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in files[CACHE_LIMIT:]:
        stale.unlink(missing_ok=True)


async def dialogue_audio(plan: dict, target: Path, log_path: Path | None = None) -> float:
    """Render only audible dialogue sources on the final timeline for ASR."""
    ffmpeg, ffprobe = toolkit()
    placed = []
    cursor = 0.0
    main = plan.get('main') or []
    for index, item in enumerate(main):
        duration = _span(item) if item.get('kind', 'clip') != 'blank' else float(item['out'])
        if item.get('kind', 'clip') != 'blank' and item.get('original', True):
            media = await probe(ffprobe, Path(item['source']), log_path)
            if media.get('has_audio'):
                placed.append((item, cursor, duration))
        cursor += duration
        transition = item.get('transition') or {}
        if index + 1 < len(main):
            cursor -= min(float(transition.get('duration', 0)), duration, _span(main[index + 1]) if main[index + 1].get('kind', 'clip') != 'blank' else float(main[index + 1]['out']))
    for item in plan.get('audios') or []:
        media = await probe(ffprobe, Path(item['source']), log_path)
        if media.get('has_audio'):
            placed.append((item, float(item.get('start', 0)), _span(item)))
    if not placed:
        raise ValueError('时间线中没有可识别的声音；请保留视频原声或添加语音素材')
    inputs, filters, labels = [], [], []
    for index, (item, start, duration) in enumerate(placed):
        inputs += ['-ss', f"{float(item.get('in', 0)):.6f}", '-t', f'{duration:.6f}', '-i', item['source']]
        label = f'a{index}'
        chain = _audio_chain(item, duration)
        delay = max(0, int(round(start * 1000)))
        filters.append(f'[{index}:a]{chain},aformat=sample_rates=16000:channel_layouts=mono,'
                       f'adelay={delay}:all=1[{label}]')
        labels.append(label)
    total = max(cursor, max(start + duration for _, start, duration in placed))
    filters.append(''.join(f'[{label}]' for label in labels) +
                   f'amix=inputs={len(labels)}:duration=longest:normalize=0,alimiter=limit=0.95,'
                   f'atrim=0:{total:.6f},asetpts=N/SR/TB[out]')
    await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *inputs,
                '-filter_complex', ';'.join(filters), '-map', '[out]', '-ac', '1', '-ar', '16000',
                '-c:a', 'pcm_s16le', target], log_path=log_path, timeout=MIX_TIMEOUT,
               action='生成全时间线字幕识别音频')
    return total


async def compose(plan: dict, report: Callable[[int], Any], log_path: Path) -> None:
    """Render the resolved timeline in ``plan`` to ``plan['output']``."""
    ffmpeg, ffprobe = toolkit()
    main = plan['main']
    if not main:
        raise ValueError('成片没有任何镜头，无法合成')
    quality = plan.get('quality', 'final')
    output = Path(plan['output'])
    work = output.parent / 'segments'
    work.mkdir(parents=True, exist_ok=True)
    cache = Path(plan['cache_dir']) if plan.get('cache_dir') else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    # 1. Normalise every main-track item and measure what it actually became.
    segments: list[Path] = []
    joins: list[dict | None] = []
    measured: list[float] = []
    total = 0.0
    for index, item in enumerate(main):
        media = None
        if item.get('kind', 'clip') != 'blank':
            media = await probe(ffprobe, Path(item['source']), log_path)
            if item.get('still'):
                media['duration'] = duration = float(item['out']) - float(item.get('in', 0))
                media['has_video'] = True
            validate(item, media)
        duration = round(float(item['out']) - (0.0 if item.get('kind', 'clip') == 'blank' else float(item['in'])), 6)
        if duration <= 0:
            raise ValueError(f'第 {index + 1} 段时长无效')
        key = segment_key(item, plan)
        segment = work / f'seg_{index:03d}{SEG_SUFFIX}'
        cached = cache / f'{key}{SEG_SUFFIX}' if cache else None
        if cached and cached.is_file():
            shutil.copyfile(cached, segment)
        else:
            await _run(_segment_command(ffmpeg, item, plan, segment, duration, media),
                       log_path=log_path, timeout=SEGMENT_TIMEOUT, action=f'第 {index + 1} 段标准化')
            if cached:
                shutil.copyfile(segment, cached)
        if not segment.is_file():
            raise ValueError(f'第 {index + 1} 段未生成标准化片段')
        actual = (await probe(ffprobe, segment, log_path))['duration'] or duration
        join = main[index - 1].get('transition') if index else None
        if join:
            overlap = min(float(join['duration']), measured[-1], actual)
            joins.append({'type': join['type'], 'duration': round(overlap, 6), 'offset': 0.0})
        else:
            joins.append(None)
        measured.append(actual)
        segments.append(segment)
        report(int(60 * (index + 1) / len(main)))

    # 2. Offsets come from measured durations, never from the nominal cut length.
    timeline = measured[0]
    for index in range(1, len(segments)):
        join = joins[index]
        if join:
            join['offset'] = round(timeline - join['duration'], 6)
            timeline += measured[index] - join['duration']
        else:
            timeline += measured[index]
    if timeline <= 0:
        raise ValueError('成片时长无效')

    # 3. Join the main track.
    joined = output.parent / f'joined{SEG_SUFFIX}'
    if any(joins[1:]):
        await _run(_assemble_graph(ffmpeg, segments, joins, plan, joined),
                   log_path=log_path, timeout=MIX_TIMEOUT, action='按时间线拼接并应用转场')
    else:
        list_path = output.parent / 'concat.txt'
        list_path.write_text('\n'.join(_concat_line(segment) for segment in segments) + '\n', encoding='utf-8')
        await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
                    '-f', 'concat', '-safe', '0', '-i', list_path, '-c', 'copy', '-f', 'mp4', joined],
                   log_path=log_path, timeout=MIX_TIMEOUT, action='按时间线拼接')
    report(72)

    result = joined
    # 4. Overlay track (picture in picture), placed on the measured timeline.
    overlays = [item for item in plan.get('overlays') or [] if item.get('rect')]
    if overlays:
        for overlay in overlays:
            media = await probe(ffprobe, Path(overlay['source']), log_path)
            if overlay.get('still'):
                media['duration'] = _span(overlay)
                media['has_video'] = True
            validate(overlay, media)
        layered = output.parent / f'layered{SEG_SUFFIX}'
        await _run(_overlay_command(ffmpeg, result, overlays, plan, layered),
                   log_path=log_path, timeout=MIX_TIMEOUT, action='叠加轨合成')
        result = layered
        report(80)

    # 5. Extra audio tracks and background music in one mix.
    audios = plan.get('audios') or []
    bgm = plan.get('bgm_path')
    if audios or bgm:
        for audio in audios:
            validate_audio(audio, await probe(ffprobe, Path(audio['source']), log_path))
        mixed = output.parent / f'mixed{SEG_SUFFIX}'
        await _run(_sound_command(ffmpeg, result, audios, bgm, int(plan.get('volume', 0)), timeline, plan, mixed),
                   log_path=log_path, timeout=MIX_TIMEOUT, action='音轨与背景音乐混音')
        result = mixed
        report(90)

    # 6. Burn the editable subtitle track only at export time. The browser can keep
    # editing plain JSON while preview and final output use the same ASS renderer.
    captions = [item for item in plan.get('captions') or [] if str(item.get('text', '')).strip()]
    texts = [item for item in plan.get('texts') or [] if str(item.get('text', '')).strip()]
    ass_path = Path(plan['captions_path']) if plan.get('captions_path') else None
    if (captions or texts) and ass_path:
        write_ass(ass_path, captions, texts, width=int(plan['width']), height=int(plan['height']))
        captioned = output.parent / f'captioned{SEG_SUFFIX}'
        await _run(_subtitle_command(ffmpeg, result, ass_path, plan, captioned),
                   log_path=log_path, timeout=MIX_TIMEOUT, action='烧录字幕')
        result = captioned
        report(94)

    # 7. Publish with faststart, then verify before the caller renames it.
    published = output.parent / f'published{SEG_SUFFIX}'
    await _run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', '-i', result,
                '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', published],
               log_path=log_path, timeout=MIX_TIMEOUT, action='发布成片文件')

    final = await probe(ffprobe, published, log_path)
    if not final['has_video'] or not final['has_audio']:
        raise ValueError('成片校验失败：输出缺少视频轨或音频轨')
    tolerance = min(5.0, 0.5 + 0.02 * len(segments))
    if final['duration'] is None or abs(final['duration'] - timeline) > tolerance:
        expected = f'{timeline:.2f}'
        actual = f'{final["duration"]:.2f}' if final['duration'] is not None else '未知'
        raise ValueError(f'成片校验失败：预期时长 {expected}s，实际 {actual}s')
    width, height, _ = quality_dimensions(plan)
    if (final['width'], final['height']) != (width, height):
        raise ValueError(f'成片校验失败：预期画幅 {width}x{height}，实际 {final["width"]}x{final["height"]}')
    published.replace(output)

    for path in [joined, output.parent / f'layered{SEG_SUFFIX}', output.parent / f'mixed{SEG_SUFFIX}',
                 output.parent / f'captioned{SEG_SUFFIX}',
                 output.parent / 'concat.txt']:
        path.unlink(missing_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    if cache:
        _prune_cache(cache)
    plan['timeline_duration'] = round(timeline, 3)
