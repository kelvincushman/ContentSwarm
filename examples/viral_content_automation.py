#!/usr/bin/env python3
"""
Viral Content Automation - Complete Pipeline Example

This script demonstrates how to use 20 phones to:
1. Monitor trending content across social platforms
2. Analyze with 12labs
3. Generate new content with Veo3
4. Post to multiple platforms

Setup your 20 phones like this:
- Phones 1-5: TikTok discovery & posting
- Phones 6-9: Instagram Reels discovery & posting
- Phones 10-13: YouTube Shorts discovery & posting
- Phones 14-16: Twitter/X discovery & posting
- Phones 17-20: Facebook discovery & posting
"""

import time
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager
from phone_agent.social_automation import (
    SocialMediaAutomation,
    Platform
)


def setup_phone_assignments():
    """Define which phones handle which platforms."""
    return {
        # TikTok: 5 phones for scale
        Platform.TIKTOK: [
            "phone_01", "phone_02", "phone_03", "phone_04", "phone_05"
        ],

        # Instagram Reels: 4 phones
        Platform.INSTAGRAM_REELS: [
            "phone_06", "phone_07", "phone_08", "phone_09"
        ],

        # YouTube Shorts: 4 phones
        Platform.YOUTUBE_SHORTS: [
            "phone_10", "phone_11", "phone_12", "phone_13"
        ],

        # Twitter/X: 3 phones
        Platform.TWITTER: [
            "phone_14", "phone_15", "phone_16"
        ],

        # Facebook: 4 phones
        Platform.FACEBOOK: [
            "phone_17", "phone_18", "phone_19", "phone_20"
        ]
    }


def main():
    """Run viral content automation pipeline."""
    print("\n" + "="*70)
    print("🚀 Viral Content Automation System")
    print("="*70 + "\n")

    # Step 1: Setup Phone Pool Manager
    print("📱 Step 1: Initializing Phone Pool Manager...")

    model_config = ModelConfig(
        base_url="https://api.novita.ai/openai",  # Using API for 20 phones
        model_name="zai-org/autoglm-phone-9b-multilingual",
        api_key="your-novita-api-key"  # Replace with your key
    )

    agent_config = AgentConfig(
        lang="en",
        verbose=False  # Set to True for debugging
    )

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    print("✅ Phone Pool Manager initialized")
    phone_manager.print_status()

    # Step 2: Setup Social Media Automation
    print("\n🤖 Step 2: Initializing Social Media Automation...")

    automation = SocialMediaAutomation(
        phone_manager=phone_manager,
        labs_12_api_key="your-12labs-api-key",  # Replace with your key
        veo3_api_key="your-veo3-api-key"  # Replace with your key
    )

    # Assign phones to platforms
    assignments = setup_phone_assignments()
    automation.assign_phones(assignments)

    print("✅ Social Media Automation ready\n")

    # Step 3: Run Viral Content Pipeline
    print("🎬 Step 3: Running Viral Content Pipeline...")
    print("-" * 70)

    automation.run_viral_pipeline(
        discovery_limit=10,  # Find 10 trending items per platform
        content_to_generate=5  # Create 5 new viral videos
    )

    print("\n" + "="*70)
    print("✅ Automation Complete!")
    print("="*70 + "\n")


def discover_only_mode():
    """Just discover trending content without posting."""
    print("\n🔍 Discovery Only Mode\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=True)

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    automation = SocialMediaAutomation(phone_manager)
    automation.assign_phones(setup_phone_assignments())

    # Discover trending on each platform
    platforms = [
        (Platform.TIKTOK, "phone_01"),
        (Platform.INSTAGRAM_REELS, "phone_06"),
        (Platform.YOUTUBE_SHORTS, "phone_10"),
        (Platform.TWITTER, "phone_14"),
        (Platform.FACEBOOK, "phone_17")
    ]

    all_trending = []
    for platform, phone in platforms:
        trending = automation.discover_trending(platform, phone, limit=5)
        all_trending.extend(trending)

        print(f"\n📊 {platform.value} Trending:")
        for item in trending:
            print(f"  - {item.title} ({item.views:,} views)")

    print(f"\n✅ Discovered {len(all_trending)} trending items total")


def post_only_mode():
    """Post pre-generated content to all platforms."""
    print("\n📤 Post Only Mode\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=True)

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    automation = SocialMediaAutomation(phone_manager)
    automation.assign_phones(setup_phone_assignments())

    # Simulate generated content
    from phone_agent.social_automation import GeneratedContent

    content = GeneratedContent(
        video_path="/path/to/viral_video.mp4",
        caption="🔥 Amazing new trend! #viral #fyp",
        hashtags=["viral", "fyp", "trending", "amazing"],
        platforms=[
            Platform.TIKTOK,
            Platform.INSTAGRAM_REELS,
            Platform.YOUTUBE_SHORTS
        ],
        metadata={"source": "veo3_generated"}
    )

    # Post to all platforms
    platforms_to_post = [
        (Platform.TIKTOK, "phone_01"),
        (Platform.INSTAGRAM_REELS, "phone_06"),
        (Platform.YOUTUBE_SHORTS, "phone_10")
    ]

    for platform, phone in platforms_to_post:
        automation.post_content(content, platform, phone)

    print("\n✅ Posted to all platforms!")


def continuous_monitoring():
    """
    Continuous monitoring mode - run forever.

    This mode:
    1. Monitors trending content every hour
    2. Analyzes top content
    3. Generates new content
    4. Posts to all platforms
    5. Repeats
    """
    print("\n♾️  Continuous Monitoring Mode\n")

    model_config = ModelConfig(
        base_url="https://api.novita.ai/openai",
        model_name="zai-org/autoglm-phone-9b-multilingual",
        api_key="your-novita-api-key"
    )

    agent_config = AgentConfig(lang="en", verbose=False)

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    automation = SocialMediaAutomation(
        phone_manager=phone_manager,
        labs_12_api_key="your-12labs-api-key",
        veo3_api_key="your-veo3-api-key"
    )

    automation.assign_phones(setup_phone_assignments())

    cycle = 1
    while True:
        print(f"\n{'='*70}")
        print(f"🔄 Cycle {cycle} - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        try:
            automation.run_viral_pipeline(
                discovery_limit=10,
                content_to_generate=3
            )

            print(f"\n✅ Cycle {cycle} complete. Waiting 1 hour...")
            time.sleep(3600)  # Wait 1 hour

            cycle += 1

        except KeyboardInterrupt:
            print("\n\n⏹️  Stopping continuous monitoring...")
            break
        except Exception as e:
            print(f"\n❌ Error in cycle {cycle}: {e}")
            print("   Retrying in 5 minutes...")
            time.sleep(300)  # Wait 5 minutes before retry


def multi_account_posting():
    """
    Post same content to multiple accounts.

    Use all 20 phones to post the same viral content
    to increase reach and engagement.
    """
    print("\n📢 Multi-Account Posting Mode\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=True)

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    automation = SocialMediaAutomation(phone_manager)
    automation.assign_phones(setup_phone_assignments())

    from phone_agent.social_automation import GeneratedContent

    content = GeneratedContent(
        video_path="/path/to/super_viral.mp4",
        caption="🚀 This is going viral! #trending #fyp #viral",
        hashtags=["trending", "fyp", "viral", "mustsee"],
        platforms=[Platform.TIKTOK],
        metadata={"campaign": "viral_boost"}
    )

    # Post from all 5 TikTok accounts for maximum reach
    tiktok_phones = ["phone_01", "phone_02", "phone_03", "phone_04", "phone_05"]

    print(f"📤 Posting to {len(tiktok_phones)} TikTok accounts...")

    for phone in tiktok_phones:
        automation.post_content(content, Platform.TIKTOK, phone)
        time.sleep(30)  # Wait between posts to avoid rate limiting

    print("\n✅ Posted to all accounts!")


if __name__ == "__main__":
    print("\n🎬 Viral Content Automation - Choose Mode:\n")
    print("1. Full Pipeline (discover → analyze → generate → post)")
    print("2. Discovery Only")
    print("3. Post Only")
    print("4. Continuous Monitoring (runs forever)")
    print("5. Multi-Account Posting")

    choice = input("\nEnter mode number (1-5): ").strip()

    modes = {
        "1": main,
        "2": discover_only_mode,
        "3": post_only_mode,
        "4": continuous_monitoring,
        "5": multi_account_posting
    }

    if choice in modes:
        modes[choice]()
    else:
        print("Invalid choice. Running full pipeline...")
        main()
