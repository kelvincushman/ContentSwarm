"""
ComfyUI Integration for Social Media Content Generation.

Supports:
- Image generation (Stable Diffusion, FLUX, etc.)
- Video generation (AnimateDiff, SVD, CogVideoX)
- Batch processing
- Custom workflows

Requirements:
- ComfyUI server running locally or remotely
- RTX 5060 16GB is perfect for this!
"""

import json
import time
import requests
import websocket
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ContentType(Enum):
    """Type of content to generate."""
    IMAGE = "image"
    VIDEO = "video"
    ANIMATION = "animation"


@dataclass
class GenerationRequest:
    """Request for content generation."""
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    num_frames: int = 16  # For video
    fps: int = 8  # For video
    content_type: ContentType = ContentType.IMAGE
    seed: int = -1  # -1 for random
    steps: int = 20
    cfg_scale: float = 7.0
    model: str = "sd_xl_base_1.0.safetensors"


@dataclass
class GeneratedContent:
    """Generated content from ComfyUI."""
    file_path: str
    prompt: str
    content_type: ContentType
    metadata: Dict[str, Any]


class ComfyUIClient:
    """
    Client for ComfyUI API.

    Example:
        >>> client = ComfyUIClient("http://127.0.0.1:8188")
        >>> request = GenerationRequest(
        ...     prompt="viral tiktok video, trending dance",
        ...     content_type=ContentType.VIDEO
        ... )
        >>> result = client.generate(request)
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8188",
        output_dir: str = "./generated_content"
    ):
        """
        Initialize ComfyUI client.

        Args:
            server_url: ComfyUI server URL
            output_dir: Directory to save generated content
        """
        self.server_url = server_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # WebSocket for progress tracking
        ws_url = server_url.replace('http://', 'ws://').replace('https://', 'wss://')
        self.ws_url = f"{ws_url}/ws"

    def generate(
        self,
        request: GenerationRequest,
        workflow_path: Optional[str] = None
    ) -> GeneratedContent:
        """
        Generate content using ComfyUI.

        Args:
            request: Generation request
            workflow_path: Path to custom ComfyUI workflow JSON

        Returns:
            GeneratedContent with file path
        """
        # Load workflow
        if workflow_path:
            workflow = self._load_workflow(workflow_path)
        else:
            # Use default workflow based on content type
            if request.content_type == ContentType.IMAGE:
                workflow = self._get_default_image_workflow()
            elif request.content_type == ContentType.VIDEO:
                workflow = self._get_default_video_workflow()
            else:
                raise ValueError(f"Unsupported content type: {request.content_type}")

        # Update workflow with request parameters
        workflow = self._update_workflow(workflow, request)

        # Queue prompt
        prompt_id = self._queue_prompt(workflow)

        print(f"🎨 Generating {request.content_type.value}...")
        print(f"   Prompt: {request.prompt}")
        print(f"   Prompt ID: {prompt_id}")

        # Wait for completion and get output
        output_path = self._wait_for_completion(prompt_id, request.content_type)

        return GeneratedContent(
            file_path=str(output_path),
            prompt=request.prompt,
            content_type=request.content_type,
            metadata={
                "prompt_id": prompt_id,
                "width": request.width,
                "height": request.height,
                "steps": request.steps,
                "cfg_scale": request.cfg_scale
            }
        )

    def _load_workflow(self, path: str) -> Dict:
        """Load workflow from JSON file."""
        with open(path) as f:
            return json.load(f)

    def _get_default_image_workflow(self) -> Dict:
        """
        Get default SDXL image generation workflow.

        This is a basic SDXL workflow. For better results,
        export a workflow from ComfyUI and use that instead.
        """
        return {
            "1": {
                "inputs": {
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["2", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "2": {
                "inputs": {
                    "ckpt_name": "sd_xl_base_1.0.safetensors"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "3": {
                "inputs": {
                    "text": "amazing viral content",
                    "clip": ["2", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "4": {
                "inputs": {
                    "text": "ugly, blurry, low quality",
                    "clip": ["2", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "5": {
                "inputs": {
                    "width": 1024,
                    "height": 1024,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "samples": ["1", 0],
                    "vae": ["2", 2]
                },
                "class_type": "VAEDecode"
            },
            "7": {
                "inputs": {
                    "filename_prefix": "generated",
                    "images": ["6", 0]
                },
                "class_type": "SaveImage"
            }
        }

    def _get_default_video_workflow(self) -> Dict:
        """
        Get default video generation workflow.

        Note: Requires AnimateDiff or similar video model.
        Export your own workflow from ComfyUI for better results.
        """
        # Placeholder - user should provide their own video workflow
        return {
            "note": "Please export a video workflow from ComfyUI",
            "suggested_models": [
                "AnimateDiff",
                "Stable Video Diffusion (SVD)",
                "CogVideoX"
            ]
        }

    def _update_workflow(
        self,
        workflow: Dict,
        request: GenerationRequest
    ) -> Dict:
        """Update workflow with request parameters."""
        # This is a simplified update
        # In practice, you'd need to map request params to specific nodes

        for node_id, node in workflow.items():
            if node.get("class_type") == "CLIPTextEncode":
                if "positive" in str(node.get("inputs", {})):
                    node["inputs"]["text"] = request.prompt
                elif "negative" in str(node.get("inputs", {})):
                    node["inputs"]["text"] = request.negative_prompt

            elif node.get("class_type") == "KSampler":
                node["inputs"]["seed"] = request.seed
                node["inputs"]["steps"] = request.steps
                node["inputs"]["cfg"] = request.cfg_scale

            elif node.get("class_type") == "EmptyLatentImage":
                node["inputs"]["width"] = request.width
                node["inputs"]["height"] = request.height

            elif node.get("class_type") == "CheckpointLoaderSimple":
                node["inputs"]["ckpt_name"] = request.model

        return workflow

    def _queue_prompt(self, workflow: Dict) -> str:
        """Queue a prompt and return prompt_id."""
        payload = {
            "prompt": workflow,
            "client_id": "social_automation"
        }

        response = requests.post(
            f"{self.server_url}/prompt",
            json=payload
        )
        response.raise_for_status()

        result = response.json()
        return result["prompt_id"]

    def _wait_for_completion(
        self,
        prompt_id: str,
        content_type: ContentType
    ) -> Path:
        """Wait for generation to complete and return output path."""
        # Connect to WebSocket for progress
        ws = websocket.WebSocket()
        ws.connect(self.ws_url)

        print("   Progress: ", end="", flush=True)

        while True:
            try:
                message = json.loads(ws.recv())

                if message["type"] == "progress":
                    data = message["data"]
                    current = data.get("value", 0)
                    max_val = data.get("max", 100)
                    percent = int((current / max_val) * 100)
                    print(f"\r   Progress: {percent}%", end="", flush=True)

                elif message["type"] == "executing":
                    data = message["data"]
                    if data.get("node") is None:
                        # Execution complete
                        print("\r   Progress: 100% ✅")
                        break

            except Exception as e:
                print(f"\n   WebSocket error: {e}")
                break

        ws.close()

        # Get output files
        time.sleep(1)  # Wait for file to be saved
        history = self._get_history(prompt_id)

        # Find output file
        output_path = self._extract_output_path(history, content_type)

        return output_path

    def _get_history(self, prompt_id: str) -> Dict:
        """Get generation history."""
        response = requests.get(f"{self.server_url}/history/{prompt_id}")
        response.raise_for_status()
        return response.json()

    def _extract_output_path(
        self,
        history: Dict,
        content_type: ContentType
    ) -> Path:
        """Extract output file path from history."""
        # ComfyUI saves to output folder by default
        # This is simplified - adjust based on your workflow

        for prompt_id, data in history.items():
            outputs = data.get("outputs", {})
            for node_id, output in outputs.items():
                if "images" in output:
                    # Image output
                    image_info = output["images"][0]
                    filename = image_info["filename"]
                    subfolder = image_info.get("subfolder", "")

                    # Construct path
                    comfy_output = Path.home() / "ComfyUI" / "output"
                    if subfolder:
                        comfy_output = comfy_output / subfolder

                    source_path = comfy_output / filename

                    # Copy to our output dir
                    dest_path = self.output_dir / filename
                    if source_path.exists():
                        import shutil
                        shutil.copy2(source_path, dest_path)
                        return dest_path

        raise RuntimeError("Could not find output file")

    def batch_generate(
        self,
        requests: List[GenerationRequest],
        workflow_path: Optional[str] = None
    ) -> List[GeneratedContent]:
        """
        Generate multiple pieces of content.

        Args:
            requests: List of generation requests
            workflow_path: Optional custom workflow

        Returns:
            List of generated content
        """
        results = []

        for i, request in enumerate(requests, 1):
            print(f"\n📦 Batch {i}/{len(requests)}")
            result = self.generate(request, workflow_path)
            results.append(result)

        return results


class TikTokVideoGenerator:
    """Helper for generating TikTok-style videos."""

    def __init__(self, comfy_client: ComfyUIClient):
        self.client = comfy_client

    def generate_from_trend(
        self,
        trend_analysis: Dict,
        style: str = "viral"
    ) -> GeneratedContent:
        """
        Generate TikTok video based on trend analysis.

        Args:
            trend_analysis: Analysis from 12labs
            style: Video style (viral, aesthetic, comedy, etc.)

        Returns:
            Generated video content
        """
        # Build prompt from analysis
        prompt = self._build_prompt(trend_analysis, style)

        request = GenerationRequest(
            prompt=prompt,
            negative_prompt="low quality, blurry, watermark, ugly",
            width=1080,
            height=1920,  # TikTok vertical format
            num_frames=48,  # 6 seconds at 8fps
            fps=8,
            content_type=ContentType.VIDEO,
            steps=25,
            cfg_scale=7.5
        )

        return self.client.generate(request)

    def _build_prompt(self, analysis: Dict, style: str) -> str:
        """Build generation prompt from trend analysis."""
        mood = analysis.get("mood", "energetic")
        visual_style = analysis.get("visual_style", "colorful")
        actions = ", ".join(analysis.get("detected_actions", []))

        prompt = (
            f"professional {style} tiktok video, "
            f"{mood} mood, {visual_style} aesthetic, "
            f"featuring {actions}, "
            f"trending, viral content, "
            f"high quality, cinematic, "
            f"vertical 9:16 format"
        )

        return prompt


# Preset workflows for common social media formats
PRESET_WORKFLOWS = {
    "tiktok_vertical": {
        "width": 1080,
        "height": 1920,
        "format": "mp4",
        "description": "Vertical format for TikTok"
    },
    "instagram_reel": {
        "width": 1080,
        "height": 1920,
        "format": "mp4",
        "description": "Vertical format for Instagram Reels"
    },
    "youtube_shorts": {
        "width": 1080,
        "height": 1920,
        "format": "mp4",
        "description": "Vertical format for YouTube Shorts"
    },
    "instagram_post": {
        "width": 1080,
        "height": 1080,
        "format": "png",
        "description": "Square format for Instagram posts"
    },
    "twitter_banner": {
        "width": 1500,
        "height": 500,
        "format": "png",
        "description": "Twitter/X banner format"
    }
}


def test_comfyui_connection(server_url: str = "http://127.0.0.1:8188") -> bool:
    """
    Test connection to ComfyUI server.

    Args:
        server_url: ComfyUI server URL

    Returns:
        True if connected successfully
    """
    try:
        response = requests.get(f"{server_url}/system_stats")
        response.raise_for_status()

        stats = response.json()
        print("\n✅ ComfyUI Connected!")
        print(f"   System: {stats.get('system', {})}")
        return True

    except Exception as e:
        print(f"\n❌ ComfyUI Connection Failed: {e}")
        print(f"   Make sure ComfyUI is running at {server_url}")
        return False
