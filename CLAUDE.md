# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI tool that automatically generates YouTube chapter timestamps using OpenAI Whisper for transcription and GPT-4/Gemini for intelligent topic analysis. Features a sophisticated caching system that enables rapid iteration on chapter extraction without re-transcribing.

## Development Commands

### Setup
```bash
# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env to add your OPENAI_API_KEY (required) and GOOGLE_API_KEY (optional for Gemini)
```

### Running the Tool
```bash
# Basic usage
uv run python main.py "https://www.youtube.com/watch?v=VIDEO_ID"

# With options
uv run python main.py "URL" -o output.txt --min-duration 45 -f markdown

# Q&A mode (for presentations with Q&A)
uv run python main.py "URL" --qa-mode

# Force reprocessing (bypass cache)
uv run python main.py "URL" --force-reprocess

# Use Gemini instead of GPT-4 for analysis
uv run python main.py "URL" --provider gemini
```

### Testing Workflow
Since there are no automated tests, test manually by:
1. Processing a short test video (5-10 min) to verify basic functionality
2. Check cache directory (`cache/VIDEO_ID/`) to verify caching works
3. Run again with different `--min-duration` to test cache reuse
4. Test `--qa-mode` on a presentation video with Q&A section

## Architecture

### Entry Point
- **main.py**: CLI interface using Click framework. Orchestrates the full pipeline: video info → audio download → transcription → topic analysis → formatting → output

### Core Components

**src/youtube_downloader.py**
- Downloads audio from YouTube using yt-dlp
- Extracts video metadata (title, duration)
- Function: `extract_video_id(url)` extracts video ID from various YouTube URL formats

**src/transcriber.py** (WhisperTranscriber)
- Transcribes audio using OpenAI Whisper API
- Handles chunked audio files for large videos
- Returns word-level timestamps in format: `{'text': str, 'words': [{'word': str, 'start': float, 'end': float}]}`
- Special exception: `InsufficientQuotaError` for quota exceeded errors
- Implements resume capability by caching chunk transcripts in `temp/cache/`

**src/topic_analyzer.py** (TopicAnalyzer)
- Analyzes transcripts to identify topic changes using GPT-4 or Gemini
- Supports two providers: `openai` and `gemini`
- **Standard mode**: Uses sliding intervals (30-60s) to sample transcript and identify chapters
- **Q&A mode** (`--qa-mode`): Two-pass analysis
  1. First pass: Locates Q&A section start time
  2. Second pass: Densely samples Q&A section to find individual questions
- For Gemini: Uses `_analyze_with_gemini()` which sends full transcript in one request (leverages large context window)
- Returns list of `(timestamp_seconds, description)` tuples

**src/cache_manager.py** (CacheManager)
- Persistent caching system organized by video ID in `cache/VIDEO_ID/`
- Caches:
  - `audio.mp3`: Downloaded audio file
  - `transcript.json`: Full Whisper transcription
  - `video_info.json`: Video metadata
- Methods: `get_cached_audio()`, `save_audio()`, `get_cached_transcript()`, `save_transcript()`
- Enables rapid re-analysis with different settings without re-transcription

**src/utils/audio_processor.py** (AudioProcessor)
- Chunks large audio files (>20MB) for Whisper API compatibility
- Uses pydub to split audio at specified intervals (default: 600s/10min)
- Method: `chunk_audio(audio_path, output_dir)` returns list of chunk paths

**src/timestamp_formatter.py** (TimestampFormatter)
- Formats timestamps for different output formats: YouTube, Markdown, JSON
- Converts seconds to HH:MM:SS format
- YouTube format: Plain text with `HH:MM:SS - Description`
- Markdown format: Table with clickable links
- JSON format: Structured data with timestamps and descriptions

**src/utils/config_loader.py**
- Loads configuration from `config.yaml` and `.env`
- Merges environment variables with YAML config
- Returns dictionary with all settings

### Key Architectural Patterns

**Caching Strategy**
- Cache is organized by YouTube video ID in `cache/VIDEO_ID/`
- Enables instant re-analysis with different parameters (e.g., `--min-duration`)
- Cost savings: $0.02 vs $0.38 for 1-hour video re-analysis
- Use `--force-reprocess` to bypass cache and start fresh

**Resume Capability**
- Chunk transcripts cached in `temp/cache/VIDEO_ID_audio_chunk_NNN_transcript.json`
- If transcription interrupted (quota exceeded), re-running resumes from last completed chunk
- Implemented in `transcriber.py:transcribe_chunks()` method

**Q&A Mode Two-Pass Analysis**
1. **Presentation Pass**: Analyzer samples entire transcript to find Q&A start time
2. **Q&A Pass**: Dense sampling (15s intervals) only within Q&A section to identify each question
3. Result: Minimal presentation timestamps + detailed Q&A question timestamps

**Error Handling**
- `InsufficientQuotaError`: Special handling for OpenAI quota exceeded - gracefully exits with instructions to add credits and resume
- Exponential backoff for transient API errors (rate limits)
- Clear user-facing error messages using Rich console formatting

## Configuration

**config.yaml**
- `transcription.model`: Whisper model (always "whisper-1")
- `topic_analysis.model`: GPT model for analysis (default: "gpt-4-turbo-preview")
- `topic_analysis.min_topic_duration`: Default minimum seconds between chapters (30)
- `audio.chunk_size_mb`: Maximum chunk size in MB (20)
- `audio.chunk_duration`: Chunk duration in seconds (600)

**.env**
- `OPENAI_API_KEY`: Required for Whisper transcription, optional for analysis if using Gemini
- `GOOGLE_API_KEY`: Optional, required only when using `--provider gemini`

## Important Implementation Details

**Video ID Extraction**
- Handles multiple YouTube URL formats: full URLs, youtu.be short links, with/without parameters
- Function: `youtube_downloader.extract_video_id(url)` returns video ID or None

**Cost Estimation**
- Whisper API: $0.006/minute
- GPT-4 analysis: ~$0.02/video (token-based, but consistent)
- Function: `main.estimate_cost(duration_seconds)` calculates estimate

**Transcript Intervals**
- Adaptive intervals based on video length in topic_analyzer.py:
  - >30 min videos: 60s intervals
  - >15 min videos: 45s intervals
  - <15 min videos: 30s intervals
- Prevents overwhelming GPT context window on long videos

**Output Directory Structure**
```
output/
  [Video Title]_timestamps.txt     # Main output
  [Video Title]_transcript.txt     # Full transcript with timestamps
  [Video Title]_transcript.json    # Raw JSON with word-level data

cache/
  [VIDEO_ID]/
    audio.mp3           # Cached audio
    transcript.json     # Cached transcript
    video_info.json     # Video metadata

temp/
  cache/
    [VIDEO_ID]_audio_chunk_NNN_transcript.json  # Resume cache
  [VIDEO_ID]_audio.mp3  # Temp audio (deleted unless --keep-files)
```

## Dependencies

- **uv**: Python package manager (alternative to pip/poetry)
- **yt-dlp**: YouTube audio download
- **openai**: Whisper transcription & GPT-4 analysis
- **google-generativeai**: Optional Gemini support
- **pydub**: Audio processing and chunking
- **click**: CLI framework
- **rich**: Beautiful terminal UI with progress bars and panels
- **ffmpeg**: Required system dependency for audio processing

## Common Patterns

**Adding New Output Format**
1. Add format choice to `main.py` click option `--format`
2. Implement formatter method in `timestamp_formatter.py`
3. Add format logic to main.py Step 6 (around line 330)

**Supporting New AI Provider**
1. Add provider to `--provider` click option
2. Implement provider logic in `topic_analyzer.py.__init__()`
3. Add provider-specific analysis method like `_analyze_with_gemini()`
4. Update prompt engineering for provider's format

**Modifying Topic Analysis Prompts**
- Prompts are in `topic_analyzer.py`
- Standard mode: `_analyze_transcript_with_intervals()` method
- Q&A mode: `_analyze_qa_transcript()` with separate presentation/QA prompts
- Gemini mode: `_analyze_with_gemini()` sends full transcript
