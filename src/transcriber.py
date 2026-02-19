"""OpenAI Whisper API integration for audio transcription."""

import time
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from openai import OpenAI
from src.utils.logger import logger


class InsufficientQuotaError(Exception):
    """Raised when OpenAI API quota is exceeded."""
    pass


class WhisperTranscriber:
    """Transcribe audio using OpenAI Whisper API."""

    def __init__(self, api_key: str, model: str = "whisper-1", cache_dir: str = "temp/cache"):
        """Initialize the transcriber.

        Args:
            api_key: OpenAI API key
            model: Whisper model to use (default: whisper-1)
            cache_dir: Directory to cache transcription progress
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def transcribe_file(self, audio_path: str, language: str = None) -> Dict:
        """Transcribe a single audio file.

        Args:
            audio_path: Path to the audio file
            language: Optional language code (e.g., 'en', 'es')

        Returns:
            Dictionary containing transcript and word-level timestamps

        Raises:
            Exception: If transcription fails after retries
        """
        logger.info(f"Transcribing audio file: {audio_path}")

        for attempt in range(self.max_retries):
            try:
                with open(audio_path, 'rb') as audio_file:
                    # Call Whisper API with verbose JSON for timestamps
                    response = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["word"]
                    )

                # Convert response to dictionary
                transcript_data = {
                    'text': response.text,
                    'words': [],
                    'segments': []
                }

                # Extract word-level timestamps if available
                if hasattr(response, 'words') and response.words:
                    transcript_data['words'] = [
                        {
                            'word': word.word,
                            'start': word.start,
                            'end': word.end
                        }
                        for word in response.words
                    ]

                logger.info(f"Transcription successful. Text length: {len(response.text)} characters")
                return transcript_data

            except Exception as e:
                error_str = str(e)

                # Check for quota/billing errors - don't retry these
                if "insufficient_quota" in error_str.lower() or "quota" in error_str.lower():
                    logger.error("❌ OpenAI API quota exceeded - out of credits")
                    logger.error("Please add credits at: https://platform.openai.com/account/billing")
                    raise InsufficientQuotaError(
                        "OpenAI API quota exceeded. Please add credits to your account:\n"
                        "https://platform.openai.com/account/billing"
                    )

                logger.warning(f"Transcription attempt {attempt + 1} failed: {e}")

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Transcription failed after {self.max_retries} attempts")
                    raise Exception(f"Failed to transcribe audio: {e}")

    def _get_cache_path(self, chunk_path: str) -> Path:
        """Get cache file path for a chunk.

        Args:
            chunk_path: Path to the audio chunk

        Returns:
            Path to cache file
        """
        chunk_name = Path(chunk_path).stem
        return self.cache_dir / f"{chunk_name}_transcript.json"

    def _save_chunk_cache(self, chunk_path: str, transcript: Dict):
        """Save transcription cache for a chunk.

        Args:
            chunk_path: Path to the audio chunk
            transcript: Transcription data to cache
        """
        cache_path = self._get_cache_path(chunk_path)
        with open(cache_path, 'w') as f:
            json.dump(transcript, f)
        logger.debug(f"Cached transcript: {cache_path}")

    def _load_chunk_cache(self, chunk_path: str) -> Optional[Dict]:
        """Load cached transcription for a chunk if available.

        Args:
            chunk_path: Path to the audio chunk

        Returns:
            Cached transcript or None if not found
        """
        cache_path = self._get_cache_path(chunk_path)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache {cache_path}: {e}")
        return None

    def transcribe_chunks(
        self,
        chunk_paths: List[Tuple[str, float]],
        language: str = None,
        resume: bool = True
    ) -> Dict:
        """Transcribe multiple audio chunks and merge results.

        Args:
            chunk_paths: List of (chunk_path, start_offset) tuples
            language: Optional language code
            resume: If True, use cached transcripts for already-processed chunks

        Returns:
            Dictionary containing merged transcript with adjusted timestamps
        """
        logger.info(f"Transcribing {len(chunk_paths)} audio chunks")

        all_words = []
        full_text_parts = []

        for i, (chunk_path, offset) in enumerate(chunk_paths, 1):
            # Check cache first if resume is enabled
            chunk_transcript = None
            if resume:
                chunk_transcript = self._load_chunk_cache(chunk_path)
                if chunk_transcript:
                    logger.info(f"✓ Using cached transcript for chunk {i}/{len(chunk_paths)}")

            # Transcribe if not cached
            if chunk_transcript is None:
                logger.info(f"Transcribing chunk {i}/{len(chunk_paths)} (offset: {offset:.1f}s)")

                try:
                    chunk_transcript = self.transcribe_file(chunk_path, language)
                    # Save to cache immediately after successful transcription
                    self._save_chunk_cache(chunk_path, chunk_transcript)

                except InsufficientQuotaError:
                    # Stop immediately on quota error
                    logger.error(f"❌ Stopped at chunk {i}/{len(chunk_paths)} due to quota limit")
                    logger.info(f"Progress saved: {i-1}/{len(chunk_paths)} chunks completed")
                    logger.info("To resume, run the same command again after adding credits")
                    raise

                except Exception as e:
                    logger.error(f"Failed to transcribe chunk {i}: {e}")
                    # Continue with remaining chunks
                    full_text_parts.append(f"[Transcription failed for chunk {i}]")
                    continue

            # Add offset to all timestamps
            adjusted_words = []
            if chunk_transcript.get('words'):
                for word_data in chunk_transcript['words']:
                    adjusted_words.append({
                        'word': word_data['word'],
                        'start': word_data['start'] + offset,
                        'end': word_data['end'] + offset
                    })

            all_words.extend(adjusted_words)
            full_text_parts.append(chunk_transcript['text'])

        merged_transcript = {
            'text': ' '.join(full_text_parts),
            'words': all_words,
            'segments': []
        }

        logger.info(f"Successfully transcribed and merged {len(chunk_paths)} chunks")
        logger.info(f"Total transcript length: {len(merged_transcript['text'])} characters")

        return merged_transcript

    def save_transcript(
        self,
        transcript: Dict,
        output_path: str,
        include_timestamps: bool = True,
        timestamp_interval: int = 60
    ):
        """Save transcript to a text file.

        Args:
            transcript: Transcript dictionary
            output_path: Path to save the transcript
            include_timestamps: Whether to include timestamps in the output
            timestamp_interval: Seconds between timestamps (default: 60)
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            if include_timestamps and transcript.get('words'):
                # Write with timestamps at intervals
                formatted = self.format_transcript_with_timestamps(
                    transcript,
                    interval=timestamp_interval
                )
                f.write(formatted)
            else:
                # Write plain text
                f.write(transcript.get('text', ''))

        logger.info(f"Transcript saved to: {output_file}")

    def save_transcript_json(self, transcript: Dict, output_path: str):
        """Save raw transcript data as JSON.

        Args:
            transcript: Transcript dictionary
            output_path: Path to save the JSON file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(transcript, f, indent=2)

        logger.info(f"Raw transcript JSON saved to: {output_file}")

    def format_transcript_with_timestamps(self, transcript: Dict, interval: int = 60) -> str:
        """Format transcript with timestamps at regular intervals.

        Args:
            transcript: Transcript dictionary from transcribe_file/transcribe_chunks
            interval: Seconds between timestamps (default: 60)

        Returns:
            Formatted transcript string with timestamps
        """
        if not transcript.get('words'):
            return transcript.get('text', '')

        formatted_lines = []
        current_time = 0
        current_words = []

        for word_data in transcript['words']:
            word = word_data['word']
            start = word_data['start']

            # Check if we should insert a timestamp
            if start >= current_time + interval:
                if current_words:
                    formatted_lines.append(' '.join(current_words))
                    current_words = []

                # Add timestamp
                minutes = int(start // 60)
                seconds = int(start % 60)
                formatted_lines.append(f"\n[{minutes:02d}:{seconds:02d}]")
                current_time = start

            current_words.append(word.strip())

        # Add remaining words
        if current_words:
            formatted_lines.append(' '.join(current_words))

        return ' '.join(formatted_lines)

    def get_transcript_at_intervals(
        self,
        transcript: Dict,
        interval: int = 30
    ) -> List[Tuple[float, str]]:
        """Extract transcript text at regular time intervals.

        Args:
            transcript: Transcript dictionary with word timestamps
            interval: Seconds between intervals (default: 30)

        Returns:
            List of (timestamp, text) tuples for each interval
        """
        if not transcript.get('words'):
            return [(0, transcript.get('text', ''))]

        intervals = []
        words = transcript['words']

        if not words:
            return [(0, transcript.get('text', ''))]

        # Determine total duration
        max_time = words[-1]['end']
        num_intervals = int(max_time // interval) + 1

        for i in range(num_intervals):
            start_time = i * interval
            end_time = (i + 1) * interval

            # Collect words in this interval
            interval_words = [
                word_data['word']
                for word_data in words
                if start_time <= word_data['start'] < end_time
            ]

            if interval_words:
                text = ' '.join(interval_words).strip()
                intervals.append((start_time, text))

        return intervals
