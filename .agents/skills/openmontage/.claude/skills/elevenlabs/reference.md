# ElevenLabs API Reference

Detailed API documentation for ElevenLabs audio generation services.

## Authentication

```python
from elevenlabs.client import ElevenLabs
client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
```

## Text-to-Speech Models

| Model ID | Description | Languages | Latency |
|----------|-------------|-----------|---------|
| `eleven_flash_v2_5` | Ultra-low latency streaming | 32 | ~75ms |
| `eleven_multilingual_v2` | Highest quality | 32 | Standard |
| `eleven_turbo_v2_5` | Fast, good quality | 32 | Low |
| `eleven_v3` | Best emotional range (alpha) | 32+ | Higher |

## Voice Settings

| Parameter | Range | Default | Effect |
|-----------|-------|---------|--------|
| `stability` | 0.0-1.0 | 0.5 | Lower = more expressive/variable |
| `similarity_boost` | 0.0-1.0 | 0.75 | Higher = closer to original voice |
| `style` | 0.0-1.0 | 0.0 | Style exaggeration (v2 models) |
| `speed` | 0.5-2.0 | 1.0 | Playback speed multiplier |

## Output Formats

| Format Code | Sample Rate | Bitrate | Tier Required |
|-------------|-------------|---------|---------------|
| `mp3_44100_128` | 44.1kHz | 128kbps | Free (default) |
| `mp3_44100_192` | 44.1kHz | 192kbps | Creator+ |
| `pcm_44100` | 44.1kHz | - | Pro+ |
| `ulaw_8000` | 8kHz | - | Free (telephony) |

## Long-form Audio (Stitching)

For continuity across multiple generations:

```python
result1 = client.text_to_speech.convert_with_timestamps(
    text="First paragraph...",
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    model_id="eleven_multilingual_v2"
)
request_id_1 = result1.request_id

result2 = client.text_to_speech.convert(
    text="Second paragraph...",
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    model_id="eleven_multilingual_v2",
    previous_request_ids=[request_id_1]
)
```

## Professional Voice Cloning (PVC)

Requires Creator plan+. Creates a fine-tuned model (3-6 hours training).

**Requirements:**
- 30 min minimum, 2-3 hours optimal audio
- Professional XLR mic recommended
- Pop filter, ~20cm distance
- Peak levels: -6dB to -3dB
- Consistent performance style

**Workflow:**

```python
# 1. Create PVC with samples
pvc = client.voices.create_professional_voice_clone(
    name="My Pro Voice",
    files=["recording1.mp3", "recording2.mp3", ...],
)

# 2. Get verification captcha
captcha = client.voices.get_pvc_verification_captcha(voice_id=pvc.voice_id)
# Read the captcha text aloud and record

# 3. Submit verification
client.voices.verify_pvc(
    voice_id=pvc.voice_id,
    recording=open("captcha_reading.mp3", "rb")
)

# 4. Start training
client.voices.start_pvc_training(voice_id=pvc.voice_id)
```

## Sound Effects Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `text` | string | Yes | Description of sound effect |
| `duration_seconds` | float | No | 1-22 seconds (auto if omitted) |
| `prompt_influence` | float | No | 0.0-1.0 (default 0.3) |

**Billing:** 100 chars/generation (auto) or 25 chars/second (fixed duration)

**Example prompts:**
- Environmental: "Rain on a tin roof, steady and rhythmic"
- Action: "Sword being drawn from sheath, metallic ring"
- Mechanical: "Old car engine struggling to start then roaring to life"

## Music Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes* | Natural language music description |
| `composition_plan` | object | Yes* | Detailed composition structure |
| `duration_ms` | int | No | 10000-300000 (10s-5min) |
| `instrumental` | bool | No | Force instrumental output |

*Either `prompt` or `composition_plan` required, not both.

**Effective prompts include:**
1. Genre/Style: "indie rock", "lo-fi hip hop", "orchestral"
2. Mood: "uplifting", "melancholic", "tense"
3. Instruments: "acoustic guitar", "synth pads", "strings"
4. Tempo/Energy: "slow", "upbeat", "driving"
5. Context: "for a travel vlog", "podcast intro"

## Rate Limits by Tier

| Tier | TTS Concurrent | SFX Concurrent | Music Concurrent |
|------|---------------|----------------|------------------|
| Free | 2 | 2 | 1 |
| Starter | 3 | 3 | 2 |
| Creator | 5 | 5 | 3 |
| Pro | 10 | 10 | 5 |
| Scale | 15 | 15 | 10 |

## Voice Management

```python
# List voices
voices = client.voices.get_all()
for voice in voices.voices:
    print(f"{voice.name}: {voice.voice_id}")

# Delete voice
client.voices.delete(voice_id="your_voice_id")
```

## Error Handling

```python
from elevenlabs.core.api_error import ApiError

try:
    audio = client.text_to_speech.convert(...)
except ApiError as e:
    if e.status_code == 429:
        print("Rate limited - wait and retry")
    elif e.status_code == 401:
        print("Invalid API key")
```

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Invalid API key | Check API key |
| 403 | Feature not available | Upgrade tier |
| 422 | Invalid parameters | Check request body |
| 429 | Rate limited | Wait and retry |
