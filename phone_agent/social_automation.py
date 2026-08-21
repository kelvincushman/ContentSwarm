"""
Social Media Automation Framework for Viral Content Pipeline.

Workflow:
1. Monitor trending topics across platforms
2. Analyze content with 12labs
3. Create new content with Veo3
4. Post to multiple platforms
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from phone_agent.phone_pool import PhonePoolManager


class Platform(Enum):
    """Supported social media platforms."""
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    TWITTER = "twitter"
    FACEBOOK = "facebook"


@dataclass
class TrendingContent:
    """Information about trending content."""
    platform: Platform
    url: str
    title: str
    views: int
    engagement: float
    hashtags: List[str]
    discovered_at: str


@dataclass
class GeneratedContent:
    """Generated content ready for posting."""
    video_path: str
    caption: str
    hashtags: List[str]
    platforms: List[Platform]
    metadata: Dict


class SocialMediaAutomation:
    """
    Automate viral content discovery, creation, and distribution.

    Example:
        >>> automation = SocialMediaAutomation(phone_manager)
        >>> automation.assign_phones({
        ...     Platform.TIKTOK: ["phone_01", "phone_02", "phone_03"],
        ...     Platform.INSTAGRAM_REELS: ["phone_04", "phone_05"],
        ... })
        >>> automation.start_monitoring()
    """

    def __init__(
        self,
        phone_manager: PhonePoolManager,
        labs_12_api_key: Optional[str] = None,
        veo3_api_key: Optional[str] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initialize social media automation.

        Args:
            phone_manager: PhonePoolManager instance
            labs_12_api_key: API key for 12labs content analysis
            veo3_api_key: API key for Veo3 video generation
            event_callback: Optional callback for pipeline stage events
        """
        self.phone_manager = phone_manager
        self.labs_12_api_key = labs_12_api_key
        self.veo3_api_key = veo3_api_key
        self._event_callback = event_callback

        # Phone assignments by platform
        self.platform_phones: Dict[Platform, List[str]] = {}

        # Trending content queue
        self.trending_queue: List[TrendingContent] = []

        # Generated content queue
        self.content_queue: List[GeneratedContent] = []

        # Pipeline state
        self._pipeline_status: Dict[str, Any] = {
            "stage": "idle",
            "progress": 0,
            "total_discovered": 0,
            "total_analyzed": 0,
            "total_generated": 0,
            "total_posted": 0,
            "last_run": None
        }

    def _emit_event(self, event: Dict[str, Any]) -> None:
        """Emit a pipeline event."""
        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception:
                pass

    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback for pipeline events."""
        self._event_callback = callback

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get the current pipeline status."""
        return {
            **self._pipeline_status,
            "trending_queue_size": len(self.trending_queue),
            "content_queue_size": len(self.content_queue),
            "platform_assignments": {
                p.value: phones for p, phones in self.platform_phones.items()
            }
        }

    def get_trending_queue(self) -> List[Dict[str, Any]]:
        """Get trending content queue as serializable dicts."""
        return [
            {
                "platform": t.platform.value,
                "url": t.url,
                "title": t.title,
                "views": t.views,
                "engagement": t.engagement,
                "hashtags": t.hashtags,
                "discovered_at": t.discovered_at
            }
            for t in self.trending_queue
        ]

    def get_content_queue(self) -> List[Dict[str, Any]]:
        """Get generated content queue as serializable dicts."""
        return [
            {
                "video_path": c.video_path,
                "caption": c.caption,
                "hashtags": c.hashtags,
                "platforms": [p.value for p in c.platforms],
                "metadata": c.metadata
            }
            for c in self.content_queue
        ]

    def assign_phones(self, assignments: Dict[Platform, List[str]]) -> None:
        """
        Assign phones to platforms.

        Args:
            assignments: Dict mapping platforms to phone lists

        Example:
            >>> automation.assign_phones({
            ...     Platform.TIKTOK: ["phone_01", "phone_02", "phone_03"],
            ...     Platform.INSTAGRAM_REELS: ["phone_04", "phone_05"],
            ...     Platform.YOUTUBE_SHORTS: ["phone_06", "phone_07"],
            ...     Platform.TWITTER: ["phone_08"],
            ...     Platform.FACEBOOK: ["phone_09", "phone_10"]
            ... })
        """
        self.platform_phones = assignments

        print("\n📱 Phone Assignments:")
        print("=" * 60)
        for platform, phones in assignments.items():
            print(f"{platform.value:20} → {', '.join(phones)}")
        print("=" * 60 + "\n")

    def discover_trending(
        self,
        platform: Platform,
        phone_name: str,
        limit: int = 10
    ) -> List[TrendingContent]:
        """
        Discover trending content on a platform.

        Args:
            platform: Platform to monitor
            phone_name: Phone to use for discovery
            limit: Number of trending items to find

        Returns:
            List of TrendingContent objects
        """
        print(f"🔍 Discovering trending on {platform.value} using {phone_name}...")

        # Platform-specific discovery workflows
        workflows = {
            Platform.TIKTOK: self._discover_tiktok,
            Platform.INSTAGRAM_REELS: self._discover_instagram,
            Platform.YOUTUBE_SHORTS: self._discover_youtube_shorts,
            Platform.TWITTER: self._discover_twitter,
            Platform.FACEBOOK: self._discover_facebook
        }

        if platform in workflows:
            return workflows[platform](phone_name, limit)
        else:
            raise ValueError(f"Platform {platform} not supported")

    def _discover_tiktok(self, phone: str, limit: int) -> List[TrendingContent]:
        """Discover trending TikTok content."""
        # Open TikTok app
        self.phone_manager.quick_run(phone, "Launch TikTok")
        time.sleep(2)

        # Navigate to trending/discover
        self.phone_manager.quick_run(phone, "Tap on Discover tab")
        time.sleep(1)

        trending = []
        for i in range(limit):
            # Swipe through trending
            self.phone_manager.quick_run(phone, f"Swipe up to see next trending video")
            time.sleep(1)

            # Here you would capture screen data and parse
            # For now, placeholder
            trending.append(TrendingContent(
                platform=Platform.TIKTOK,
                url=f"https://tiktok.com/trending/{i}",
                title=f"Trending TikTok {i}",
                views=1000000,
                engagement=0.15,
                hashtags=["trending", "viral"],
                discovered_at=time.strftime("%Y-%m-%d %H:%M:%S")
            ))

        return trending

    def _discover_instagram(self, phone: str, limit: int) -> List[TrendingContent]:
        """Discover trending Instagram Reels."""
        self.phone_manager.quick_run(phone, "Launch Instagram")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on Reels icon")
        time.sleep(1)

        trending = []
        for i in range(limit):
            self.phone_manager.quick_run(phone, "Swipe up for next reel")
            time.sleep(1)

            trending.append(TrendingContent(
                platform=Platform.INSTAGRAM_REELS,
                url=f"https://instagram.com/reel/{i}",
                title=f"Trending Reel {i}",
                views=500000,
                engagement=0.12,
                hashtags=["reels", "viral"],
                discovered_at=time.strftime("%Y-%m-%d %H:%M:%S")
            ))

        return trending

    def _discover_youtube_shorts(self, phone: str, limit: int) -> List[TrendingContent]:
        """Discover trending YouTube Shorts."""
        self.phone_manager.quick_run(phone, "Launch YouTube")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on Shorts tab")
        time.sleep(1)

        trending = []
        for i in range(limit):
            self.phone_manager.quick_run(phone, "Swipe up for next short")
            time.sleep(1)

            trending.append(TrendingContent(
                platform=Platform.YOUTUBE_SHORTS,
                url=f"https://youtube.com/shorts/{i}",
                title=f"Trending Short {i}",
                views=750000,
                engagement=0.18,
                hashtags=["shorts", "trending"],
                discovered_at=time.strftime("%Y-%m-%d %H:%M:%S")
            ))

        return trending

    def _discover_twitter(self, phone: str, limit: int) -> List[TrendingContent]:
        """Discover trending Twitter/X topics."""
        self.phone_manager.quick_run(phone, "Launch X")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on Trending tab")
        time.sleep(1)

        trending = []
        for i in range(limit):
            trending.append(TrendingContent(
                platform=Platform.TWITTER,
                url=f"https://twitter.com/trending/{i}",
                title=f"Trending Topic {i}",
                views=2000000,
                engagement=0.20,
                hashtags=["trending"],
                discovered_at=time.strftime("%Y-%m-%d %H:%M:%S")
            ))

        return trending

    def _discover_facebook(self, phone: str, limit: int) -> List[TrendingContent]:
        """Discover trending Facebook content."""
        self.phone_manager.quick_run(phone, "Launch Facebook")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on Watch tab")
        time.sleep(1)

        trending = []
        for i in range(limit):
            trending.append(TrendingContent(
                platform=Platform.FACEBOOK,
                url=f"https://facebook.com/watch/{i}",
                title=f"Trending Video {i}",
                views=300000,
                engagement=0.10,
                hashtags=["viral"],
                discovered_at=time.strftime("%Y-%m-%d %H:%M:%S")
            ))

        return trending

    def analyze_with_12labs(self, content: TrendingContent) -> Dict:
        """
        Analyze trending content with 12labs API.

        Args:
            content: TrendingContent to analyze

        Returns:
            Analysis results from 12labs
        """
        print(f"🔬 Analyzing content with 12labs: {content.title}")

        # Placeholder for 12labs API integration
        # In production, you would call 12labs API here
        analysis = {
            "video_url": content.url,
            "detected_objects": ["person", "landscape", "text"],
            "detected_actions": ["dancing", "talking", "transition"],
            "mood": "energetic",
            "visual_style": "colorful",
            "audio_features": {
                "music_type": "upbeat",
                "has_voiceover": True,
                "sound_effects": ["whoosh", "pop"]
            },
            "key_moments": [
                {"timestamp": 0, "description": "Hook"},
                {"timestamp": 3, "description": "Main content"},
                {"timestamp": 12, "description": "Call to action"}
            ],
            "suggested_recreations": [
                "Similar visual style with different subject",
                "Same structure but different niche",
                "Remix with trending audio"
            ]
        }

        return analysis

    def generate_with_veo3(
        self,
        analysis: Dict,
        original_content: TrendingContent
    ) -> GeneratedContent:
        """
        Generate new content with Veo3 based on analysis.

        Args:
            analysis: 12labs analysis results
            original_content: Original trending content

        Returns:
            GeneratedContent ready for posting
        """
        print(f"🎬 Generating new content with Veo3...")

        # Placeholder for Veo3 API integration
        # In production, you would call Veo3 API here

        # Create prompt based on analysis
        prompt = self._create_veo3_prompt(analysis, original_content)

        print(f"   Prompt: {prompt}")

        # Simulated generated content
        generated = GeneratedContent(
            video_path="/path/to/generated_video.mp4",
            caption=self._generate_caption(analysis, original_content),
            hashtags=self._generate_hashtags(analysis, original_content),
            platforms=[Platform.TIKTOK, Platform.INSTAGRAM_REELS, Platform.YOUTUBE_SHORTS],
            metadata={
                "original_url": original_content.url,
                "generation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "veo3_prompt": prompt
            }
        )

        return generated

    def _create_veo3_prompt(self, analysis: Dict, content: TrendingContent) -> str:
        """Create Veo3 generation prompt from analysis."""
        mood = analysis.get("mood", "energetic")
        style = analysis.get("visual_style", "colorful")
        actions = ", ".join(analysis.get("detected_actions", []))

        prompt = (
            f"Create a {mood} {style} short video featuring {actions}. "
            f"Style should match popular content on {content.platform.value}. "
            f"Duration: 15-60 seconds. High quality, professional editing."
        )

        return prompt

    def _generate_caption(self, analysis: Dict, content: TrendingContent) -> str:
        """Generate engaging caption for the content."""
        # AI-generated caption based on analysis
        return f"🔥 Trending now! Check out this amazing content! #{content.platform.value}"

    def _generate_hashtags(self, analysis: Dict, content: TrendingContent) -> List[str]:
        """Generate relevant hashtags."""
        base_hashtags = ["viral", "trending", "fyp", "foryou"]
        content_hashtags = content.hashtags
        return list(set(base_hashtags + content_hashtags))[:10]

    def post_content(
        self,
        content: GeneratedContent,
        platform: Platform,
        phone_name: str
    ) -> bool:
        """
        Post generated content to a platform.

        Args:
            content: GeneratedContent to post
            platform: Platform to post to
            phone_name: Phone to use for posting

        Returns:
            True if posted successfully
        """
        print(f"📤 Posting to {platform.value} using {phone_name}...")

        # Platform-specific posting workflows
        workflows = {
            Platform.TIKTOK: self._post_to_tiktok,
            Platform.INSTAGRAM_REELS: self._post_to_instagram,
            Platform.YOUTUBE_SHORTS: self._post_to_youtube,
            Platform.TWITTER: self._post_to_twitter,
            Platform.FACEBOOK: self._post_to_facebook
        }

        if platform in workflows:
            return workflows[platform](content, phone_name)
        else:
            raise ValueError(f"Platform {platform} not supported for posting")

    def _post_to_tiktok(self, content: GeneratedContent, phone: str) -> bool:
        """Post video to TikTok."""
        self.phone_manager.quick_run(phone, "Launch TikTok")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on plus button to create")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Select upload video option")
        time.sleep(1)

        # Here you would transfer the video file and select it
        # For now, placeholder workflow

        self.phone_manager.quick_run(phone, f"Type caption: {content.caption}")
        time.sleep(1)

        hashtags_str = " ".join(f"#{tag}" for tag in content.hashtags)
        self.phone_manager.quick_run(phone, f"Add hashtags: {hashtags_str}")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Tap Post button")
        time.sleep(2)

        print(f"✅ Posted to TikTok!")
        return True

    def _post_to_instagram(self, content: GeneratedContent, phone: str) -> bool:
        """Post Reel to Instagram."""
        self.phone_manager.quick_run(phone, "Launch Instagram")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on plus button")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Select Reel")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Select video from gallery")
        time.sleep(2)

        self.phone_manager.quick_run(phone, f"Write caption: {content.caption}")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Tap Share to post")
        time.sleep(2)

        print(f"✅ Posted to Instagram Reels!")
        return True

    def _post_to_youtube(self, content: GeneratedContent, phone: str) -> bool:
        """Post Short to YouTube."""
        self.phone_manager.quick_run(phone, "Launch YouTube")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap on plus button")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Select Create a Short")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Upload video")
        time.sleep(2)

        self.phone_manager.quick_run(phone, f"Add title: {content.caption}")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Tap Upload")
        time.sleep(2)

        print(f"✅ Posted to YouTube Shorts!")
        return True

    def _post_to_twitter(self, content: GeneratedContent, phone: str) -> bool:
        """Post to Twitter/X."""
        self.phone_manager.quick_run(phone, "Launch X")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap compose tweet button")
        time.sleep(1)

        self.phone_manager.quick_run(phone, f"Type: {content.caption}")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Attach video")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap Post")
        time.sleep(2)

        print(f"✅ Posted to X!")
        return True

    def _post_to_facebook(self, content: GeneratedContent, phone: str) -> bool:
        """Post to Facebook."""
        self.phone_manager.quick_run(phone, "Launch Facebook")
        time.sleep(2)

        self.phone_manager.quick_run(phone, "Tap What's on your mind")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Select Photo/Video")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Choose video")
        time.sleep(2)

        self.phone_manager.quick_run(phone, f"Write caption: {content.caption}")
        time.sleep(1)

        self.phone_manager.quick_run(phone, "Tap Post")
        time.sleep(2)

        print(f"✅ Posted to Facebook!")
        return True

    def run_viral_pipeline(
        self,
        discovery_limit: int = 10,
        content_to_generate: int = 3
    ) -> Dict[str, int]:
        """Run the complete viral content pipeline.

        Wraps the pipeline so a failure never leaves the status stuck on a
        running stage: on error the stage becomes 'error' and the exception
        propagates to the caller.
        """
        try:
            return self._run_viral_pipeline(discovery_limit, content_to_generate)
        except Exception:
            self._pipeline_status["stage"] = "error"
            self._emit_event({"event": "pipeline_error", "timestamp": time.time()})
            raise

    def _run_viral_pipeline(
        self,
        discovery_limit: int = 10,
        content_to_generate: int = 3
    ) -> Dict[str, int]:
        """
        Run complete viral content pipeline.

        Workflow:
        1. Discover trending across all platforms
        2. Analyze top content with 12labs
        3. Generate new content with Veo3
        4. Post to all platforms

        Args:
            discovery_limit: Number of trending items per platform
            content_to_generate: Number of new content pieces to create

        Returns:
            Dict with counts: discovered, analyzed, generated, posted
        """
        print("\n" + "="*70)
        print("🚀 Starting Viral Content Pipeline")
        print("="*70 + "\n")

        self._pipeline_status["stage"] = "discovery"
        self._pipeline_status["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._emit_event({"event": "pipeline_started", "timestamp": time.time()})

        # Step 1: Discover trending across platforms
        print("Step 1: Discovering trending content...")
        self._emit_event({"event": "pipeline_stage", "stage": "discovery", "timestamp": time.time()})
        all_trending = []

        for platform, phones in self.platform_phones.items():
            if phones:
                phone = phones[0]  # Use first assigned phone
                trending = self.discover_trending(platform, phone, discovery_limit)
                all_trending.extend(trending)

        self.trending_queue.extend(all_trending)
        self._pipeline_status["total_discovered"] += len(all_trending)
        self._pipeline_status["progress"] = 25
        print(f"✅ Found {len(all_trending)} trending items\n")
        self._emit_event({"event": "discovery_completed", "count": len(all_trending), "timestamp": time.time()})

        # Step 2: Analyze top content
        print("Step 2: Analyzing top content with 12labs...")
        self._pipeline_status["stage"] = "analysis"
        self._emit_event({"event": "pipeline_stage", "stage": "analysis", "timestamp": time.time()})
        analyzed = []

        # Sort by engagement and take top N
        top_content = sorted(all_trending, key=lambda x: x.engagement, reverse=True)[:content_to_generate]

        for content in top_content:
            analysis = self.analyze_with_12labs(content)
            analyzed.append((content, analysis))

        self._pipeline_status["total_analyzed"] += len(analyzed)
        self._pipeline_status["progress"] = 50
        print(f"✅ Analyzed {len(analyzed)} pieces\n")
        self._emit_event({"event": "analysis_completed", "count": len(analyzed), "timestamp": time.time()})

        # Step 3: Generate new content
        print("Step 3: Generating new content with Veo3...")
        self._pipeline_status["stage"] = "generation"
        self._emit_event({"event": "pipeline_stage", "stage": "generation", "timestamp": time.time()})
        generated = []

        for content, analysis in analyzed:
            new_content = self.generate_with_veo3(analysis, content)
            generated.append(new_content)

        self.content_queue.extend(generated)
        self._pipeline_status["total_generated"] += len(generated)
        self._pipeline_status["progress"] = 75
        print(f"✅ Generated {len(generated)} new pieces\n")
        self._emit_event({"event": "generation_completed", "count": len(generated), "timestamp": time.time()})

        # Step 4: Post to all platforms
        print("Step 4: Posting to platforms...")
        self._pipeline_status["stage"] = "posting"
        self._emit_event({"event": "pipeline_stage", "stage": "posting", "timestamp": time.time()})
        posted_count = 0

        for content in generated:
            for platform in content.platforms:
                if platform in self.platform_phones and self.platform_phones[platform]:
                    phone = self.platform_phones[platform][0]
                    self.post_content(content, platform, phone)
                    posted_count += 1

        self._pipeline_status["total_posted"] += posted_count
        self._pipeline_status["stage"] = "idle"
        self._pipeline_status["progress"] = 100

        print("\n" + "="*70)
        print("✅ Viral Content Pipeline Complete!")
        print("="*70 + "\n")

        result = {
            "discovered": len(all_trending),
            "analyzed": len(analyzed),
            "generated": len(generated),
            "posted": posted_count
        }
        self._emit_event({"event": "pipeline_completed", "result": result, "timestamp": time.time()})
        return result
