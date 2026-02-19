# youtube-timestamps

Making timestamps/chapters from a YouTube video feels like the world's worst homework. Can we use the magic of LLMs to make this less horrible and yet … good? Yes. Yes we can. 

Here you go:

---

Generate chapter timestamps for any YouTube video — just give it a URL.

Transcribes with OpenAI Whisper, analyzes topics with GPT-4, and outputs YouTube-ready chapter markers you can paste directly into a video description.

```
00:00:00 - Welcome
00:03:42 - Presentation starts
00:11:17 - Q&A Begins
00:28:05 - What's the best place to each chicken ramen in Tokyo?
00:41:33 - Why does every middle aged white guy want to buy abandoned farmhouse in a dying village in Japan?
00:58:12 - What's the most you ever lost in a coin toss?
01:14:45 - Is this a butterfly?
```

## Features

- **Automatic transcription** using OpenAI Whisper API
- **Intelligent topic detection** using GPT-4 to identify chapter boundaries
- **Q&A mode** — specialized for presentation + Q&A videos with per-question timestamps
- **YouTube-ready format** — paste directly into video descriptions
- **Full transcript saving** — text and JSON formats with timestamps
- **Persistent caching** — saves audio & transcripts by video ID for instant re-analysis
- **Iterate on chapters** — tweak settings and re-run without re-transcribing ($0.02 vs $0.38!)
- **Multiple output formats** — YouTube, Markdown, or JSON
- **Handles long videos** — automatically chunks large audio files
- **Resume capability** — automatically resumes if interrupted mid-transcription
- **Beautiful CLI** with progress indicators and formatted output
- **Cost estimation** before processing

## Quick Start

**Requirements:** Python 3.9+, [ffmpeg](https://ffmpeg.org/download.html), [uv](https://docs.astral.sh/uv/)

```bash
# 1. Clone and install
git clone https://github.com/cmod/youtube-timestamps
cd youtube-timestamps
uv sync

# 2. Configure API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Run
uv run python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

## API Keys

| Key | Where to get it | Required? |
|-----|-----------------|-----------|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | **Required** — Whisper transcription + GPT-4 analysis |
| `GOOGLE_API_KEY` | [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) | Optional — only needed for `--provider gemini` |

### Installing ffmpeg and uv

<details>
<summary>macOS</summary>

```bash
brew install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
```
</details>

<details>
<summary>Ubuntu/Debian</summary>

```bash
sudo apt install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
```
</details>

<details>
<summary>Windows</summary>

- ffmpeg: download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- uv: `pip install uv`
</details>

## Usage

```bash
uv run python main.py [URL] [OPTIONS]

Options:
  -o, --output PATH                     Output file path (default: output/timestamps.txt)
  --min-duration INTEGER                Minimum topic duration in seconds (default: 30)
  -f, --format [youtube|markdown|json]  Output format (default: youtube)
  --save-transcript / --no-save-transcript
                                        Save full transcript to file (default: enabled)
  --qa-mode                             Optimize for presentation + Q&A format
  --provider [openai|gemini]            AI provider for analysis (default: openai)
  --force-reprocess                     Force re-download and re-transcription (ignore cache)
  --keep-files                          Keep temporary audio files
  --help                                Show help message
```

### Examples

```bash
# Basic usage
uv run python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Save to custom location
uv run python main.py "https://youtu.be/VIDEO_ID" -o my_timestamps.txt

# Output as Markdown table
uv run python main.py "URL" -f markdown

# More chapters (shorter minimum duration)
uv run python main.py "URL" --min-duration 20

# Re-analyze with different settings — uses cache, only re-runs GPT-4 (~$0.02)
uv run python main.py "URL" --min-duration 45

# Use Gemini instead of GPT-4 for analysis
uv run python main.py "URL" --provider gemini

# Presentation + Q&A video
uv run python main.py "URL" --qa-mode

# Skip saving the transcript
uv run python main.py "URL" --no-save-transcript

# Force complete reprocessing (ignore cache)
uv run python main.py "URL" --force-reprocess
```

## Q&A Mode

For videos with a **presentation followed by audience Q&A**, use `--qa-mode` for detailed question-level timestamps.

**Two-pass analysis:**
1. Locates where Q&A begins in the video
2. Densely samples the Q&A section to find each individual question

**Without Q&A mode** (generic chapters):
```
00:00:00 - Introduction
00:18:30 - The walk begins
00:44:15 - Crossing the mountain pass
01:09:00 - Arriving at the coast
```

**With Q&A mode** (per-question timestamps):
```
00:00:00 - Walking 1000km across Japan
00:47:23 - Q&A begins
00:47:58 - Q: How do you decide when a photo is finished?
00:51:30 - Q: What camera gear did you carry for 1000km?
00:55:12 - Q: How do you stay motivated on long solo walks?
00:59:44 - Q: Advice for someone planning their first long walk?
```

**Use Q&A mode for:** board meetings, conference talks, webinars, town halls — any video with a structured presentation → Q&A format.

## Output Files

All files are saved to the `output/` directory:

**`[Video Title]_timestamps.txt`** — YouTube-ready chapter markers:
```
Video: Walking Across Japan
Duration: 1h 18m 32s

Chapters:
00:00:00 - Arriving in Tokyo at dawn
00:03:42 - Morning coffee at a kissaten in Yanaka
...
```

**`[Video Title]_transcript.txt`** — Full transcription with timestamps every 60 seconds.

**`[Video Title]_transcript.json`** — Machine-readable format with word-level timestamps:
```json
{
  "text": "Welcome everyone...",
  "words": [
    {"word": "Welcome", "start": 0.5, "end": 1.2},
    ...
  ]
}
```

## Configuration

Edit `config.yaml` to customize defaults:

```yaml
transcription:
  model: whisper-1

topic_analysis:
  model: gpt-4-turbo-preview  # or gpt-3.5-turbo for lower cost
  temperature: 0.3
  min_topic_duration: 30      # seconds between chapters

audio:
  chunk_size_mb: 20
  chunk_duration: 600         # seconds per chunk
```

## Cost Estimate

- **Whisper API**: $0.006/minute of audio
- **GPT-4 analysis**: ~$0.02/video (consistent regardless of length)

| Video length | Estimated cost |
|-------------|----------------|
| 5 minutes   | ~$0.05         |
| 30 minutes  | ~$0.20         |
| 1 hour      | ~$0.38         |
| 2 hours     | ~$0.74         |

**Re-analysis is nearly free:** once a video is transcribed and cached, changing settings and re-running only costs the GPT-4 analysis (~$0.02).

## Caching

Audio and transcripts are cached by video ID in `cache/[video_id]/`. On subsequent runs with the same URL, the tool skips re-downloading and re-transcribing — only the topic analysis re-runs. This makes iteration fast and cheap.

If transcription is interrupted (quota exceeded, network error), re-running the same command automatically resumes from the last completed chunk.

## Advanced Usage

### Using as a Python Module

```python
from src.youtube_downloader import YouTubeDownloader
from src.transcriber import WhisperTranscriber
from src.topic_analyzer import TopicAnalyzer

downloader = YouTubeDownloader()
audio_file = downloader.download_audio("https://youtube.com/watch?v=...")

transcriber = WhisperTranscriber(api_key="your-key")
transcript = transcriber.transcribe_file(audio_file)

analyzer = TopicAnalyzer(api_key="your-key")
topics = analyzer.analyze_transcript(transcript)

for timestamp, description in topics:
    print(f"{timestamp}s: {description}")
```

### Batch Processing

```bash
cat urls.txt | while read url; do
  uv run python main.py "$url"
done
```

## Troubleshooting

**"OPENAI_API_KEY not found"**
```bash
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-...
```

**"ffmpeg not found"**
Install ffmpeg using your package manager (see Quick Start above).

**"Private video" or "Video unavailable"**
Only public YouTube videos are supported.

**"Rate limit exceeded" or "Quota exceeded"**
The tool stops and saves progress. Add credits at [platform.openai.com/account/billing](https://platform.openai.com/account/billing), then re-run the same command — it resumes automatically from the last completed chunk.

**Poor timestamp quality**
Try adjusting `--min-duration` (lower = more chapters, higher = fewer). Videos with music or no clear speech may produce inconsistent results.

## Limitations

- Only works with public YouTube videos
- Quality depends on audio clarity and speech content
- Music-heavy videos or videos without clear speech may not work well
- Very long videos (3+ hours) require significant processing time
- Costs money per video (see Cost Estimate)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License — see [LICENSE](LICENSE) for details.

## Credits

Built with:
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) — speech-to-text transcription
- [OpenAI GPT-4](https://platform.openai.com/docs/models) — topic analysis
- [Google Gemini](https://ai.google.dev/) — optional alternative for analysis
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube audio download
- [pydub](https://github.com/jiaaro/pydub) — audio processing
- [Click](https://click.palletsprojects.com/) — CLI framework
- [Rich](https://rich.readthedocs.io/) — terminal output
