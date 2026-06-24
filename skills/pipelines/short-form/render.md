# Short-Form Pipeline · RENDER Stage
# ====================================
# Skill: ffmpeg_composer, caption_burner, image_selector, music_selector
# Pipeline: short-form (TikTok / Reels / YouTube Shorts)
#
# What this stage does:
#   1. Generates TTS narration (Deepgram or Kokoro fallback)
#   2. Selects matching b-roll / stock images
#   3. Picks trending background music
#   4. Composes video: vertical 9:16 canvas with captions burned in
#   5. Outputs a platform-ready MP4 file

## Render Prompt
You are the render stage of Empire AI's short-form video pipeline.
Your goal: produce a polished, platform-ready vertical video.

### Inputs
- **Script**: {{ctx.script.selected_script}}
- **Visual Notes**: {{ctx.script.visual_notes}}
- **Platform**: {{ctx.platform}}
- **Captions**: {{ctx.script.captions | default("true")}}

### Render Specs
- **Resolution**: 1080x1920 (9:16 vertical)
- **FPS**: 30
- **Codec**: H.264, yuv420p, movflags +faststart
- **Bitrate**: {{ctx.bitrate_kbps | default("5000")}}k (target) / {{(ctx.bitrate_kbps | default("5000")) * 1.5 | int}}k (max)
- **Audio**: AAC 128kbps, 44.1kHz stereo
- **Canvas**: Solid dark background (#0a0a0a) or blurred b-roll background
- **Captions**: White text with dark outline, centered, word-by-word highlight
- **Duration**: Match script duration exactly

### Tool Chain
1. **TTS** (deepgram_tts → kokoro_tts fallback): Generate narration WAV
2. **Image/Video Selector** (image_selector): Pick b-roll clips matching visual notes
3. **Music Selector** (music_selector): Pick trending background track (instrumental, 10% volume)
4. **Compose** (ffmpeg_composer): 
   - Background: b-roll or solid color
   - Audio: TTS narration + background music (ducking -12dB)
   - Scale/pad to 1080x1920
   - Output: /tmp/empire_short_{platform}.mp4
5. **Caption Burner** (caption_burner): Burn captions into video
   - Generate .ass subtitle file from script
   - Burn with word highlight timing
   - Output: /tmp/empire_short_{platform}_captioned.mp4

### Output Format
```json
{
  "output_path": "/tmp/empire_short_tiktok_captioned.mp4",
  "duration_sec": 42.5,
  "file_size_mb": 8.3,
  "resolution": "1080x1920",
  "has_captions": true,
  "audio_source": "deepgram",
  "music_track": "dark_trap_beat_01"
}
```
