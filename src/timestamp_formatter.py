"""Format timestamps for YouTube descriptions."""

from typing import List, Tuple
from datetime import timedelta
from src.utils.logger import logger


class TimestampFormatter:
    """Format timestamps for YouTube video descriptions."""

    @staticmethod
    def seconds_to_youtube_format(seconds: int) -> str:
        """Convert seconds to YouTube timestamp format.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted timestamp (HH:MM:SS)

        Examples:
            123 -> "00:02:03"
            3723 -> "01:02:03"
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        # Always use HH:MM:SS format for YouTube
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def seconds_to_duration(seconds: int) -> str:
        """Convert seconds to readable duration.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted duration string

        Examples:
            123 -> "2m 3s"
            3723 -> "1h 2m 3s"
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)

    def validate_timestamps(self, topics: List[Tuple[int, str]]) -> bool:
        """Validate that timestamps are in chronological order.

        Args:
            topics: List of (timestamp, description) tuples

        Returns:
            True if valid, False otherwise
        """
        if not topics:
            return True

        for i in range(len(topics) - 1):
            if topics[i][0] >= topics[i + 1][0]:
                logger.warning(
                    f"Timestamps not in order: {topics[i][0]} >= {topics[i + 1][0]}"
                )
                return False

        return True

    def format_for_youtube(
        self,
        topics: List[Tuple[int, str]],
        video_title: str = "",
        video_duration: int = 0
    ) -> str:
        """Format timestamps for YouTube video description.

        Args:
            topics: List of (timestamp_seconds, description) tuples
            video_title: Optional video title
            video_duration: Optional video duration in seconds

        Returns:
            Formatted string ready for YouTube description
        """
        logger.info(f"Formatting {len(topics)} timestamps for YouTube")

        # Validate timestamps
        if not self.validate_timestamps(topics):
            logger.warning("Timestamps are not in chronological order")

        # Build output
        lines = []

        # Add header if video title provided
        if video_title:
            lines.append(f"Video: {video_title}")

        if video_duration > 0:
            duration_str = self.seconds_to_duration(video_duration)
            lines.append(f"Duration: {duration_str}")

        if video_title or video_duration:
            lines.append("")  # Blank line

        # Add timestamps header
        lines.append("Chapters:")

        # Add each timestamp
        for timestamp, description in topics:
            time_str = self.seconds_to_youtube_format(timestamp)
            lines.append(f"{time_str} - {description}")

        return '\n'.join(lines)

    def format_for_markdown(
        self,
        topics: List[Tuple[int, str]],
        video_url: str = "",
        video_title: str = ""
    ) -> str:
        """Format timestamps as Markdown with clickable links.

        Args:
            topics: List of (timestamp_seconds, description) tuples
            video_url: YouTube video URL
            video_title: Optional video title

        Returns:
            Markdown formatted string
        """
        lines = []

        # Add title
        if video_title:
            lines.append(f"# {video_title}\n")

        # Add timestamps
        lines.append("## Chapters\n")

        for timestamp, description in topics:
            time_str = self.seconds_to_youtube_format(timestamp)

            if video_url:
                # Create clickable timestamp link
                url_with_timestamp = f"{video_url}&t={timestamp}s"
                lines.append(f"- [{time_str}]({url_with_timestamp}) - {description}")
            else:
                lines.append(f"- {time_str} - {description}")

        return '\n'.join(lines)

    def format_as_json(self, topics: List[Tuple[int, str]]) -> str:
        """Format timestamps as JSON.

        Args:
            topics: List of (timestamp_seconds, description) tuples

        Returns:
            JSON string
        """
        import json

        chapters = []
        for timestamp, description in topics:
            chapters.append({
                "timestamp": timestamp,
                "time": self.seconds_to_youtube_format(timestamp),
                "description": description
            })

        return json.dumps({"chapters": chapters}, indent=2)

    def format_with_durations(
        self,
        topics: List[Tuple[int, str]],
        video_duration: int = None
    ) -> str:
        """Format timestamps with duration for each chapter.

        Args:
            topics: List of (timestamp_seconds, description) tuples
            video_duration: Total video duration in seconds

        Returns:
            Formatted string with durations
        """
        lines = ["Chapters with Durations:\n"]

        for i, (timestamp, description) in enumerate(topics):
            time_str = self.seconds_to_youtube_format(timestamp)

            # Calculate chapter duration
            if i < len(topics) - 1:
                next_timestamp = topics[i + 1][0]
                duration = next_timestamp - timestamp
            elif video_duration:
                duration = video_duration - timestamp
            else:
                duration = None

            if duration:
                duration_str = self.seconds_to_duration(duration)
                lines.append(f"{time_str} - {description} ({duration_str})")
            else:
                lines.append(f"{time_str} - {description}")

        return '\n'.join(lines)
