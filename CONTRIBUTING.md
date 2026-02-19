# Contributing

This is a personal project — I'm not actively seeking contributors, but bug fixes and small improvements are welcome.

## Running Locally

**Requirements:** Python 3.9+, ffmpeg, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/cmod/youtube-timestamps
cd youtube-timestamps
uv sync
cp .env.example .env
# Add your OPENAI_API_KEY to .env
uv run python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Testing

There is no automated test suite. Manual testing workflow:

1. Process a 5–10 minute video to verify basic functionality
2. Check `cache/VIDEO_ID/` to confirm caching is working
3. Run again with `--min-duration 45` to confirm cache reuse (should be fast and cheap)
4. Test `--qa-mode` on a presentation video that includes a Q&A section

## Submitting a PR

- Keep changes focused and minimal
- Update README.md if any user-facing behavior changes
- Describe what you tested and how in the PR description
