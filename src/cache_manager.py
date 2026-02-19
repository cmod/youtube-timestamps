"""Cache manager for storing processed video data."""

import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from src.utils.logger import logger


class CacheManager:
    """Manage persistent cache for video processing."""

    def __init__(self, cache_dir: str = "cache"):
        """Initialize cache manager.

        Args:
            cache_dir: Base directory for cache storage
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_video_cache_dir(self, video_id: str) -> Path:
        """Get cache directory for a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            Path to video cache directory
        """
        video_cache = self.cache_dir / video_id
        video_cache.mkdir(parents=True, exist_ok=True)
        return video_cache

    def get_cached_audio(self, video_id: str) -> Optional[str]:
        """Get cached audio file path if it exists.

        Args:
            video_id: YouTube video ID

        Returns:
            Path to cached audio file or None
        """
        audio_path = self._get_video_cache_dir(video_id) / "audio.mp3"
        if audio_path.exists():
            logger.info(f"✓ Found cached audio for video {video_id}")
            return str(audio_path)
        return None

    def save_audio(self, video_id: str, audio_path: str) -> str:
        """Save audio file to cache.

        Args:
            video_id: YouTube video ID
            audio_path: Path to audio file to cache

        Returns:
            Path to cached audio file
        """
        cache_path = self._get_video_cache_dir(video_id) / "audio.mp3"

        # Copy audio file to cache
        shutil.copy2(audio_path, cache_path)
        logger.info(f"✓ Cached audio for video {video_id}")

        return str(cache_path)

    def get_cached_transcript(self, video_id: str) -> Optional[Dict]:
        """Get cached transcript if it exists.

        Args:
            video_id: YouTube video ID

        Returns:
            Transcript dictionary or None
        """
        transcript_path = self._get_video_cache_dir(video_id) / "transcript.json"
        if transcript_path.exists():
            try:
                with open(transcript_path, 'r') as f:
                    transcript = json.load(f)
                logger.info(f"✓ Found cached transcript for video {video_id}")
                return transcript
            except Exception as e:
                logger.warning(f"Failed to load cached transcript: {e}")
        return None

    def save_transcript(self, video_id: str, transcript: Dict):
        """Save transcript to cache.

        Args:
            video_id: YouTube video ID
            transcript: Transcript dictionary
        """
        transcript_path = self._get_video_cache_dir(video_id) / "transcript.json"

        with open(transcript_path, 'w') as f:
            json.dump(transcript, f, indent=2)

        logger.info(f"✓ Cached transcript for video {video_id}")

    def get_cached_video_info(self, video_id: str) -> Optional[Dict]:
        """Get cached video metadata if it exists.

        Args:
            video_id: YouTube video ID

        Returns:
            Video info dictionary or None
        """
        info_path = self._get_video_cache_dir(video_id) / "video_info.json"
        if info_path.exists():
            try:
                with open(info_path, 'r') as f:
                    video_info = json.load(f)
                logger.info(f"✓ Found cached video info for {video_id}")
                return video_info
            except Exception as e:
                logger.warning(f"Failed to load cached video info: {e}")
        return None

    def save_video_info(self, video_id: str, video_info: Dict):
        """Save video metadata to cache.

        Args:
            video_id: YouTube video ID
            video_info: Video info dictionary
        """
        info_path = self._get_video_cache_dir(video_id) / "video_info.json"

        with open(info_path, 'w') as f:
            json.dump(video_info, f, indent=2)

        logger.debug(f"Cached video info for {video_id}")

    def has_complete_cache(self, video_id: str) -> bool:
        """Check if video has complete cache (audio + transcript).

        Args:
            video_id: YouTube video ID

        Returns:
            True if both audio and transcript are cached
        """
        has_audio = self.get_cached_audio(video_id) is not None
        has_transcript = self.get_cached_transcript(video_id) is not None
        return has_audio and has_transcript

    def clear_video_cache(self, video_id: str):
        """Clear cache for a specific video.

        Args:
            video_id: YouTube video ID
        """
        video_cache = self._get_video_cache_dir(video_id)
        if video_cache.exists():
            shutil.rmtree(video_cache)
            logger.info(f"Cleared cache for video {video_id}")

    def get_cache_summary(self, video_id: str) -> Dict:
        """Get summary of what's cached for a video.

        Args:
            video_id: YouTube video ID

        Returns:
            Dictionary with cache status
        """
        return {
            'video_id': video_id,
            'has_audio': self.get_cached_audio(video_id) is not None,
            'has_transcript': self.get_cached_transcript(video_id) is not None,
            'has_video_info': self.get_cached_video_info(video_id) is not None,
            'cache_complete': self.has_complete_cache(video_id)
        }
