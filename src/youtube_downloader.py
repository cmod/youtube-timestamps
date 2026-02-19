"""YouTube video downloader using yt-dlp."""

import re
from pathlib import Path
from typing import Dict, Optional
import yt_dlp
from src.utils.logger import logger


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL.

    Args:
        url: YouTube video URL

    Returns:
        Video ID or None if not found
    """
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


class YouTubeDownloader:
    """Download audio from YouTube videos."""

    def __init__(self, output_dir: str = "temp"):
        """Initialize the YouTube downloader.

        Args:
            output_dir: Directory to save downloaded audio files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def validate_url(self, url: str) -> bool:
        """Check if the URL is a valid YouTube URL.

        Args:
            url: URL to validate

        Returns:
            True if valid YouTube URL, False otherwise
        """
        youtube_regex = (
            r'(https?://)?(www\.)?'
            r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
            r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        )
        match = re.match(youtube_regex, url)
        return match is not None

    def get_video_info(self, url: str) -> Dict[str, any]:
        """Extract video metadata without downloading.

        Args:
            url: YouTube video URL

        Returns:
            Dictionary containing video metadata

        Raises:
            Exception: If unable to fetch video info
        """
        if not self.validate_url(url):
            raise ValueError(f"Invalid YouTube URL: {url}")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Fetching video info: {url}")
                info = ydl.extract_info(url, download=False)

                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),  # seconds
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', 'Unknown'),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                }
        except Exception as e:
            logger.error(f"Failed to fetch video info: {e}")
            raise

    def download_audio(self, url: str, filename: Optional[str] = None, use_fallback_format: bool = False) -> str:
        """Download audio from YouTube video.

        Args:
            url: YouTube video URL
            filename: Optional custom filename (without extension)
            use_fallback_format: If True, tries alternative format for live streams

        Returns:
            Path to the downloaded audio file

        Raises:
            ValueError: If URL is invalid
            Exception: If download fails
        """
        if not self.validate_url(url):
            raise ValueError(f"Invalid YouTube URL: {url}")

        # Determine output filename
        if filename:
            output_template = str(self.output_dir / f"{filename}.%(ext)s")
        else:
            output_template = str(self.output_dir / "%(title)s.%(ext)s")

        # Configure yt-dlp options
        # For live streams, sometimes 'ba' (best audio) works better than 'bestaudio/best'
        format_string = 'ba/b' if use_fallback_format else 'bestaudio/best'

        ydl_opts = {
            'format': format_string,
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
            'extract_audio': True,
            'prefer_ffmpeg': True,
            # Options for handling live streams and fragment errors
            'fragment_retries': 10,  # Retry fragments up to 10 times
            'retries': 10,  # General retry count
            'extractor_retries': 5,  # Retry info extraction
            # Use Android client to avoid SABR streaming issues
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs']
                }
            }
        }

        # Use cookies if available
        cookies_file = Path('cookies.txt')
        if cookies_file.exists():
            ydl_opts['cookiefile'] = str(cookies_file)
            logger.info("Using cookies.txt for authentication")

        try:
            logger.info(f"Downloading audio from: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                # Determine the actual output filename
                if filename:
                    audio_file = self.output_dir / f"{filename}.mp3"
                else:
                    title = info.get('title', 'audio')
                    # Sanitize title for filename
                    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                    audio_file = self.output_dir / f"{safe_title}.mp3"

                # Verify the file was actually created
                if not audio_file.exists():
                    raise Exception(
                        "Download appeared to succeed but audio file was not created. "
                        "This usually means YouTube blocked the download (HTTP 403). "
                        "Try: 1) Export YouTube cookies to cookies.txt, or "
                        "2) Wait and try again later, or "
                        "3) Check if the video is accessible on YouTube directly."
                    )

                logger.info(f"Audio downloaded successfully: {audio_file}")
                return str(audio_file)

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Private video" in error_msg:
                raise Exception("This video is private and cannot be accessed.")
            elif "Video unavailable" in error_msg:
                raise Exception("This video is unavailable or has been removed.")
            elif "age-restricted" in error_msg.lower():
                raise Exception("This video is age-restricted. Consider using authentication.")
            else:
                logger.error(f"Download failed: {e}")
                raise Exception(f"Failed to download video: {error_msg}")
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise

    def cleanup_file(self, file_path: str):
        """Delete a downloaded file.

        Args:
            file_path: Path to the file to delete
        """
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete {file_path}: {e}")
