#!/usr/bin/env python3
"""
Viral Content Automation with ComfyUI (FREE!)

Uses ComfyUI running on your RTX 5060 16GB instead of paid APIs.
Save $3,000-6,000/month on content generation!

Workflow:
1. Discover trending content on social platforms
2. Analyze with 12labs
3. Generate content with ComfyUI (FREE!)
4. Post to all platforms
"""

import time
from pathlib import Path
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager
from phone_agent.social_automation import (
    SocialMediaAutomation,
    Platform,
    TrendingContent,
    GeneratedContent
)
from phone_agent.comfyui_integration import (
    ComfyUIClient,
    GenerationRequest,
    ContentType,
    test_comfyui_connection
)


def setup_comfyui_automation():
    """Setup automation with ComfyUI for content generation."""

    print("\n" + "="*70)
    print("🎨 Viral Content Automation with ComfyUI")
    print("   FREE content generation on your RTX 5060 16GB!")
    print("="*70 + "\n")

    # Test ComfyUI connection first
    print("🔍 Checking ComfyUI connection...")
    if not test_comfyui_connection("http://127.0.0.1:8188"):
        print("\n❌ ComfyUI not running!")
        print("\nTo start ComfyUI:")
        print("  cd ~/ComfyUI")
        print("  python main.py --listen 0.0.0.0 --port 8188")
        print("\nSee COMFYUI_SETUP.md for installation")
        return

    # Setup ComfyUI client
    comfy_client = ComfyUIClient(
        server_url="http://127.0.0.1:8188",
        output_dir="./generated_content"
    )

    # Setup phone manager
    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",  # Local model for phone control
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=False)

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    print("✅ Phone Pool Manager initialized")

    # Create custom automation class with ComfyUI
    automation = ComfyUIBasedAutomation(
        phone_manager=phone_manager,
        comfyui_client=comfy_client,
        labs_12_api_key="your-12labs-key"  # Optional
    )

    return automation


class ComfyUIBasedAutomation(SocialMediaAutomation):
    """
    Extended social automation that uses ComfyUI for content generation.
    """

    def __init__(
        self,
        phone_manager,
        comfyui_client: ComfyUIClient,
        labs_12_api_key=None
    ):
        super().__init__(phone_manager, labs_12_api_key, None)
        self.comfyui = comfyui_client

    def generate_with_comfyui(
        self,
        analysis: dict,
        original_content: TrendingContent,
        workflow_path: str = None
    ) -> GeneratedContent:
        """
        Generate content using ComfyUI instead of Veo3.

        Args:
            analysis: 12labs analysis (or mock analysis)
            original_content: Original trending content
            workflow_path: Path to ComfyUI workflow JSON

        Returns:
            GeneratedContent ready for posting
        """
        print(f"🎨 Generating content with ComfyUI (FREE!)...")

        # Build prompt from analysis
        prompt = self._create_comfyui_prompt(analysis, original_content)

        # Determine format based on platform
        width, height = self._get_platform_dimensions(original_content.platform)

        # Create generation request
        request = GenerationRequest(
            prompt=prompt,
            negative_prompt="low quality, blurry, watermark, ugly, deformed",
            width=width,
            height=height,
            num_frames=48 if original_content.platform in [
                Platform.TIKTOK,
                Platform.INSTAGRAM_REELS,
                Platform.YOUTUBE_SHORTS
            ] else 1,
            content_type=ContentType.VIDEO if original_content.platform in [
                Platform.TIKTOK,
                Platform.INSTAGRAM_REELS,
                Platform.YOUTUBE_SHORTS
            ] else ContentType.IMAGE,
            steps=25,
            cfg_scale=7.5,
            seed=-1  # Random
        )

        # Generate with ComfyUI
        generated = self.comfyui.generate(request, workflow_path)

        # Create GeneratedContent object
        return GeneratedContent(
            video_path=generated.file_path,
            caption=self._generate_caption(analysis, original_content),
            hashtags=self._generate_hashtags(analysis, original_content),
            platforms=[original_content.platform],
            metadata={
                "original_url": original_content.url,
                "generation_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "generator": "ComfyUI",
                "prompt": prompt
            }
        )

    def _create_comfyui_prompt(
        self,
        analysis: dict,
        content: TrendingContent
    ) -> str:
        """Create ComfyUI prompt from trend analysis."""
        mood = analysis.get("mood", "energetic")
        style = analysis.get("visual_style", "colorful")
        actions = ", ".join(analysis.get("detected_actions", ["dynamic motion"]))

        platform_styles = {
            Platform.TIKTOK: "viral tiktok style, trending, fast-paced",
            Platform.INSTAGRAM_REELS: "aesthetic instagram reels, polished, beautiful",
            Platform.YOUTUBE_SHORTS: "professional youtube shorts, high quality",
            Platform.TWITTER: "engaging twitter content, eye-catching",
            Platform.FACEBOOK: "shareable facebook content, relatable"
        }

        platform_style = platform_styles.get(
            content.platform,
            "viral social media content"
        )

        prompt = (
            f"{platform_style}, "
            f"{mood} mood, {style} aesthetic, "
            f"featuring {actions}, "
            f"professional quality, cinematic lighting, "
            f"trending, viral worthy, "
            f"vertical 9:16 format"
        )

        return prompt

    def _get_platform_dimensions(self, platform: Platform) -> tuple:
        """Get dimensions for platform."""
        vertical_platforms = [
            Platform.TIKTOK,
            Platform.INSTAGRAM_REELS,
            Platform.YOUTUBE_SHORTS
        ]

        if platform in vertical_platforms:
            return (1080, 1920)  # Vertical
        else:
            return (1080, 1080)  # Square

    def run_free_pipeline(
        self,
        discovery_limit: int = 10,
        content_to_generate: int = 5,
        workflow_path: str = None
    ):
        """
        Run complete pipeline with FREE ComfyUI generation.

        Args:
            discovery_limit: Number of trending items per platform
            content_to_generate: Number of videos to generate
            workflow_path: Optional custom ComfyUI workflow
        """
        print("\n" + "="*70)
        print("🚀 Starting FREE Viral Content Pipeline (ComfyUI)")
        print("="*70 + "\n")

        # Step 1: Discover trending
        print("Step 1: Discovering trending content...")
        all_trending = []

        for platform, phones in self.platform_phones.items():
            if phones:
                phone = phones[0]
                trending = self.discover_trending(platform, phone, discovery_limit)
                all_trending.extend(trending)

        print(f"✅ Found {len(all_trending)} trending items\n")

        # Step 2: Analyze (mock if no 12labs key)
        print("Step 2: Analyzing content...")
        analyzed = []

        top_content = sorted(
            all_trending,
            key=lambda x: x.engagement,
            reverse=True
        )[:content_to_generate]

        for content in top_content:
            if self.labs_12_api_key:
                analysis = self.analyze_with_12labs(content)
            else:
                # Mock analysis if no 12labs
                analysis = {
                    "mood": "energetic",
                    "visual_style": "colorful",
                    "detected_actions": ["dynamic", "engaging"],
                    "suggested_recreations": ["viral style recreation"]
                }

            analyzed.append((content, analysis))

        print(f"✅ Analyzed {len(analyzed)} pieces\n")

        # Step 3: Generate with ComfyUI (FREE!)
        print("Step 3: Generating content with ComfyUI (FREE!)...")
        print("   This may take a few minutes per video on RTX 5060")
        generated = []

        for i, (content, analysis) in enumerate(analyzed, 1):
            print(f"\n   Generating {i}/{len(analyzed)}...")
            new_content = self.generate_with_comfyui(
                analysis,
                content,
                workflow_path
            )
            generated.append(new_content)

        print(f"\n✅ Generated {len(generated)} pieces (FREE!)\n")

        # Step 4: Post to platforms
        print("Step 4: Posting to platforms...")

        for content in generated:
            for platform in content.platforms:
                if platform in self.platform_phones and self.platform_phones[platform]:
                    phone = self.platform_phones[platform][0]
                    self.post_content(content, platform, phone)

        print("\n" + "="*70)
        print("✅ FREE Viral Content Pipeline Complete!")
        print(f"   Generated {len(generated)} videos at $0 cost!")
        print(f"   (Would have cost ${len(generated) * 10} with Veo3 API)")
        print("="*70 + "\n")


def main():
    """Run viral automation with ComfyUI."""

    automation = setup_comfyui_automation()
    if not automation:
        return

    # Assign phones
    automation.assign_phones({
        Platform.TIKTOK: ["phone_01", "phone_02", "phone_03"],
        Platform.INSTAGRAM_REELS: ["phone_06", "phone_07"],
        Platform.YOUTUBE_SHORTS: ["phone_10", "phone_11"],
        Platform.TWITTER: ["phone_14"],
        Platform.FACEBOOK: ["phone_17"]
    })

    # Run FREE pipeline
    automation.run_free_pipeline(
        discovery_limit=5,
        content_to_generate=3
    )


def generate_batch_images():
    """Generate batch of images for testing."""

    print("\n🎨 Batch Image Generation Test\n")

    # Test ComfyUI
    if not test_comfyui_connection():
        return

    client = ComfyUIClient("http://127.0.0.1:8188")

    # Generate 5 viral-style images
    prompts = [
        "viral tiktok aesthetic, colorful, trending",
        "instagram reels style, aesthetic, beautiful",
        "youtube shorts thumbnail, eye-catching, professional",
        "twitter viral content, engaging, shareable",
        "facebook viral post, relatable, emotional"
    ]

    requests = [
        GenerationRequest(
            prompt=prompt,
            width=1080,
            height=1920,
            content_type=ContentType.IMAGE,
            seed=i
        )
        for i, prompt in enumerate(prompts)
    ]

    results = client.batch_generate(requests)

    print(f"\n✅ Generated {len(results)} images!")
    for result in results:
        print(f"   - {result.file_path}")


def test_single_generation():
    """Test single content generation."""

    print("\n🧪 Testing Single Generation\n")

    if not test_comfyui_connection():
        return

    client = ComfyUIClient("http://127.0.0.1:8188")

    # Generate one viral image
    request = GenerationRequest(
        prompt="amazing viral tiktok content, colorful, energetic, trending",
        negative_prompt="ugly, blurry, low quality",
        width=1080,
        height=1920,
        content_type=ContentType.IMAGE,
        steps=25,
        cfg_scale=7.5
    )

    result = client.generate(request)

    print(f"\n✅ Generated: {result.file_path}")
    print(f"   Prompt: {result.prompt}")
    print(f"   Type: {result.content_type.value}")


if __name__ == "__main__":
    print("\n🎨 Viral Automation with ComfyUI (FREE!)\n")
    print("Choose mode:")
    print("1. Full automation pipeline")
    print("2. Batch image generation test")
    print("3. Single generation test")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == "1":
        main()
    elif choice == "2":
        generate_batch_images()
    elif choice == "3":
        test_single_generation()
    else:
        print("Invalid choice")
