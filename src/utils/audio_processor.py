"""Audio processing utilities for chunking and optimization."""

import os
from pathlib import Path
from typing import List, Tuple
from pydub import AudioSegment
from src.utils.logger import logger


class AudioProcessor:
    """Handle audio file processing including chunking and optimization."""

    def __init__(self, max_chunk_size_mb: int = 20, chunk_duration: int = 600):
        """Initialize the audio processor.

        Args:
            max_chunk_size_mb: Maximum chunk size in MB (Whisper limit is 25MB)
            chunk_duration: Duration of each chunk in seconds (default: 600 = 10 minutes)
        """
        self.max_chunk_size_mb = max_chunk_size_mb
        self.chunk_duration = chunk_duration * 1000  # Convert to milliseconds for pydub

    def get_audio_duration(self, file_path: str) -> float:
        """Get the duration of an audio file in seconds.

        Args:
            file_path: Path to the audio file

        Returns:
            Duration in seconds
        """
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0  # Convert milliseconds to seconds

    def get_file_size_mb(self, file_path: str) -> float:
        """Get the file size in megabytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in MB
        """
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)

    def needs_chunking(self, file_path: str) -> bool:
        """Check if a file needs to be chunked based on size.

        Args:
            file_path: Path to the audio file

        Returns:
            True if file needs chunking, False otherwise
        """
        size_mb = self.get_file_size_mb(file_path)
        logger.info(f"Audio file size: {size_mb:.2f} MB")
        return size_mb > self.max_chunk_size_mb

    def chunk_audio(self, file_path: str, output_dir: str = "temp") -> List[Tuple[str, float]]:
        """Split audio into chunks.

        Args:
            file_path: Path to the audio file to chunk
            output_dir: Directory to save chunks (default: 'temp')

        Returns:
            List of tuples (chunk_path, start_time_offset) where start_time_offset
            is the cumulative duration before this chunk in seconds
        """
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Load audio file
        logger.info(f"Loading audio file: {file_path}")
        audio = AudioSegment.from_file(file_path)
        total_duration = len(audio)  # in milliseconds

        # Calculate number of chunks
        num_chunks = (total_duration + self.chunk_duration - 1) // self.chunk_duration
        logger.info(f"Splitting audio into {num_chunks} chunks of {self.chunk_duration/1000:.0f}s each")

        chunks = []
        base_name = Path(file_path).stem

        for i in range(num_chunks):
            start_ms = i * self.chunk_duration
            end_ms = min((i + 1) * self.chunk_duration, total_duration)
            start_seconds = start_ms / 1000.0

            # Extract chunk
            chunk = audio[start_ms:end_ms]

            # Save chunk
            chunk_filename = f"{base_name}_chunk_{i+1:03d}.mp3"
            chunk_path = output_path / chunk_filename

            logger.info(f"Exporting chunk {i+1}/{num_chunks}: {chunk_filename}")
            chunk.export(
                chunk_path,
                format="mp3",
                parameters=["-ar", "16000", "-ac", "1"]  # 16kHz, mono
            )

            chunks.append((str(chunk_path), start_seconds))

        logger.info(f"Successfully created {len(chunks)} audio chunks")
        return chunks

    def optimize_for_whisper(self, file_path: str, output_path: str = None) -> str:
        """Optimize audio file for Whisper API (mono, 16kHz, mp3).

        Args:
            file_path: Path to the input audio file
            output_path: Optional output path (if None, overwrites original)

        Returns:
            Path to the optimized audio file
        """
        logger.info(f"Optimizing audio for Whisper: {file_path}")

        # Load audio
        audio = AudioSegment.from_file(file_path)

        # Convert to mono
        if audio.channels > 1:
            logger.info("Converting to mono")
            audio = audio.set_channels(1)

        # Set sample rate to 16kHz (optimal for Whisper)
        if audio.frame_rate != 16000:
            logger.info("Resampling to 16kHz")
            audio = audio.set_frame_rate(16000)

        # Determine output path
        if output_path is None:
            output_path = file_path

        # Export optimized audio
        audio.export(
            output_path,
            format="mp3",
            parameters=["-q:a", "2"]  # Good quality
        )

        size_mb = self.get_file_size_mb(output_path)
        logger.info(f"Optimized audio saved: {output_path} ({size_mb:.2f} MB)")

        return output_path

    def cleanup_chunks(self, chunk_paths: List[Tuple[str, float]]):
        """Delete temporary chunk files.

        Args:
            chunk_paths: List of (chunk_path, offset) tuples
        """
        logger.info("Cleaning up temporary chunk files")
        for chunk_path, _ in chunk_paths:
            try:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                    logger.debug(f"Deleted: {chunk_path}")
            except Exception as e:
                logger.warning(f"Failed to delete {chunk_path}: {e}")
