#!/usr/bin/env python3
"""YouTube Timestamps Generator - CLI interface."""

import sys
from pathlib import Path
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markdown import Markdown

from src.utils.config_loader import load_config
from src.utils.logger import setup_logger
from src.utils.audio_processor import AudioProcessor
from src.youtube_downloader import YouTubeDownloader, extract_video_id
from src.transcriber import WhisperTranscriber, InsufficientQuotaError
from src.topic_analyzer import TopicAnalyzer
from src.timestamp_formatter import TimestampFormatter
from src.cache_manager import CacheManager

console = Console()
logger = setup_logger()


def estimate_cost(duration_seconds: float) -> str:
    """Estimate the cost for processing a video.

    Args:
        duration_seconds: Video duration in seconds

    Returns:
        Cost estimate string
    """
    duration_minutes = duration_seconds / 60
    whisper_cost = duration_minutes * 0.006  # $0.006 per minute
    gpt_cost = 0.02  # ~$0.02 per video
    total_cost = whisper_cost + gpt_cost

    return f"${total_cost:.2f}"


@click.command()
@click.argument('url')
@click.option(
    '--output', '-o',
    default='output/timestamps.txt',
    help='Output file path'
)
@click.option(
    '--min-duration',
    default=30,
    type=int,
    help='Minimum topic duration in seconds'
)
@click.option(
    '--format', '-f',
    'output_format',
    type=click.Choice(['youtube', 'markdown', 'json']),
    default='youtube',
    help='Output format'
)
@click.option(
    '--save-transcript/--no-save-transcript',
    default=True,
    help='Save full transcript to file (default: enabled)'
)
@click.option(
    '--qa-mode',
    is_flag=True,
    help='Optimize for presentation + Q&A format (detailed Q&A timestamps)'
)
@click.option(
    '--force-reprocess',
    is_flag=True,
    help='Force re-download and re-transcription (ignore cache)'
)
@click.option(
    '--keep-files',
    is_flag=True,
    help='Keep temporary audio files'
)
@click.option(
    '--provider',
    type=click.Choice(['openai', 'gemini']),
    default='openai',
    help='AI provider for topic analysis (openai or gemini, default: openai)'
)
def main(url, output, min_duration, output_format, save_transcript, qa_mode, force_reprocess, keep_files, provider):
    """Generate YouTube timestamps from video URL.

    Example:
        python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
    """
    try:
        # Display header
        console.print(
            Panel.fit(
                "[bold cyan]YouTube Timestamps Generator[/bold cyan]\n"
                "[dim]Powered by OpenAI Whisper & GPT-4[/dim]",
                border_style="cyan"
            )
        )

        # Load configuration
        console.print("\n[yellow]Loading configuration...[/yellow]")
        try:
            config = load_config()
            api_key = config['openai_api_key']
        except Exception as e:
            console.print(f"[red]Error loading configuration: {e}[/red]")
            console.print("\n[yellow]Please ensure:[/yellow]")
            console.print("1. .env file exists with OPENAI_API_KEY")
            console.print("2. config.yaml exists")
            sys.exit(1)

        # Extract video ID
        video_id = extract_video_id(url)
        if not video_id:
            console.print("[red]Error: Could not extract video ID from URL[/red]")
            sys.exit(1)

        console.print(f"[dim]Video ID: {video_id}[/dim]")

        if qa_mode:
            console.print("[bold cyan]📝 Q&A Mode Enabled[/bold cyan]")
            console.print("[dim]Optimized for presentation + Q&A format[/dim]")

        # Display provider info
        if provider == 'gemini':
            if not config.get('google_api_key'):
                console.print("[red]Error: Google API key required for Gemini provider[/red]")
                console.print("[yellow]Please add GOOGLE_API_KEY to your .env file[/yellow]")
                console.print("[yellow]Get your key from: https://aistudio.google.com/app/apikey[/yellow]")
                sys.exit(1)
            console.print("[bold cyan]🤖 Using Gemini for analysis[/bold cyan]")
            console.print("[dim]Full transcript analysis with large context window[/dim]")

        # Initialize components
        cache_manager = CacheManager()
        downloader = YouTubeDownloader(output_dir="temp")
        audio_processor = AudioProcessor(
            max_chunk_size_mb=config['audio']['chunk_size_mb'],
            chunk_duration=config['audio']['chunk_duration']
        )
        transcriber = WhisperTranscriber(
            api_key=api_key,
            model=config['transcription']['model']
        )
        analyzer = TopicAnalyzer(
            api_key=api_key,
            model=config['topic_analysis']['model'],
            temperature=config['topic_analysis']['temperature'],
            min_topic_duration=min_duration,
            qa_mode=qa_mode,
            provider=provider,
            google_api_key=config.get('google_api_key', '')
        )
        formatter = TimestampFormatter()

        # Check cache status
        if not force_reprocess:
            cache_summary = cache_manager.get_cache_summary(video_id)
            if cache_summary['cache_complete']:
                console.print("\n[bold green]✓ Complete cache found![/bold green]")
                console.print("[dim]Skipping download and transcription[/dim]")
                console.print("[dim]Use --force-reprocess to re-process from scratch[/dim]")

        # Step 1: Get video info
        console.print("\n[yellow]Fetching video information...[/yellow]")
        video_info = None

        # Try cache first
        if not force_reprocess:
            video_info = cache_manager.get_cached_video_info(video_id)

        # Fetch from YouTube if not cached
        if video_info is None:
            try:
                video_info = downloader.get_video_info(url)
                cache_manager.save_video_info(video_id, video_info)
            except Exception as e:
                console.print(f"[red]✗ Failed to fetch video info: {e}[/red]")
                sys.exit(1)

        console.print(f"[green]✓[/green] Title: {video_info['title']}")
        console.print(f"[green]✓[/green] Duration: {formatter.seconds_to_duration(video_info['duration'])}")

        # Show cost estimate (only if we need to process)
        cached_audio = cache_manager.get_cached_audio(video_id) if not force_reprocess else None
        cached_transcript = cache_manager.get_cached_transcript(video_id) if not force_reprocess else None

        if not cached_transcript:
            cost_estimate = estimate_cost(video_info['duration'])
            console.print(f"[dim]Estimated cost: ~{cost_estimate}[/dim]")
        else:
            console.print(f"[dim]Using cached data - no API cost[/dim]")

        # Step 2: Download audio (or use cache)
        audio_file = None

        if cached_audio:
            console.print(f"\n[green]✓[/green] Using cached audio")
            audio_file = cached_audio
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Downloading audio...", total=None)

                try:
                    audio_file = downloader.download_audio(url, filename=f"{video_id}_audio")
                    temp_audio_file = audio_file  # Track for cleanup
                    progress.update(task, description="[green]✓ Audio downloaded")
                    console.print(f"[green]✓[/green] Audio saved: {audio_file}")

                    # Save to cache
                    cache_manager.save_audio(video_id, audio_file)
                except Exception as e:
                    progress.update(task, description=f"[red]✗ Download failed")
                    console.print(f"[red]Error: {e}[/red]")
                    sys.exit(1)

        # Step 3: Transcribe audio (or use cache)
        transcript = None
        chunks = None  # Track chunks for cleanup
        temp_audio_file = None  # Track temp audio for cleanup

        if cached_transcript:
            console.print(f"\n[green]✓[/green] Using cached transcript")
            transcript = cached_transcript
            console.print(f"[green]✓[/green] Transcript length: {len(transcript['text'])} characters")
        else:
            # Need to transcribe
            # Process audio (chunk if needed)
            console.print("\n[yellow]Processing audio...[/yellow]")
            chunks = None
            needs_chunking = audio_processor.needs_chunking(audio_file)

            if needs_chunking:
                console.print("[yellow]File is large, splitting into chunks...[/yellow]")
                try:
                    chunks = audio_processor.chunk_audio(audio_file, output_dir="temp")
                    console.print(f"[green]✓[/green] Created {len(chunks)} audio chunks")
                except Exception as e:
                    console.print(f"[red]✗ Failed to chunk audio: {e}[/red]")
                    sys.exit(1)

            # Transcribe audio
            console.print("\n[yellow]Transcribing audio...[/yellow]")
            if chunks:
                console.print("[dim]Resume enabled - cached chunks will be skipped[/dim]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Transcribing audio with Whisper API...", total=None)

                try:
                    if chunks:
                        transcript = transcriber.transcribe_chunks(chunks)
                    else:
                        transcript = transcriber.transcribe_file(audio_file)

                    progress.update(task, description="[green]✓ Transcription complete")
                    console.print(f"[green]✓[/green] Transcript length: {len(transcript['text'])} characters")

                    # Save transcript to cache
                    cache_manager.save_transcript(video_id, transcript)

                except InsufficientQuotaError as e:
                    progress.update(task, description="[red]✗ Quota exceeded")
                    console.print("\n")
                    console.print(Panel.fit(
                        "[bold red]❌ OpenAI API Quota Exceeded[/bold red]\n\n"
                        "[yellow]Your OpenAI account is out of credits.[/yellow]\n\n"
                        "To continue:\n"
                        "1. Add credits at: [cyan]https://platform.openai.com/account/billing[/cyan]\n"
                        "2. Run the same command again - it will resume where it left off!\n\n"
                        "[dim]Progress has been saved and chunks will not be re-transcribed.[/dim]",
                        border_style="red",
                        title="💳 Action Required"
                    ))
                    sys.exit(1)

                except Exception as e:
                    progress.update(task, description="[red]✗ Transcription failed")
                    console.print(f"[red]Error: {e}[/red]")
                    sys.exit(1)

        # Save transcript to output files
        if save_transcript and transcript:
            try:
                # Create safe filename from video title
                safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_title = safe_title[:100]  # Limit length

                transcript_txt = Path("output") / f"{safe_title}_transcript.txt"
                transcript_json = Path("output") / f"{safe_title}_transcript.json"

                transcriber.save_transcript(transcript, str(transcript_txt), include_timestamps=True, timestamp_interval=60)
                transcriber.save_transcript_json(transcript, str(transcript_json))

                console.print(f"[green]✓[/green] Transcript saved: {transcript_txt}")
                console.print(f"[dim]Raw JSON: {transcript_json}[/dim]")
            except Exception as e:
                logger.warning(f"Failed to save transcript: {e}")

        # Step 4: Analyze topics
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            model_name = "Gemini" if provider == "gemini" else "GPT-4"
            task = progress.add_task(f"[cyan]Analyzing topics with {model_name}...", total=None)

            try:
                topics = analyzer.analyze_transcript(transcript, video_info['title'])
                progress.update(task, description="[green]✓ Topic analysis complete")
                console.print(f"[green]✓[/green] Identified {len(topics)} chapters")
            except Exception as e:
                progress.update(task, description="[red]✗ Analysis failed")
                console.print(f"[red]Error: {e}[/red]")
                sys.exit(1)

        # Step 6: Format output
        console.print("\n[yellow]Formatting timestamps...[/yellow]")

        if output_format == 'youtube':
            output_text = formatter.format_for_youtube(
                topics,
                video_info['title'],
                video_info['duration']
            )
        elif output_format == 'markdown':
            output_text = formatter.format_for_markdown(
                topics,
                url,
                video_info['title']
            )
        elif output_format == 'json':
            output_text = formatter.format_as_json(topics)

        # Step 7: Save output
        # If using default output path, generate unique filename from video title
        if output == 'output/timestamps.txt':
            # Create safe filename from video title
            safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title[:100]  # Limit length

            # Determine extension based on format
            extension = '.txt' if output_format != 'json' else '.json'
            output_path = Path("output") / f"{safe_title}_timestamps{extension}"
        else:
            output_path = Path(output)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_text)

        console.print(f"[green]✓[/green] Timestamps saved to: {output}")

        # Display preview
        console.print("\n[bold cyan]Preview:[/bold cyan]")
        console.print(Panel(output_text, border_style="green"))

        # Cleanup temporary files (not cache)
        if not keep_files:
            console.print("\n[yellow]Cleaning up temporary files...[/yellow]")
            try:
                # Only delete temp audio file (not cached audio)
                if temp_audio_file:
                    downloader.cleanup_file(temp_audio_file)
                    logger.info(f"Deleted temp audio: {temp_audio_file}")

                # Clean up chunks if they were created
                if chunks:
                    audio_processor.cleanup_chunks(chunks)
                    logger.info("Deleted audio chunks")

                console.print("[green]✓[/green] Cleanup complete")
            except Exception as e:
                console.print(f"[yellow]Warning: Cleanup failed: {e}[/yellow]")

        # Success message
        console.print(
            "\n[bold green]✓ Success![/bold green] "
            f"Generated timestamps for [cyan]{video_info['title']}[/cyan]"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected error in main")
        sys.exit(1)


if __name__ == '__main__':
    main()
