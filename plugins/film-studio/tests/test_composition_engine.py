"""Real FFmpeg regressions for the editing timeline engine.

Run from the repository root:

    python -m unittest discover -s plugins/film-studio/tests -p 'test_*.py'

The suite uses the FFmpeg and FFprobe executables installed on system PATH.
"""
import array
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import asyncio
import json
import unittest
from unittest.mock import patch

from backend.modules.generation.plugins import PluginCatalog
from backend.modules.projects.service import ProjectService
from backend.modules.shared.application_runtime import ApplicationRuntime
from backend.persistence.database import Database

ROOT = Path(__file__).resolve().parents[3]
CATALOG = PluginCatalog(ROOT / 'plugins')
ACTION = CATALOG.actions()['film.save']
CompositionService = CATALOG._load_handler(ACTION, 'service.py:CompositionService')
render = sys.modules[CompositionService.__module__].render

try:
    FFMPEG, FFPROBE = render.toolkit()
except ValueError:
    FFMPEG = FFPROBE = None

needs_toolkit = unittest.skipUnless(FFMPEG is not None, '系统 PATH 中未安装 FFmpeg/ffprobe')


class ComfyWhisperTests(unittest.TestCase):
    def setUp(self):
        self.catalog = PluginCatalog(ROOT / 'plugins')
        self.action = self.catalog.actions()['film.transcribe']
        self.whisper_type = self.catalog._load_handler(self.action, 'asr.py:ComfyWhisper')

    def test_api_chinese_language_is_mapped_to_comfyui_enum(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'voice.wav'
            source.write_bytes(b'fake audio')
            runtime = SimpleNamespace(comfyui_upload=lambda *_args: 'input/voice.wav')
            requests = []

            def request(path, method='GET', body=None):
                if path == '/prompt':
                    workflow = json.loads(body)['prompt']
                    requests.append(workflow['2']['inputs']['language'])
                    return {'prompt_id': 'prompt-1'}
                return {'prompt-1': {
                    'status': {'completed': True},
                    'outputs': {'3': {'text': '[{"text":"你好","start":0,"end":1}]'}},
                }}

            runtime.comfyui_request = request
            result = asyncio.run(self.whisper_type(runtime).transcribe(source, language='zh'))

        self.assertEqual(requests, ['Chinese'])
        self.assertEqual(result, [{'text': '你好', 'start': 0.0, 'end': 1.0}])

    def test_whisper_prompt_defaults_to_language_specific_transcription_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'voice.wav'
            source.write_bytes(b'fake audio')
            runtime = SimpleNamespace(comfyui_upload=lambda *_args: 'input/voice.wav')
            received = {}

            def request(path, method='GET', body=None):
                workflow = json.loads(body)['prompt']
                received.update(workflow['2']['inputs'])
                return {'prompt_id': 'prompt-1'}

            runtime.comfyui_request = request
            with self.assertRaisesRegex(RuntimeError, '超时'):
                asyncio.run(self.whisper_type(runtime).transcribe(source, language='zh', timeout=0))

        self.assertIn('简体中文转写', received['prompt'])
        self.assertEqual(received['language'], 'Chinese')

    def test_chinese_normalization_requires_opencc_and_handles_locale_case(self):
        from types import ModuleType
        module = sys.modules[self.whisper_type.__module__]

        fake_opencc = ModuleType('opencc')
        fake_opencc.OpenCC = lambda config: SimpleNamespace(convert=lambda text: f'{config}:{text}')
        with patch.dict('sys.modules', {'opencc': fake_opencc}):
            self.assertEqual(module.normalize_text('測試', 'zh-cn'), 't2s:測試')
        with patch.dict('sys.modules', {'opencc': None}):
            with self.assertRaisesRegex(RuntimeError, 'opencc-python-reimplemented'):
                module.normalize_text('測試', 'zh')

    def test_auto_language_and_validation_errors_are_not_reported_as_missing_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'voice.wav'
            source.write_bytes(b'fake audio')
            languages = []
            runtime = SimpleNamespace(comfyui_upload=lambda *_args: 'input/voice.wav')

            def request(path, method='GET', body=None):
                if path == '/prompt':
                    workflow = json.loads(body)['prompt']
                    languages.append(workflow['2']['inputs']['language'])
                    return {'prompt_id': 'prompt-1'}
                return {'prompt-1': {
                    'status': {'completed': True},
                    'outputs': {'3': {'text': '[{"text":"hello","start":0,"end":1}]'}},
                }}

            runtime.comfyui_request = request
            whisper = self.whisper_type(runtime)
            result = asyncio.run(whisper.transcribe(source, language='auto'))
            self.assertTrue(result)
            self.assertEqual(languages, ['auto'])

            failing_runtime = SimpleNamespace(
                comfyui_upload=lambda *_args: 'input/voice.wav',
                comfyui_request=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError('Invalid input for node 2 Apply Whisper class_type: language must be Chinese')),
            )
            with self.assertRaisesRegex(RuntimeError, 'ComfyUI 拒绝字幕识别任务.*Invalid input') as raised:
                asyncio.run(self.whisper_type(failing_runtime).transcribe(source, language='zh'))
            self.assertNotIn('节点未正确加载', str(raised.exception))


def tool(*args) -> bytes:
    """Run the installed ffmpeg with an argument array and return stdout."""
    result = subprocess.run([str(FFMPEG), '-hide_banner', '-nostdin', '-loglevel', 'error', *map(str, args)],
                            capture_output=True)
    if result.returncode:
        raise AssertionError(f'FFmpeg 夹具失败：{result.stderr.decode("utf-8","replace")[-1000:]}')
    return result.stdout


def scratch() -> tempfile.TemporaryDirectory:
    """夹具临时目录放在仓库内 tests/.tmp（可用 FILM_TEST_TMP 覆盖）。

    部分 Windows 机器的安全软件会拦截未签名的 ffmpeg.exe 向 %TEMP% 写文件
    （报 Permission denied），仓库内路径不受影响，也便于事后排查。
    """
    base = Path(os.environ.get('FILM_TEST_TMP') or ROOT / 'tests' / '.tmp')
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


def encode(target: Path, video: str, audio: str | None = None) -> Path:
    args = ['-y', '-f', 'lavfi', '-i', video]
    if audio:
        args += ['-f', 'lavfi', '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-shortest']
    else:
        args += ['-an']
    tool(*args, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', target)
    return target


@needs_toolkit
class TimelineEngineTests(unittest.TestCase):
    """Engine-level coverage: probing, normalising, joins, transitions, overlays, mixing."""

    def setUp(self):
        temporary = scratch()
        self.addCleanup(temporary.cleanup)
        # 中文与空格路径必须和 ASCII 路径表现一致。
        self.work = Path(temporary.name) / '镜头 输出 目录'
        self.work.mkdir()
        self.log = self.work / 'render.log'
        self.progress = []

    def clip(self, name: str, video: str, audio: str | None, start: float, end: float, **fields) -> dict:
        item = {'kind': 'clip', 'job_id': name, 'artifact_index': 0,
                'source': str(encode(self.work / name, video, audio)), 'in': start, 'out': end, 'original': True}
        item.update(fields)
        return item

    def compose(self, main: list[dict], **overrides) -> Path:
        plan = {'main': main, 'overlays': [], 'audios': [], 'bgm_path': None, 'volume': 18,
                'output': str(self.work / '.final.partial.mp4'), 'cache_dir': str(self.work / '_cache'),
                'width': 1280, 'height': 720, 'fps': 30, 'fit': 'contain'}
        plan.update(overrides)
        asyncio.run(render.compose(plan, self.progress.append, self.log))
        output = Path(plan['output'])
        self.assertTrue(output.is_file())
        return output

    def probe(self, path: Path) -> dict:
        return asyncio.run(render.probe(FFPROBE, path, self.log))

    def amplitude(self, path: Path, start: float, window: float = 0.3) -> int:
        raw = tool('-ss', start, '-i', path, '-t', window, '-f', 's16le', '-ac', '1', '-ar', '8000', '-')
        samples = array.array('h', raw)
        return max((abs(value) for value in samples), default=0)

    def pixel(self, path: Path, x: int, y: int, at: float = 0.2) -> tuple:
        raw = tool('-ss', at, '-i', path, '-frames:v', '1', '-vf', f'crop=2:2:{x}:{y}',
                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-')
        return tuple(raw[:3])

    def assert_color(self, path: Path, x: int, y: int, *, channel: str, at: float = 0.2) -> None:
        """YUV round-tripping shifts pure colours slightly, so check the range."""
        red, green, blue = self.pixel(path, x, y, at)
        rgb = {'red': (red, green, blue), 'green': (green, red, blue), 'blue': (blue, red, green)}[channel]
        self.assertGreater(rgb[0], 200, (channel, (red, green, blue)))
        self.assertLess(rgb[1], 60, (channel, (red, green, blue)))
        self.assertLess(rgb[2], 60, (channel, (red, green, blue)))

    def test_mixed_specs_are_normalised_and_concatenated(self):
        main = [self.clip('甲 4x3.mp4', 'color=c=red:s=160x120:r=24:d=1', 'sine=frequency=440:duration=1', 0, 0.6),
                self.clip('乙 hd 60fps.mp4', 'color=c=blue:s=1920x1080:r=60:d=1', None, 0.2, 1.0)]
        final = self.compose(main)
        media = self.probe(final)
        self.assertEqual((media['width'], media['height']), (1280, 720))
        self.assertTrue(media['has_audio'])
        self.assertAlmostEqual(media['duration'], 1.4, delta=0.3)
        self.assertEqual(self.progress, sorted(self.progress))
        self.assertEqual(self.progress[-1], 72)
        # contain 保留完整画面，4:3 素材左右留黑边。
        self.assertLess(max(self.pixel(final, 5, 360)), 16)
        self.assert_color(final, 640, 360, channel='red')

    def test_cover_fit_fills_the_frame(self):
        main = [self.clip('cover.mp4', 'color=c=red:s=160x120:r=24:d=1', None, 0, 0.5)]
        final = self.compose(main, width=720, height=720, fit='cover')
        self.assertEqual((self.probe(final)['width'], self.probe(final)['height']), (720, 720))
        self.assert_color(final, 4, 4, channel='red')

    def test_blank_gap_extends_the_timeline(self):
        main = [self.clip('first.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 0.5),
                {'kind': 'blank', 'out': 1.0},
                self.clip('second.mp4', 'color=c=blue:s=160x90:r=24:d=1', None, 0, 0.5)]
        final = self.compose(main)
        self.assertAlmostEqual(self.probe(final)['duration'], 2.0, delta=0.3)
        self.assertLess(max(self.pixel(final, 640, 360, at=1.0)), 16)
        self.assert_color(final, 640, 360, channel='blue', at=1.8)

    def test_blank_can_transition_into_video(self):
        main = [self.clip('first.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 0.5),
                {'kind': 'blank', 'out': 0.5, 'transition': {'type': 'fade', 'duration': 0.2}},
                self.clip('second.mp4', 'color=c=blue:s=160x90:r=24:d=1', None, 0, 0.5)]
        final = self.compose(main)
        self.assertAlmostEqual(self.probe(final)['duration'], 1.3, delta=0.15)

    def test_transition_blends_two_segments(self):
        main = [self.clip('red.mp4', 'color=c=red:s=160x90:r=24:d=1', 'sine=frequency=440:duration=1', 0, 1,
                          transition={'type': 'fade', 'duration': 0.4}),
                self.clip('blue.mp4', 'color=c=blue:s=160x90:r=24:d=1', 'sine=frequency=880:duration=1', 0, 1)]
        final = self.compose(main)
        # 转场吃掉两侧素材，总时长精确等于两段之和减去重叠。
        self.assertAlmostEqual(self.probe(final)['duration'], 1.6, delta=0.15)
        red, green, blue = self.pixel(final, 640, 360, at=0.8)
        self.assertGreater(red, 60)
        self.assertGreater(blue, 60)

    def test_overlay_is_placed_at_its_absolute_start(self):
        overlay = self.clip('画中画.mp4', 'color=c=blue:s=160x90:r=24:d=2', None, 0.5, 1.5)
        overlay.update({'start': 0.5, 'rect': {'x': 0, 'y': 0, 'w': 240, 'h': 135, 'opacity': 100}})
        main = [self.clip('base.mp4', 'color=c=red:s=160x90:r=24:d=2', None, 0, 2)]
        final = self.compose(main, overlays=[overlay])
        self.assertAlmostEqual(self.probe(final)['duration'], 2.0, delta=0.3)
        self.assert_color(final, 60, 60, channel='blue', at=1.0)
        self.assert_color(final, 60, 60, channel='red', at=0.1)
        self.assert_color(final, 1000, 600, channel='red', at=1.0)

    def test_extra_audio_track_is_delayed_to_its_start(self):
        voice = self.clip('配音.mp4', 'color=c=black:s=16x16:r=24:d=1', 'sine=frequency=1000:duration=1', 0.2, 0.7)
        voice['start'] = 1.0
        main = [self.clip('silent base.mp4', 'color=c=red:s=160x90:r=24:d=2', None, 0, 2)]
        final = self.compose(main, audios=[voice])
        self.assertLess(self.amplitude(final, 0.2), 10)
        self.assertGreater(self.amplitude(final, 1.3), 100)
        self.assertLess(self.amplitude(final, 1.9), 10)

    def test_per_clip_volume_and_fades(self):
        source = self.clip('audio.mp4', 'color=c=red:s=160x90:r=24:d=1', 'sine=frequency=440:duration=1', 0, 1)
        loud = self.compose([{**source, 'volume': 100}], output=str(self.work / 'loud.mp4'))
        quiet = self.compose([{**source, 'volume': 0}], output=str(self.work / 'quiet.mp4'))
        faded = self.compose([{**source, 'fade_in': 0.6, 'fade_out': 0.6}], output=str(self.work / 'faded.mp4'))
        self.assertGreater(self.amplitude(loud, 0.4), 100)
        self.assertLess(self.amplitude(quiet, 0.4), 10)
        self.assertLess(self.amplitude(faded, 0.0, 0.05) * 4, self.amplitude(faded, 0.4, 0.1))
        self.assertGreater(self.amplitude(faded, 0.4, 0.1), 100)

    def test_source_without_audio_gets_silence(self):
        main = [self.clip('silent.mp4', 'color=c=green:s=160x90:r=24:d=1', None, 0, 0.8)]
        final = self.compose(main)
        self.assertTrue(self.probe(final)['has_audio'])
        self.assertLess(self.amplitude(final, 0.3), 10)

    def test_original_audio_is_per_clip(self):
        source = self.clip('audio.mp4', 'color=c=red:s=160x90:r=24:d=1', 'sine=frequency=440:duration=1', 0, 1)
        final = self.compose([{**source, 'original': False}, {**source, 'original': True}])
        self.assertLess(self.amplitude(final, 0.3), 10)
        self.assertGreater(self.amplitude(final, 1.3), 100)

    def test_bgm_loops_and_is_truncated_to_the_film(self):
        bgm = encode(self.work / '背景音乐 loop.mp4', 'color=c=black:s=16x16:r=24:d=0.2', 'sine=frequency=220:duration=0.3')
        final = self.compose([self.clip('long.mp4', 'color=c=red:s=160x90:r=24:d=2', None, 0, 2)],
                             bgm_path=str(bgm), volume=60)
        self.assertAlmostEqual(self.probe(final)['duration'], 2.0, delta=0.3)
        self.assertGreater(self.amplitude(final, 1.6), 100)
        self.assertEqual(self.progress[-1], 90)

    def test_zero_volume_bgm_stays_silent(self):
        bgm = encode(self.work / 'bgm.mp4', 'color=c=black:s=16x16:r=24:d=0.2', 'sine=frequency=220:duration=0.2')
        final = self.compose([self.clip('quiet.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 1)],
                             bgm_path=str(bgm), volume=0)
        self.assertLess(self.amplitude(final, 0.5), 10)

    def test_dialogue_audio_follows_timeline_and_excludes_bgm(self):
        voiced = self.clip('对白.mp4', 'color=c=black:s=16x16:r=24:d=1',
                           'sine=frequency=440:duration=1', 0, 0.5)
        voice = self.clip('补充对白.mp4', 'color=c=black:s=16x16:r=24:d=1',
                          'sine=frequency=880:duration=1', 0, 0.5)
        voice['start'] = 1.0
        bgm = encode(self.work / '不应识别的背景音乐.mp4', 'color=c=black:s=16x16:r=24:d=2',
                     'sine=frequency=220:duration=2')
        target = self.work / 'dialogue.wav'
        duration = asyncio.run(render.dialogue_audio({
            'main': [voiced, {'kind': 'blank', 'out': 1.0}],
            'audios': [voice], 'bgm_path': str(bgm),
        }, target, self.log))
        self.assertAlmostEqual(duration, 1.5, delta=0.05)
        self.assertGreater(self.amplitude(target, 0.2), 100)
        self.assertLess(self.amplitude(target, 0.7), 10)
        self.assertGreater(self.amplitude(target, 1.2), 100)

    def test_captions_and_positioned_text_are_burned_together(self):
        source = self.clip('黑底.mp4', 'color=c=black:s=720x720:r=24:d=1', None, 0, 1)
        ass = self.work / 'captions.ass'
        final = self.compose(
            [source], width=720, height=720, captions_path=str(ass),
            captions=[{'text': 'CAPTION', 'start': 0, 'end': 1}],
            texts=[{'text': 'TEXT', 'start': 0, 'end': 1, 'x': 360, 'y': 240,
                    'font_size': 96, 'color': '#FFFFFF'}],
        )
        content = ass.read_text(encoding='utf-8-sig')
        self.assertIn(r'\an5\pos(360,240)\fs96', content)
        self.assertEqual(content.count('Dialogue:'), 2)
        raw = tool('-ss', '0.5', '-i', final, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-')
        width = 720
        center = sum(value > 180 for y in range(170, 310) for value in raw[y * width + 220:y * width + 500])
        bottom = sum(value > 180 for y in range(580, 700) for value in raw[y * width + 120:y * width + 600])
        self.assertGreater(center, 100)
        self.assertGreater(bottom, 100)

    def test_audio_shorter_than_the_cut_keeps_the_full_length(self):
        source = self.work / '短音轨.mp4'
        tool('-y', '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=24:d=2',
             '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.5', '-map', '0:v:0', '-map', '1:a:0',
             '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', source)
        final = self.compose([{'kind': 'clip', 'job_id': 'short-audio', 'artifact_index': 0, 'source': str(source),
                               'in': 0, 'out': 2, 'original': True}])
        self.assertAlmostEqual(self.probe(final)['duration'], 2.0, delta=0.3)

    def test_preview_quality_is_smaller_and_faster(self):
        main = [self.clip('big.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 1)]
        final = self.compose(main, width=1920, height=1080)
        preview = self.compose(main, width=1920, height=1080, quality='preview',
                               output=str(self.work / 'preview.mp4'))
        self.assertEqual((self.probe(final)['width'], self.probe(final)['height']), (1920, 1080))
        self.assertEqual((self.probe(preview)['width'], self.probe(preview)['height']), (852, 480))

    def test_segment_cache_is_reused(self):
        main = [self.clip('cached.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 0.5)]
        self.compose(main)
        cache = self.work / '_cache'
        self.assertEqual(len(list(cache.glob('*.seg'))), 1)
        stamp = next(cache.glob('*.seg')).stat().st_mtime_ns
        self.compose(main)
        self.assertEqual(next(cache.glob('*.seg')).stat().st_mtime_ns, stamp)
        self.compose([{**main[0], 'out': 0.4}])
        self.assertEqual(len(list(cache.glob('*.seg'))), 2)

    def test_out_of_range_cut_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.compose([self.clip('short.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 9.5)])
        self.assertIn('超过素材实际时长', str(raised.exception))

    def test_cut_starting_past_the_source_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.compose([self.clip('short.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0.999, 1.0)])
        self.assertIn('裁剪起点', str(raised.exception))

    def test_corrupt_source_is_rejected(self):
        broken = self.work / 'broken.mp4'
        broken.write_text('not a video', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.compose([{'kind': 'clip', 'job_id': 'broken', 'artifact_index': 0, 'source': str(broken),
                           'in': 0, 'out': 1, 'original': True}])

    def test_image_only_source_is_rejected(self):
        audio_only = self.work / '只有声音.mp4'
        tool('-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'aac', audio_only)
        with self.assertRaises(ValueError) as raised:
            self.compose([{'kind': 'clip', 'job_id': 'audio', 'artifact_index': 0, 'source': str(audio_only),
                           'in': 0, 'out': 0.5, 'original': True}])
        self.assertIn('没有视频轨', str(raised.exception))

    def test_audio_track_without_audio_stream_is_rejected(self):
        silent = self.work / '无声视频.mp4'
        encode(silent, 'color=c=red:s=16x16:r=24:d=1', None)
        with self.assertRaises(ValueError) as raised:
            self.compose([self.clip('base.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 0.5)],
                         audios=[{'kind': 'clip', 'job_id': 'silent', 'artifact_index': 0, 'source': str(silent),
                                   'in': 0, 'out': 0.5, 'start': 0}])
        self.assertIn('没有音频轨', str(raised.exception))

    def test_intermediate_files_are_cleaned_after_success(self):
        final = self.compose([self.clip('clean.mp4', 'color=c=red:s=160x90:r=24:d=1', None, 0, 0.5)])
        self.assertFalse((self.work / 'segments').exists())
        self.assertFalse((self.work / 'joined.seg').exists())
        self.assertFalse((self.work / 'concat.txt').exists())
        self.assertTrue(final.is_file())


@needs_toolkit
class TimelineTaskTests(unittest.TestCase):
    """Service-level coverage: pre-flight rejection, queueing, preview, proxies, cleanup."""

    def setUp(self):
        temporary = scratch()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.db = Database(root / 'test.sqlite')
        self.db.initialize({})
        self.context = SimpleNamespace(db=self.db, jobs={}, library_cache={}, application_tasks={},
                                       application_semaphores={}, paths=SimpleNamespace(
                                           root=ROOT, projects=root / '项目 素材 目录'))
        self.projects = ProjectService(self.context)
        self.project = self.projects.create('成片 回归')['id']
        self.runtime = ApplicationRuntime(self.context, 'film-studio')
        self.service = CompositionService(self.runtime)

    def add_job(self, job_id: str, *, audio: bool = True, kind: str = 'video') -> dict:
        directory = self.projects.ensure_directory(self.db.project(self.project))
        video = kind == 'video'
        path = directory / ('videos' if video else 'audio') / f'{job_id}{".mp4" if video else ".m4a"}'
        path.parent.mkdir(parents=True, exist_ok=True)
        if video:
            encode(path, 'color=c=red:s=160x120:r=24:d=1', 'sine=frequency=440:duration=1' if audio else None)
        else:
            tool('-y', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=0.3', '-c:a', 'aac', path)
        job = {'id': job_id, 'kind': kind, 'status': 'completed', 'created_at': 1, 'request': {},
               'project_id': self.project}
        self.db.insert_job(job)
        self.db.update_job(job_id, {'artifacts_json': json.dumps(
            [{'name': path.name, 'project_path': path.relative_to(self.context.paths.projects).as_posix()}])})
        return self.db.job(job_id)

    def body(self, job_id: str, **overrides) -> dict:
        plan = {'name': '回归成片', 'clips': [{'job_id': job_id, 'artifact_index': 0, 'in': 0, 'out': 0.6,
                                              'original': True}],
                'bgm_job_id': None, 'volume': 18, 'width': 1280, 'height': 720, 'fps': 30, 'fit': 'contain'}
        plan.update(overrides)
        return plan

    def run_task(self, film_id: str, quality: str = 'final') -> dict:
        async def render_once():
            await self.service.submit(self.project, film_id, quality)
            await next(iter(self.context.application_tasks.values()))
            return self.service.get(self.project, film_id)
        return asyncio.run(render_once())

    def test_submit_rejects_broken_source_before_queueing(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one', clips=[{'job_id': 'video-one',
                                                                            'artifact_index': 0, 'in': 0,
                                                                            'out': 30, 'original': True}]))
        with self.assertRaises(ValueError):
            asyncio.run(self.service.submit(self.project, film['id']))
        self.assertEqual(self.context.application_tasks, {})
        self.assertEqual(self.service.get(self.project, film['id'])['render']['status'], 'draft')

    def test_validate_reports_issues_without_queueing(self):
        empty = self.service.save(self.project, {'name': '空时间线'})
        invalid = asyncio.run(self.service.validate(self.project, empty['id']))
        self.assertFalse(invalid['valid'])
        self.assertEqual(invalid['issues'], ['主轨没有素材'])
        self.assertFalse(self.context.application_tasks)

        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one'))
        valid = asyncio.run(self.service.validate(self.project, film['id']))
        self.assertTrue(valid['valid'], valid['issues'])
        self.assertEqual(valid['summary']['clips'], 1)
        self.assertEqual(valid['summary']['output'], '1280x720@30fps')
        self.assertFalse(self.context.application_tasks)

    def test_save_allows_omitted_name_on_existing_film(self):
        film = self.service.save(self.project, {'name': 'partial update', 'clips': []})
        updated = self.service.save(self.project, {'volume': 27}, film['id'])
        self.assertEqual(updated['name'], 'partial update')
        self.assertEqual(updated['volume'], 27)
        self.assertNotIn('name', ACTION['input_schema']['properties']['plan'].get('required', []))

    def test_transcription_is_queued_and_persisted_for_polling(self):
        async def scenario():
            film = self.service.save(self.project, {'name': 'async transcription', 'clips': []})
            self.service.plugin_runtime = object()

            async def fake_transcribe(project_id, film_id, language, model):
                result = self.service.get(project_id, film_id)
                result['captions'] = [{'text': '简体字幕', 'start': 0, 'end': 1}]
                return result

            with patch.object(self.service, 'transcribe', side_effect=fake_transcribe):
                queued = await self.service.queue_transcribe(self.project, film['id'])
                self.assertEqual(queued['transcribe']['status'], 'queued')
                await next(iter(self.context.application_tasks.values()))
            return film['id']

        film_id = asyncio.run(scenario())

        completed = self.service.get(self.project, film_id)
        self.assertEqual(completed['transcribe']['status'], 'completed')
        self.assertEqual(completed['captions'][0]['text'], '简体字幕')
        self.assertFalse(self.context.application_tasks)

    def test_recovery_marks_interrupted_transcription_failed(self):
        film = self.service.save(self.project, {'name': 'interrupted transcription', 'clips': []})
        film['transcribe'] = {'status': 'running', 'progress': 5}
        self.service.persist(film)
        self.service.recover()
        recovered = self.service.get(self.project, film['id'])
        self.assertEqual(recovered['transcribe']['status'], 'failed')
        self.assertIn('网关重启', recovered['transcribe']['error'])

    def test_transcription_failure_is_pollable_and_blocks_edits_while_running(self):
        async def scenario():
            film = self.service.save(self.project, {'name': 'transcription state', 'clips': []})
            self.service.plugin_runtime = object()
            started, release = asyncio.Event(), asyncio.Event()

            async def failing_transcribe(*_args):
                started.set()
                await release.wait()
                raise RuntimeError('Whisper unavailable')

            with patch.object(self.service, 'transcribe', side_effect=failing_transcribe):
                await self.service.queue_transcribe(self.project, film['id'])
                await started.wait()
                with self.assertRaisesRegex(RuntimeError, '任务进行中'):
                    self.service.save(self.project, {'volume': 20}, film['id'])
                release.set()
                await next(iter(self.context.application_tasks.values()))
            failed = self.service.get(self.project, film['id'])
            self.assertEqual(failed['transcribe']['status'], 'failed')
            self.assertEqual(failed['transcribe']['error'], 'Whisper unavailable')

        asyncio.run(scenario())

    def test_render_publishes_final_and_keeps_history(self):
        self.add_job('video-one')
        self.add_job('bgm-one', audio=True, kind='music')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one', bgm_job_id='bgm-one'))
        completed = self.run_task(film['id'])
        self.assertEqual(completed['render']['status'], 'completed', completed['render'].get('error'))
        self.assertEqual(len(completed['renders']), 1)
        self.assertEqual(completed['stages']['composition']['status'], 'completed')
        final = next(self.context.paths.projects.rglob('final.mp4'))
        media = asyncio.run(render.probe(FFPROBE, final))
        self.assertEqual((media['width'], media['height'], media['has_audio']), (1280, 720, True))
        run_directory = final.parent
        self.assertFalse((run_directory / 'segments').exists())
        self.assertTrue((run_directory / 'plan.json').is_file())
        self.assertFalse(self.context.application_tasks)

    def test_timeline_plan_renders_blanks_transitions_and_tracks(self):
        self.add_job('video-one')
        self.add_job('voice-one', kind='music')
        self.service.select('video-one', True)
        clip = {'job_id': 'video-one', 'artifact_index': 0, 'in': 0, 'out': 0.6, 'original': True}
        plan = self.body('video-one', clips=[{**clip, 'transition': {'type': 'fade', 'duration': 0.2}},
                                             {'kind': 'blank', 'out': 0.4}, clip],
                         overlay_clips=[{**clip, 'start': 0.2, 'rect': {'x': 0, 'y': 0, 'w': 320, 'h': 180}}],
                         audio_clips=[{'job_id': 'voice-one', 'artifact_index': 0, 'in': 0, 'out': 0.3,
                                       'start': 0.5, 'volume': 80}])
        film = self.service.save(self.project, plan)
        completed = self.run_task(film['id'])
        self.assertEqual(completed['render']['status'], 'completed', completed['render'].get('error'))
        final = next(self.context.paths.projects.rglob('final.mp4'))
        media = asyncio.run(render.probe(FFPROBE, final))
        self.assertEqual((media['width'], media['height'], media['has_audio']), (1280, 720, True))
        self.assertAlmostEqual(media['duration'], 1.4, delta=0.3)

    def test_preview_is_separate_from_the_final_render(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one', width=1920, height=1080))
        completed = self.run_task(film['id'], 'preview')
        self.assertEqual(completed['preview']['status'], 'completed', completed['preview'].get('error'))
        self.assertEqual(completed['render']['status'], 'draft')
        self.assertEqual(completed['renders'], [])
        self.assertEqual(completed['stages']['composition']['status'], 'pending')
        preview = next(self.context.paths.projects.rglob('preview.mp4'))
        media = asyncio.run(render.probe(FFPROBE, preview))
        self.assertEqual((media['width'], media['height']), (852, 480))
        self.assertTrue(completed['preview']['url'].startswith('/v1/library/files/'))
        self.assertFalse(self.context.application_tasks)

    def test_proxies_build_thumbnails_and_waveform_once(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        first = asyncio.run(self.service.proxies(self.project, 'video-one'))
        self.assertTrue(first['thumbnails_url'].startswith('data:image/png;base64,'))
        self.assertTrue(first['waveform_url'].startswith('data:image/png;base64,'))
        self.assertAlmostEqual(first['duration'], 1.0, delta=0.2)
        self.assertFalse(first['cached'])
        second = asyncio.run(self.service.proxies(self.project, 'video-one'))
        self.assertTrue(second['cached'])
        self.assertEqual(first['thumbnails_url'], second['thumbnails_url'])
        # 过程图片不得进入素材库：它们没有媒体扩展名。
        images = [path for path in self.context.paths.projects.rglob('thumbs.*')]
        self.assertEqual([path.suffix for path in images], ['.dat'])
        self.assertTrue((images[0].parent / 'wave.dat').is_file())

    def test_documents_and_sources_are_isolated_per_project(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one'))
        other = self.projects.create('另一个 项目')['id']
        directory = self.projects.ensure_directory(self.db.project(other))
        foreign = directory / 'videos' / 'foreign-one.mp4'
        foreign.parent.mkdir(parents=True, exist_ok=True)
        encode(foreign, 'color=c=blue:s=160x120:r=24:d=1', 'sine=frequency=440:duration=1')
        self.db.insert_job({'id': 'foreign-one', 'kind': 'video', 'status': 'completed', 'created_at': 1,
                            'request': {}, 'project_id': other})
        self.db.update_job('foreign-one', {'artifacts_json': json.dumps(
            [{'name': foreign.name, 'project_path': foreign.relative_to(self.context.paths.projects).as_posix()}])})
        self.service.select('foreign-one', True)
        self.assertEqual(self.service.list(other), [])
        with self.assertRaises(ValueError):
            self.service.get(other, film['id'])
        with self.assertRaises(ValueError):
            self.service.save(other, self.body('video-one'))
        with self.assertRaises(ValueError):
            self.service.source(self.project, 'foreign-one', 0)
        self.assertEqual(self.service.source(other, 'foreign-one', 0), foreign.resolve())

    def test_cancelling_a_render_fails_cleanly(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one'))

        async def cancel_midway():
            await self.service.submit(self.project, film['id'])
            task = next(iter(self.context.application_tasks.values()))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return self.service.get(self.project, film['id'])
        failed = asyncio.run(cancel_midway())
        self.assertEqual(failed['render']['status'], 'failed')
        self.assertIn('中断', failed['render']['error'])
        self.assertEqual(list(self.context.paths.projects.rglob('final.mp4')), [])
        self.assertFalse(self.context.application_tasks)

    def test_cancel_rejects_an_already_finished_render(self):
        self.add_job('video-one')
        film = self.service.save(self.project, self.body('video-one'))
        with self.assertRaises(RuntimeError) as raised:
            self.service.cancel(self.project, film['id'])
        self.assertIn('无需取消', str(raised.exception))

    def test_missing_system_ffmpeg_is_reported(self):
        self.add_job('video-one')
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body('video-one'))
        with patch.object(render.shutil, 'which', return_value=None):
            with self.assertRaises(ValueError) as raised:
                asyncio.run(self.service.submit(self.project, film['id']))
        self.assertIn('系统 PATH', str(raised.exception))
        self.assertEqual(self.context.application_tasks, {})
        self.assertEqual(self.service.get(self.project, film['id'])['render']['status'], 'draft')


class PlanSchemaTests(unittest.TestCase):
    """Timeline plan rules that must be rejected before anything reaches FFmpeg."""

    FilmWrite = sys.modules[CompositionService.__module__].FilmWrite

    def body(self, **overrides) -> dict:
        plan = {'name': '时间线', 'clips': [{'job_id': 'a', 'out': 2}], 'bgm_job_id': None, 'volume': 18,
                'width': 1280, 'height': 720, 'fps': 30, 'fit': 'contain'}
        plan.update(overrides)
        return plan

    def rejected(self, **overrides) -> None:
        with self.assertRaises(ValueError):
            self.FilmWrite(**self.body(**overrides))

    def test_transition_longer_than_a_neighbour_is_rejected(self):
        self.rejected(clips=[{'job_id': 'a', 'out': 1, 'transition': {'type': 'fade', 'duration': 1.5}},
                             {'job_id': 'b', 'out': 1}])

    def test_fades_longer_than_the_clip_are_rejected(self):
        self.rejected(clips=[{'job_id': 'a', 'out': 1, 'fade_in': 0.8, 'fade_out': 0.8}])

    def test_blank_needs_no_source_but_a_clip_does(self):
        self.FilmWrite(**self.body(clips=[{'kind': 'blank', 'out': 1}]))
        self.rejected(clips=[{'kind': 'clip', 'out': 1}])

    def test_overlay_needs_a_rectangle_inside_the_canvas(self):
        self.rejected(overlay_clips=[{'job_id': 'a', 'out': 1, 'start': 0}])
        self.rejected(overlay_clips=[{'job_id': 'a', 'out': 1, 'start': 0, 'rect': {'x': 1200, 'y': 0,
                                                                                   'w': 200, 'h': 100}}])

    def test_placed_clips_must_stay_inside_the_film(self):
        self.rejected(overlay_clips=[{'job_id': 'a', 'out': 1, 'start': 2.5, 'rect': {'w': 100, 'h': 100}}])
        self.rejected(audio_clips=[{'job_id': 'a', 'out': 1, 'start': 2.5}])

    def test_unknown_fields_and_bad_cuts_are_rejected(self):
        self.rejected(clips=[{'job_id': 'a', 'out': 1, 'speed': 2}])
        self.rejected(clips=[{'job_id': 'a', 'in': 1, 'out': 1}])
        self.rejected(clips=[{'job_id': 'a', 'out': float('nan')}])
        self.rejected(unknown_field=1)

    def test_timeline_defaults_are_backward_compatible(self):
        film = self.FilmWrite(**self.body())
        self.assertEqual(film.clips[0].in_seconds, 0)
        self.assertEqual(film.clips[0].kind, 'clip')
        self.assertEqual(film.clips[0].volume, 100)
        self.assertIsNone(film.clips[0].transition)
        self.assertEqual((film.overlay_clips, film.audio_clips), ([], []))


if __name__ == '__main__':
    unittest.main()
