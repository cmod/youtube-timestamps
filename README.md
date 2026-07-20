# youtube-timestamps

Making timestamps/chapters from a YouTube video feels like the world's worst homework. Can we use the magic of LLMs to make this less horrible and yet … good? Yes. Yes we can. 

Here you go:

---

Generate chapter timestamps for any YouTube video — just give it a URL.

Transcribes with OpenAI Whisper, analyzes structure with GPT-4o, and outputs YouTube-ready chapter markers you can paste directly into a video description.

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
- **Intelligent topic detection** using GPT-4o to identify chapter boundaries
- **Q&A mode (default)** — presentation + Q&A videos get warmup / presentation / Q&A boundary chapters and a timestamp for every question
- **Word-level accuracy** — question and boundary stamps are snapped to Whisper's word timestamps, not left at coarse transcript-bucket markers
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
  --qa-mode / --no-qa-mode              Optimize for presentation + Q&A format
                                        (default: enabled)
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

# Plain topical chapters (Q&A mode is on by default)
uv run python main.py "URL" --no-qa-mode

# Skip saving the transcript
uv run python main.py "URL" --no-save-transcript

# Force complete reprocessing (ignore cache)
uv run python main.py "URL" --force-reprocess
```

## Q&A Mode

Q&A mode is **on by default** — it's built for videos with a **presentation followed by audience Q&A**. Use `--no-qa-mode` for plain topical chapters instead.

**How it works:**
1. One boundary pass finds where the presentation proper begins (after the
   waiting-for-people warmup) and where Q&A starts — each pinned to the exact
   spoken phrase via word-level timestamps
2. The Q&A section is densely sampled to identify every individual question
3. Each question's timestamp is then snapped to the words of the question in
   the transcript (bucket markers alone are up to ~15s off)

Questions are phrased in second person ("What lens do you use…") even when the
speaker reads them aloud in first person, and a small spelling glossary in
`src/topic_analyzer.py` fixes proper nouns the transcript reliably mishears.

**Without Q&A mode** (generic chapters):
```
00:00:00 - Introduction
00:18:30 - The walk begins
00:44:15 - Crossing the mountain pass
01:09:00 - Arriving at the coast
```

**With Q&A mode** (per-question timestamps):
```
00:00:00 - Warmup / waiting
00:04:12 - Start of presentation
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
  model: gpt-4o               # or gpt-4o-mini for lower cost
  temperature: 0.3
  min_topic_duration: 30      # seconds between chapters

audio:
  chunk_size_mb: 20
  chunk_duration: 600         # seconds per chunk
```

## Cost Estimate

- **Whisper API**: $0.006/minute of audio
- **GPT-4o analysis**: ~$0.02/video (consistent regardless of length)

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
- [OpenAI GPT-4o](https://platform.openai.com/docs/models) — structure & topic analysis
- [Google Gemini](https://ai.google.dev/) — optional alternative for analysis
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube audio download
- [pydub](https://github.com/jiaaro/pydub) — audio processing
- [Click](https://click.palletsprojects.com/) — CLI framework
- [Rich](https://rich.readthedocs.io/) — terminal output
