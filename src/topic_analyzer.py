"""Topic analysis using GPT-4 or Gemini to identify chapter boundaries."""

import json
from typing import Dict, List, Tuple, Optional
from openai import OpenAI
from src.utils.logger import logger

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class TopicAnalyzer:
    """Analyze transcript to identify topic changes and generate timestamps."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.3,
        min_topic_duration: int = 30,
        qa_mode: bool = False,
        provider: str = "openai",
        google_api_key: str = ""
    ):
        """Initialize the topic analyzer.

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4-turbo-preview for OpenAI, gemini-2.0-flash-exp for Gemini)
            temperature: Sampling temperature (default: 0.3)
            min_topic_duration: Minimum duration for topics in seconds (default: 30)
            qa_mode: If True, optimizes for presentation + Q&A format (default: False)
            provider: AI provider to use ('openai' or 'gemini', default: 'openai')
            google_api_key: Google API key (required if provider='gemini')
        """
        self.provider = provider.lower()
        self.temperature = temperature
        self.min_topic_duration = min_topic_duration
        self.qa_mode = qa_mode

        if self.provider == "openai":
            self.client = OpenAI(api_key=api_key)
            self.model = model
        elif self.provider == "gemini":
            if not GEMINI_AVAILABLE:
                raise ImportError("google-genai package not installed. Run: uv sync")
            if not google_api_key:
                raise ValueError("Google API key required when using Gemini provider")
            self.client = genai.Client(api_key=google_api_key)
            # Use gemini-2.5-flash (latest) or gemini-2.0-flash as fallback
            self.model = model if model != "gpt-4-turbo-preview" else "gemini-2.5-flash"
            logger.info(f"Using Gemini model: {self.model}")
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'openai' or 'gemini'")

    def analyze_transcript(
        self,
        transcript: Dict,
        video_title: str = ""
    ) -> List[Tuple[int, str]]:
        """Analyze transcript to identify topic changes.

        Args:
            transcript: Transcript dictionary with text and word timestamps
            video_title: Optional video title for context

        Returns:
            List of (timestamp_seconds, description) tuples
        """
        logger.info("Analyzing transcript for topic changes")

        # Get intervals with text for analysis
        from src.transcriber import WhisperTranscriber
        transcriber = WhisperTranscriber(api_key="dummy")  # Just for utility method

        # For Gemini, use full transcript analysis
        if self.provider == "gemini":
            return self._analyze_with_gemini(transcript, video_title, transcriber)

        # For Q&A mode with OpenAI, use two-pass approach
        if self.qa_mode:
            return self._analyze_qa_transcript(transcript, video_title, transcriber)

        # Standard mode: Use longer intervals for long videos to avoid overwhelming GPT
        if transcript.get('words'):
            video_duration = transcript['words'][-1]['end']
            # Use 60s intervals for videos >30 min, 45s for >15 min, 30s otherwise
            if video_duration > 1800:  # 30 minutes
                interval = 60
            elif video_duration > 900:  # 15 minutes
                interval = 45
            else:
                interval = 30
            logger.info(f"Using {interval}s intervals for {video_duration/60:.1f} min video")
        else:
            interval = 30

        intervals = transcriber.get_transcript_at_intervals(transcript, interval=interval)

        if not intervals:
            logger.warning("No transcript intervals found")
            return [(0, "Video content")]

        # Format transcript with timestamps for GPT
        formatted_transcript = self._format_for_gpt(intervals)

        # Create analysis prompt
        prompt = self._create_analysis_prompt(formatted_transcript, video_title)

        try:
            # Call GPT-4 for analysis
            logger.info(f"Calling {self.model} for topic analysis")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing video transcripts and identifying "
                                   "meaningful topic boundaries to create chapter timestamps."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )

            # Parse response
            content = response.choices[0].message.content

            # Save response to debug file
            try:
                from pathlib import Path
                debug_dir = Path("temp/debug")
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_file = debug_dir / "gpt_response.json"
                with open(debug_file, 'w') as f:
                    f.write(content)
                logger.info(f"GPT response saved to: {debug_file}")
            except Exception as e:
                logger.warning(f"Failed to save debug file: {e}")

            logger.debug(f"GPT response preview: {content[:500]}...")
            topics = self._parse_gpt_response(content)

            # Filter short topics
            filtered_topics = self._filter_short_topics(topics)
            logger.info(f"After filtering: {len(filtered_topics)} topics")

            # Ensure there's always an intro at 0:00 if not present
            if not filtered_topics or filtered_topics[0][0] > 0:
                filtered_topics.insert(0, (0, "Introduction"))

            # If we got good results, use them
            if filtered_topics and len(filtered_topics) > 1:
                logger.info(f"✓ Identified {len(filtered_topics)} meaningful topic boundaries")
                return filtered_topics
            else:
                logger.warning("GPT returned too few topics, using fallback")
                return self._create_fallback_chapters(transcript)

        except Exception as e:
            logger.error(f"Topic analysis failed: {e}")
            import traceback
            logger.debug(f"Full error: {traceback.format_exc()}")
            # Fallback: create time-based chapters every 5 minutes
            logger.warning("Using fallback time-based chapters due to error")
            return self._create_fallback_chapters(transcript)

    def _analyze_qa_transcript(
        self,
        transcript: Dict,
        video_title: str,
        transcriber
    ) -> List[Tuple[int, str]]:
        """Two-pass analysis for Q&A videos.

        Args:
            transcript: Transcript dictionary
            video_title: Video title
            transcriber: Transcriber instance for utilities

        Returns:
            List of (timestamp, description) tuples
        """
        logger.info("Q&A mode: Two-pass analysis")

        # Pass 1: Find where Q&A starts (use broad intervals)
        logger.info("Pass 1: Locating Q&A section...")
        video_duration = int(transcript['words'][-1]['end']) if transcript.get('words') else 1800
        logger.info(f"Video duration: {video_duration}s ({video_duration/60:.1f} minutes)")
        broad_intervals = transcriber.get_transcript_at_intervals(transcript, interval=120)  # 2-minute intervals

        qa_start_time = self._find_qa_start(broad_intervals, video_title)

        if qa_start_time is None:
            logger.warning("Could not identify Q&A start, analyzing entire video")
            qa_start_time = 0

        logger.info(f"Q&A section starts at approximately {qa_start_time}s ({qa_start_time/60:.1f} minutes)")

        # Pass 2: Analyze presentation section with standard approach
        logger.info("Pass 2: Analyzing presentation section...")
        presentation_topics = []

        if qa_start_time > 300:  # Only if presentation is > 5 minutes
            # Get presentation portion with 60-second intervals
            presentation_intervals = [
                (ts, text) for ts, text in transcriber.get_transcript_at_intervals(transcript, interval=60)
                if ts < qa_start_time
            ]

            if presentation_intervals:
                pres_transcript = self._format_for_gpt(presentation_intervals)
                pres_prompt = self._create_presentation_prompt(pres_transcript, video_title, qa_start_time)

                try:
                    logger.info(f"Calling {self.model} for presentation analysis")
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You analyze presentation content to identify major sections."},
                            {"role": "user", "content": pres_prompt}
                        ],
                        temperature=self.temperature,
                        response_format={"type": "json_object"}
                    )

                    content = response.choices[0].message.content
                    presentation_topics = self._parse_gpt_response(content)

                    # Filter out any timestamps beyond Q&A start or video duration
                    presentation_topics = [(ts, desc) for ts, desc in presentation_topics if ts < qa_start_time and ts <= video_duration]

                    # Save debug
                    try:
                        from pathlib import Path
                        debug_dir = Path("temp/debug")
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        with open(debug_dir / "gpt_presentation_response.json", 'w') as f:
                            f.write(content)
                    except:
                        pass

                    logger.info(f"✓ Identified {len(presentation_topics)} presentation chapters")
                except Exception as e:
                    logger.warning(f"Presentation analysis failed: {e}")
                    presentation_topics = [(0, "Presentation")]
            else:
                presentation_topics = [(0, "Presentation")]
        else:
            presentation_topics = [(0, "Presentation")]

        # Pass 3: Analyze Q&A section in detail with dense intervals
        logger.info("Pass 3: Analyzing Q&A section for individual questions...")

        # Get just the Q&A portion with 15-second intervals for better precision
        qa_intervals = [
            (ts, text) for ts, text in transcriber.get_transcript_at_intervals(transcript, interval=15)
            if ts >= qa_start_time
        ]

        if not qa_intervals:
            logger.warning("No Q&A content found")
            return presentation_topics + [(int(qa_start_time), "Q&A begins")]

        # Format Q&A section for detailed analysis
        qa_transcript = self._format_for_gpt(qa_intervals)

        # Create focused Q&A prompt
        prompt = self._create_qa_detail_prompt(qa_transcript, video_title, qa_start_time, video_duration)

        try:
            # Call GPT-4 for detailed Q&A analysis
            logger.info(f"Calling {self.model} for detailed Q&A analysis")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing Q&A sessions and identifying individual questions."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content

            # Save debug output
            try:
                from pathlib import Path
                debug_dir = Path("temp/debug")
                debug_dir.mkdir(parents=True, exist_ok=True)
                with open(debug_dir / "gpt_qa_response.json", 'w') as f:
                    f.write(content)
                logger.info(f"GPT Q&A response saved to: temp/debug/gpt_qa_response.json")
            except:
                pass

            qa_topics = self._parse_gpt_response(content)

            # Filter out any timestamps beyond video duration
            qa_topics = [(ts, desc) for ts, desc in qa_topics if ts <= video_duration]
            invalid_count = len(self._parse_gpt_response(content)) - len(qa_topics)
            if invalid_count > 0:
                logger.warning(f"Filtered out {invalid_count} Q&A timestamps beyond video duration ({video_duration}s)")

            # Combine: presentation topics + Q&A marker + Q&A topics
            final_topics = presentation_topics + [(int(qa_start_time), "Q&A begins")] + qa_topics

            # Filter and sort
            final_topics = self._filter_short_topics(final_topics)
            final_topics.sort(key=lambda x: x[0])

            logger.info(f"✓ Total: {len(presentation_topics)} presentation + {len(qa_topics)} Q&A chapters")
            return final_topics

        except Exception as e:
            logger.error(f"Q&A analysis failed: {e}")
            import traceback
            logger.debug(f"Full error: {traceback.format_exc()}")

            # Fallback
            return presentation_topics + [(int(qa_start_time), "Q&A begins")]

    def _analyze_with_gemini(
        self,
        transcript: Dict,
        video_title: str,
        transcriber
    ) -> List[Tuple[int, str]]:
        """Analyze full transcript with Gemini's large context window.

        Args:
            transcript: Transcript dictionary
            video_title: Video title
            transcriber: Transcriber instance for utilities

        Returns:
            List of (timestamp, description) tuples
        """
        logger.info("Gemini mode: Full transcript analysis")

        video_duration = int(transcript['words'][-1]['end']) if transcript.get('words') else 1800
        logger.info(f"Video duration: {video_duration}s ({video_duration/60:.1f} minutes)")

        # For Q&A mode with Gemini, use fine-grained intervals (10 seconds)
        # Gemini can handle it with its massive context window
        if self.qa_mode:
            interval = 10
            logger.info(f"Q&A mode: Using {interval}s intervals for precision")
        else:
            interval = 30
            logger.info(f"Standard mode: Using {interval}s intervals")

        # Get full transcript with intervals
        intervals = transcriber.get_transcript_at_intervals(transcript, interval=interval)
        full_transcript = self._format_for_gpt(intervals)

        # Create prompt for Gemini
        if self.qa_mode:
            prompt = self._create_gemini_qa_prompt(full_transcript, video_title, video_duration)
        else:
            prompt = self._create_gemini_standard_prompt(full_transcript, video_title)

        try:
            logger.info(f"Calling Gemini {self.model}...")
            logger.info(f"Transcript length: {len(full_transcript)} characters")

            # Call Gemini using new google.genai API
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=self.temperature,
                    response_mime_type="application/json"
                )
            )

            content = response.text

            # Save debug
            try:
                from pathlib import Path
                debug_dir = Path("temp/debug")
                debug_dir.mkdir(parents=True, exist_ok=True)
                with open(debug_dir / "gemini_response.json", 'w') as f:
                    f.write(content)
                logger.info(f"Gemini response saved to: temp/debug/gemini_response.json")
            except:
                pass

            topics = self._parse_gpt_response(content)

            # Filter out any timestamps beyond video duration
            topics = [(ts, desc) for ts, desc in topics if ts <= video_duration]

            # Filter and sort
            topics = self._filter_short_topics(topics)
            topics.sort(key=lambda x: x[0])

            # Ensure intro at 0:00
            if not topics or topics[0][0] > 0:
                if self.qa_mode:
                    topics.insert(0, (0, "Presentation"))
                else:
                    topics.insert(0, (0, "Introduction"))

            logger.info(f"✓ Identified {len(topics)} chapters with Gemini")
            return topics

        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            import traceback
            logger.debug(f"Full error: {traceback.format_exc()}")
            logger.warning("Falling back to time-based chapters")
            return self._create_fallback_chapters(transcript)

    def _find_qa_start(
        self,
        intervals: List[Tuple[float, str]],
        video_title: str
    ) -> Optional[int]:
        """Find where Q&A section starts.

        Args:
            intervals: List of (timestamp, text) tuples
            video_title: Video title

        Returns:
            Timestamp in seconds where Q&A starts, or None
        """
        # Create condensed transcript for Q&A detection
        condensed = self._format_for_gpt(intervals[:30])  # First ~60 minutes

        prompt = f"""Analyze this video transcript to find where the Q&A session begins.

Video Title: {video_title}

The video has a presentation followed by a Q&A session. Find the timestamp where Q&A starts.
Look for phrases like:
- "questions"
- "Q&A"
- "let's take some questions"
- "open it up for questions"
- "anyone have questions"
- Speaker starts answering questions

Transcript (first portion):
{condensed}

Return JSON with the Q&A start time:
{{
  "qa_start_seconds": 1250,
  "confidence": "high",
  "indicator": "Speaker says 'let's open it up for questions'"
}}

If you cannot find clear Q&A indicators, return your best estimate or null for qa_start_seconds."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You identify where Q&A sections begin in video transcripts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            qa_start = data.get('qa_start_seconds')
            if qa_start:
                logger.info(f"Detected Q&A start: {data.get('indicator', 'unknown indicator')}")
                return int(qa_start)

        except Exception as e:
            logger.warning(f"Failed to detect Q&A start: {e}")

        return None

    def _create_presentation_prompt(
        self,
        presentation_transcript: str,
        video_title: str,
        qa_start_time: int
    ) -> str:
        """Create prompt for presentation analysis.

        Args:
            presentation_transcript: Transcript of presentation portion only
            video_title: Video title
            qa_start_time: When Q&A starts (end of presentation)

        Returns:
            Prompt string
        """
        prompt = f"""Analyze the PRESENTATION portion of this video and create timestamps for major sections.

Video: {video_title}
Presentation ends at: {qa_start_time} seconds (Q&A begins after)

TASK: Identify major sections and topic changes in the presentation.

INSTRUCTIONS:
1. Create timestamps for significant topic changes in the presentation
2. Use descriptive section titles that capture what's being discussed
3. Don't create too many timestamps - focus on major sections only
4. Timestamps must be in SECONDS (integers) based on [MM:SS] markers
5. Always start with timestamp 0

PRESENTATION TRANSCRIPT:
{presentation_transcript}

Return JSON with presentation chapters:
{{
  "chapters": [
    {{"timestamp": 0, "description": "Introduction and overview"}},
    {{"timestamp": 420, "description": "Q3/Q4 activities recap"}},
    {{"timestamp": 1200, "description": "Studio renovation and personal updates"}},
    {{"timestamp": 1680, "description": "Goals for 2026"}}
  ]
}}

CRITICAL:
- Focus on major sections, not every small detail
- Use the [MM:SS] markers to get exact timestamps
- Convert to seconds (e.g., [07:00] = 420 seconds)
- Return ONLY JSON"""

        return prompt

    def _create_qa_detail_prompt(
        self,
        qa_transcript: str,
        video_title: str,
        qa_start_time: int,
        video_duration: int
    ) -> str:
        """Create prompt for detailed Q&A analysis.

        Args:
            qa_transcript: Transcript of Q&A section only
            video_title: Video title
            qa_start_time: When Q&A starts in seconds
            video_duration: Total video duration in seconds

        Returns:
            Prompt string
        """
        prompt = f"""Analyze this Q&A SESSION transcript and create a timestamp for EVERY QUESTION.

Video: {video_title}
Q&A starts at: {qa_start_time} seconds
VIDEO ENDS AT: {video_duration} seconds ({video_duration//60}m {video_duration%60}s)

TASK: Identify EVERY question asked and answered in this Q&A session.

INSTRUCTIONS:
1. Create ONE timestamp for EACH question/answer pair
2. Identify the EXACT moment each new question begins - look for transition phrases like:
   - "Next question..."
   - "Another question..."
   - "Someone asks..."
   - Change in topic indicating new question
   - Speaker starting to address a new topic
3. Extract or infer the actual question being asked
4. Even if the question isn't read aloud, infer it from the answer
5. Format: "Q: [actual question]" - be specific about what's being asked
6. For each question, find the [MM:SS] marker in the transcript where it starts
7. Return that EXACT [MM:SS] marker in the "time_marker" field - DO NOT convert to seconds yourself
8. Include ALL questions - don't skip any

Q&A TRANSCRIPT (with 15-second precision):
{qa_transcript}

Return JSON with ALL questions:
{{
  "chapters": [
    {{"time_marker": "[40:15]", "description": "Q: Specific question about X"}},
    {{"time_marker": "[43:47]", "description": "Q: Specific question about Y"}},
    {{"time_marker": "[47:24]", "description": "Q: Specific question about Z"}}
  ]
}}

CRITICAL:
- Find EVERY question - there should be 10+ questions
- Return the LITERAL [MM:SS] marker from the transcript (e.g., "[40:15]")
- DO NOT convert to seconds - just copy the marker exactly as it appears
- Be specific in descriptions
- Return ONLY JSON"""

        return prompt

    def _create_gemini_qa_prompt(
        self,
        full_transcript: str,
        video_title: str,
        video_duration: int
    ) -> str:
        """Create prompt for Gemini Q&A analysis with full transcript.

        Args:
            full_transcript: Complete transcript with timestamps
            video_title: Video title
            video_duration: Total video duration in seconds

        Returns:
            Prompt string
        """
        prompt = f"""Analyze this complete video transcript for a PRESENTATION + Q&A SESSION.

Video: {video_title}
Duration: {video_duration} seconds ({video_duration//60}m {video_duration%60}s)

TASK: Create timestamps for the presentation AND detailed timestamps for EVERY question in the Q&A.

INSTRUCTIONS:
1. First, identify where the Q&A section begins (look for "questions", "Q&A", etc.)
2. For the PRESENTATION (before Q&A):
   - Create 2-5 timestamps for major sections only
   - Focus on significant topic changes
3. For the Q&A SECTION (after Q&A begins):
   - Create ONE timestamp for EVERY individual question
   - Look at the [MM:SS] markers in the transcript to find exactly when each question starts
   - Extract or infer what each question is about
   - Format as "Q: [actual question]"
4. Return the LITERAL [MM:SS] marker you see in the transcript
5. DO NOT create timestamps beyond {video_duration} seconds

COMPLETE TRANSCRIPT:
{full_transcript}

Return JSON:
{{
  "chapters": [
    {{"time_marker": "[00:00]", "description": "Introduction and overview"}},
    {{"time_marker": "[07:00]", "description": "Main presentation content"}},
    {{"time_marker": "[40:00]", "description": "Q&A begins"}},
    {{"time_marker": "[40:15]", "description": "Q: First question about X"}},
    {{"time_marker": "[43:47]", "description": "Q: Second question about Y"}},
    {{"time_marker": "[47:24]", "description": "Q: Third question about Z"}}
  ]
}}

CRITICAL:
- Find EVERY question in the Q&A section (should be 10+)
- Return the EXACT [MM:SS] marker from the transcript
- Keep presentation timestamps minimal (2-5)
- Be specific about what each question asks
- Return ONLY JSON"""

        return prompt

    def _create_gemini_standard_prompt(
        self,
        full_transcript: str,
        video_title: str
    ) -> str:
        """Create prompt for Gemini standard analysis with full transcript.

        Args:
            full_transcript: Complete transcript with timestamps
            video_title: Video title

        Returns:
            Prompt string
        """
        prompt = f"""Analyze this complete video transcript to create meaningful chapter timestamps.

Video: {video_title}

TASK: Identify major topic changes and create descriptive chapter timestamps.

INSTRUCTIONS:
1. Read through the ENTIRE transcript
2. Identify when the topic or focus significantly changes
3. Create descriptive chapter titles (5-10 words)
4. Return the LITERAL [MM:SS] marker you see in the transcript where each chapter starts
5. Only include significant topic changes (not every minor detail)

COMPLETE TRANSCRIPT:
{full_transcript}

Return JSON:
{{
  "chapters": [
    {{"time_marker": "[00:00]", "description": "Introduction and welcome"}},
    {{"time_marker": "[05:30]", "description": "Main topic discussion begins"}},
    {{"time_marker": "[15:45]", "description": "Demonstration and examples"}},
    {{"time_marker": "[25:10]", "description": "Summary and conclusions"}}
  ]
}}

CRITICAL:
- Return the EXACT [MM:SS] marker from the transcript
- Create descriptive, specific chapter titles
- Focus on major topic changes
- Return ONLY JSON"""

        return prompt

    def _format_for_gpt(self, intervals: List[Tuple[float, str]]) -> str:
        """Format transcript intervals for GPT analysis.

        Args:
            intervals: List of (timestamp, text) tuples

        Returns:
            Formatted string with timestamps
        """
        lines = []
        for timestamp, text in intervals:
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        return '\n'.join(lines)

    def _create_analysis_prompt(self, transcript: str, video_title: str = "") -> str:
        """Create the prompt for GPT analysis.

        Args:
            transcript: Formatted transcript with timestamps
            video_title: Optional video title

        Returns:
            Analysis prompt string
        """
        title_context = f"\nVideo Title: {video_title}" if video_title else ""

        if self.qa_mode:
            # Special prompt for presentation + Q&A format
            prompt = f"""You are analyzing a video transcript for a PRESENTATION + Q&A SESSION.{title_context}

VIDEO STRUCTURE:
This video has two parts:
1. PRESENTATION (first part) - The speaker presents information
2. Q&A SESSION (second part) - Questions are asked and answered

YOUR TASK:
Create detailed timestamps focusing on the Q&A section. Each question should get its own timestamp.

INSTRUCTIONS:
1. Identify where the Q&A section begins (look for phrases like "questions", "Q&A", "let's take questions", etc.)
2. For the PRESENTATION: Create just 1-2 timestamps maximum (e.g., "00:00 - Presentation" and maybe one for Q&A start)
3. For the Q&A SECTION: Create a timestamp for EACH question/answer
4. Extract the actual question being asked - either from what the speaker reads aloud OR infer it from the answer
5. Format question timestamps as: "Q: [actual question text]" or "Q&A: [topic of question]"
6. Timestamps must be in SECONDS (integers like 0, 125, 380) NOT time format
7. Be specific about what each question is about

TRANSCRIPT:
{transcript}

EXAMPLE OUTPUT FORMAT:
{{
  "chapters": [
    {{"timestamp": 0, "description": "Presentation"}},
    {{"timestamp": 1250, "description": "Q&A begins"}},
    {{"timestamp": 1280, "description": "Q: How do you handle project delays and timeline adjustments?"}},
    {{"timestamp": 1520, "description": "Q: What's the budget allocation for next quarter?"}},
    {{"timestamp": 1840, "description": "Q: Team expansion plans and hiring priorities"}},
    {{"timestamp": 2100, "description": "Q: How are remote work policies changing?"}}
  ]
}}

CRITICAL:
- Focus detail on Q&A section - that's what viewers want to navigate
- Make question descriptions specific and clear
- Use integer seconds for timestamps (NOT "20:00" format)
- Return ONLY valid JSON, no other text"""

        else:
            # Standard prompt for general videos
            prompt = f"""You are analyzing a video transcript to create meaningful YouTube chapter timestamps.{title_context}

CRITICAL INSTRUCTIONS:
1. READ THE ENTIRE TRANSCRIPT CAREFULLY - analyze the actual content, topics discussed, questions asked, etc.
2. Identify when the conversation shifts to new topics, questions, or discussion points
3. For Q&A videos: create chapters for each major question or topic discussed
4. For presentations: identify section changes, new concepts, demonstrations
5. Create descriptive chapter titles (5-10 words) that capture what's being discussed
6. Timestamps should be in SECONDS (integers only - not "20:00" format)
7. Only include topics lasting at least {self.min_topic_duration} seconds
8. Always start with timestamp 0 for the introduction/opening

TRANSCRIPT TO ANALYZE:
{transcript}

REQUIRED OUTPUT FORMAT (JSON only):
{{
  "chapters": [
    {{"timestamp": 0, "description": "Opening remarks and welcome"}},
    {{"timestamp": 125, "description": "Q&A: Discussion about project timelines"}},
    {{"timestamp": 380, "description": "Q&A: Budget allocation and priorities"}},
    {{"timestamp": 650, "description": "Team updates and announcements"}}
  ]
}}

IMPORTANT:
- Use integer seconds for timestamps (0, 125, 380) NOT time format (0:00, 2:05)
- Base descriptions on ACTUAL content from the transcript
- Return ONLY the JSON object, no other text"""

        return prompt

    def _parse_timestamp(self, timestamp_value) -> int:
        """Parse timestamp from various formats to seconds.

        Args:
            timestamp_value: Timestamp as int, string with seconds, or MM:SS/HH:MM:SS format

        Returns:
            Timestamp in seconds
        """
        if isinstance(timestamp_value, int):
            return timestamp_value

        if isinstance(timestamp_value, str):
            # Try parsing as MM:SS or HH:MM:SS
            if ':' in timestamp_value:
                parts = timestamp_value.split(':')
                if len(parts) == 2:  # MM:SS
                    minutes, seconds = map(int, parts)
                    return minutes * 60 + seconds
                elif len(parts) == 3:  # HH:MM:SS
                    hours, minutes, seconds = map(int, parts)
                    return hours * 3600 + minutes * 60 + seconds

            # Try parsing as plain number string
            return int(timestamp_value)

        return 0

    def _parse_gpt_response(self, response_content: str) -> List[Tuple[int, str]]:
        """Parse GPT response into topic list.

        Args:
            response_content: JSON response from GPT

        Returns:
            List of (timestamp, description) tuples
        """
        try:
            data = json.loads(response_content)
            chapters = data.get('chapters', [])

            topics = []
            for chapter in chapters:
                try:
                    # Check if GPT returned time_marker (new format) or timestamp (old format)
                    if 'time_marker' in chapter:
                        time_marker = chapter['time_marker'].strip()
                        # Parse [MM:SS] or [HH:MM:SS] marker
                        # Remove brackets if present
                        time_marker = time_marker.strip('[]')
                        timestamp = self._parse_timestamp(time_marker)
                    else:
                        # Fallback to old format
                        timestamp_value = chapter.get('timestamp', 0)
                        timestamp = self._parse_timestamp(timestamp_value)

                    description = chapter.get('description', '').strip()

                    if description:
                        topics.append((timestamp, description))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse chapter timestamp: {chapter}, error: {e}")
                    continue

            # Sort by timestamp
            topics.sort(key=lambda x: x[0])

            logger.info(f"Parsed {len(topics)} topics from GPT response")
            return topics

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GPT response as JSON: {e}")
            logger.debug(f"Response content: {response_content[:500]}")
            return []

    def _filter_short_topics(
        self,
        topics: List[Tuple[int, str]]
    ) -> List[Tuple[int, str]]:
        """Filter out topics that are too short.

        Args:
            topics: List of (timestamp, description) tuples

        Returns:
            Filtered list with short topics removed
        """
        if not topics:
            return topics

        filtered = []

        for i, (timestamp, description) in enumerate(topics):
            # Calculate duration until next topic
            if i < len(topics) - 1:
                next_timestamp = topics[i + 1][0]
                duration = next_timestamp - timestamp
            else:
                # Last topic - assume it's long enough
                duration = self.min_topic_duration + 1

            # Keep topics that meet minimum duration
            if duration >= self.min_topic_duration:
                filtered.append((timestamp, description))
            else:
                logger.debug(f"Filtered out short topic ({duration}s): {description}")

        return filtered

    def _create_fallback_chapters(self, transcript: Dict) -> List[Tuple[int, str]]:
        """Create simple time-based chapters as fallback.

        Args:
            transcript: Transcript dictionary

        Returns:
            List of (timestamp, description) tuples
        """
        # Estimate total duration from transcript
        if transcript.get('words'):
            total_duration = int(transcript['words'][-1]['end'])
        else:
            # Fallback if no word timestamps
            total_duration = 300  # 5 minutes default

        chapters = [(0, "Introduction")]

        # Create chapters every 5 minutes
        interval = 300  # 5 minutes
        current_time = interval

        chapter_num = 1
        while current_time < total_duration:
            chapters.append((current_time, f"Part {chapter_num}"))
            current_time += interval
            chapter_num += 1

        logger.info(f"Created {len(chapters)} fallback chapters")
        return chapters
