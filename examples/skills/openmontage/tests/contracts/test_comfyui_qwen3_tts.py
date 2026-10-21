"""Contract tests for the local ComfyUI Qwen3-TTS adapter."""

from pathlib import Path

from tools.base_tool import ToolRuntime, ToolStatus, ToolTier


def test_qwen3_tts_is_local_tts_provider(monkeypatch):
    monkeypatch.setenv("COMFYUI_TTS_SERVER_URL", "http://comfy.test")
    from tools.audio.comfyui_qwen3_tts import ComfyUIQwen3TTS

    tool = ComfyUIQwen3TTS()
    assert tool.capability == "tts"
    assert tool.provider == "comfyui"
    assert tool.tier == ToolTier.VOICE
    assert tool.runtime == ToolRuntime.LOCAL_GPU
    assert tool.supports["offline"] is True
    assert tool._client.server_url == "http://comfy.test"


def test_qwen3_tts_is_available_when_required_nodes_exist(monkeypatch):
    from tools.audio.comfyui_qwen3_tts import ComfyUIQwen3TTS

    tool = ComfyUIQwen3TTS()
    monkeypatch.setattr(tool._client, "is_available", lambda: True)
    monkeypatch.setattr(tool._client, "has_node", lambda node: node in {"Qwen3Loader", "Qwen3CustomVoice", "SaveAudio"})
    assert tool.get_status() == ToolStatus.AVAILABLE


def test_qwen3_tts_builds_offline_custom_voice_workflow(monkeypatch):
    from tools.audio.comfyui_qwen3_tts import ComfyUIQwen3TTS

    tool = ComfyUIQwen3TTS()
    workflow = tool._build_workflow({
        "text": "你好，这是本地语音测试。",
        "voice": "Vivian",
        "language": "Chinese",
        "seed": 42,
        "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    })
    assert workflow["1"]["class_type"] == "Qwen3Loader"
    assert workflow["2"]["class_type"] == "Qwen3CustomVoice"
    assert workflow["2"]["inputs"]["text"] == "你好，这是本地语音测试。"
    assert workflow["2"]["inputs"]["speaker"] == "Vivian"
    assert workflow["3"]["class_type"] == "SaveAudio"


def test_qwen3_tts_downloads_audio_to_requested_path(monkeypatch, tmp_path):
    from tools.audio.comfyui_qwen3_tts import ComfyUIQwen3TTS

    tool = ComfyUIQwen3TTS()
    output = tmp_path / "narration.flac"
    monkeypatch.setattr(tool._client, "is_available", lambda: True)
    monkeypatch.setattr(tool._client, "has_node", lambda node: True)

    def fake_generate(workflow, output_node, dest, **kwargs):
        assert output_node == "3"
        assert dest == output
        dest.write_bytes(b"fLaC")
        return [dest]

    monkeypatch.setattr(tool._client, "generate", fake_generate)
    result = tool.execute({"text": "测试", "output_path": str(output), "seed": 7})
    assert result.success is True
    assert result.data["output"] == str(output)
    assert result.cost_usd == 0.0
    assert Path(result.artifacts[0]).read_bytes() == b"fLaC"
