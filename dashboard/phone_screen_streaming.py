"""
Phone Screen Streaming Module
Captures and streams phone screens via ADB with bandwidth optimization
"""

import subprocess
import base64
from threading import Thread, Event
import time
from typing import Optional, Dict, Callable
from PIL import Image
import io
from dataclasses import dataclass
from enum import Enum


class StreamQuality(Enum):
    """Stream quality presets with bandwidth targets"""
    THUMBNAIL = "thumbnail"  # 240×427 @ 5fps (~200 Kbps)
    MEDIUM = "medium"        # 720×1280 @ 15fps (~1 Mbps)
    FULL = "full"            # 1080×1920 @ 30fps (~2 Mbps)


@dataclass
class QualitySettings:
    """Quality-specific streaming settings"""
    width: int
    height: int
    fps: int
    jpeg_quality: int
    bandwidth_kbps: int


# Quality presets
QUALITY_PRESETS: Dict[StreamQuality, QualitySettings] = {
    StreamQuality.THUMBNAIL: QualitySettings(
        width=240, height=427, fps=5, jpeg_quality=60, bandwidth_kbps=200
    ),
    StreamQuality.MEDIUM: QualitySettings(
        width=720, height=1280, fps=15, jpeg_quality=75, bandwidth_kbps=1000
    ),
    StreamQuality.FULL: QualitySettings(
        width=1080, height=1920, fps=30, jpeg_quality=85, bandwidth_kbps=2000
    ),
}


class PhoneScreenStreamer:
    """
    Captures and streams phone screen via ADB

    Features:
    - Configurable quality (thumbnail/medium/full)
    - Frame rate control
    - JPEG compression
    - Bandwidth monitoring
    - Thread-safe operation

    Example:
        streamer = PhoneScreenStreamer(
            device_id="192.168.1.100:5555",
            quality=StreamQuality.THUMBNAIL,
            on_frame=lambda frame: socketio.emit('screen_frame', frame)
        )
        streamer.start()
        # ... later ...
        streamer.stop()
    """

    def __init__(
        self,
        device_id: str,
        quality: StreamQuality = StreamQuality.THUMBNAIL,
        on_frame: Optional[Callable[[Dict], None]] = None
    ):
        """
        Initialize screen streamer

        Args:
            device_id: ADB device ID (e.g., "192.168.1.100:5555")
            quality: Stream quality (THUMBNAIL, MEDIUM, or FULL)
            on_frame: Callback function for new frames (receives dict with frame data)
        """
        self.device_id = device_id
        self.quality = quality
        self.settings = QUALITY_PRESETS[quality]
        self.on_frame = on_frame

        self.running = False
        self.paused = False
        self.thread: Optional[Thread] = None
        self.stop_event = Event()

        # Stats
        self.frames_captured = 0
        self.frames_sent = 0
        self.bytes_sent = 0
        self.errors = 0
        self.start_time = 0

    def start(self):
        """Start streaming in background thread"""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()
        self.start_time = time.time()

        self.thread = Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop streaming"""
        self.running = False
        self.stop_event.set()

        if self.thread:
            self.thread.join(timeout=2)

    def pause(self):
        """Pause streaming (keep thread alive but don't capture)"""
        self.paused = True

    def resume(self):
        """Resume streaming"""
        self.paused = False

    def set_quality(self, quality: StreamQuality):
        """Change stream quality (requires restart)"""
        was_running = self.running
        if was_running:
            self.stop()

        self.quality = quality
        self.settings = QUALITY_PRESETS[quality]

        if was_running:
            self.start()

    def get_stats(self) -> Dict:
        """Get streaming statistics"""
        runtime = time.time() - self.start_time if self.running else 0

        return {
            'device_id': self.device_id,
            'quality': self.quality.value,
            'running': self.running,
            'paused': self.paused,
            'frames_captured': self.frames_captured,
            'frames_sent': self.frames_sent,
            'bytes_sent': self.bytes_sent,
            'errors': self.errors,
            'runtime_seconds': runtime,
            'fps': self.frames_sent / runtime if runtime > 0 else 0,
            'bandwidth_kbps': (self.bytes_sent * 8 / 1024) / runtime if runtime > 0 else 0,
        }

    def _capture_loop(self):
        """Main capture loop (runs in background thread)"""
        frame_interval = 1.0 / self.settings.fps

        while self.running and not self.stop_event.is_set():
            loop_start = time.time()

            try:
                if not self.paused:
                    self._capture_and_send_frame()

            except Exception as e:
                self.errors += 1
                print(f"Screen capture error for {self.device_id}: {e}")

            # Frame rate control - sleep for remaining time
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)

            if sleep_time > 0:
                self.stop_event.wait(timeout=sleep_time)

    def _capture_and_send_frame(self):
        """Capture one frame and send via callback"""
        # Capture screenshot via ADB
        result = subprocess.run(
            ['adb', '-s', self.device_id, 'exec-out', 'screencap', '-p'],
            capture_output=True,
            timeout=2
        )

        if result.returncode != 0:
            raise Exception(f"ADB screencap failed: {result.stderr.decode()}")

        self.frames_captured += 1

        # Resize and compress
        frame_data = self._process_frame(result.stdout)

        # Convert to base64 for WebSocket transmission
        frame_b64 = base64.b64encode(frame_data).decode('utf-8')

        self.frames_sent += 1
        self.bytes_sent += len(frame_data)

        # Send via callback
        if self.on_frame:
            frame_info = {
                'device_id': self.device_id,
                'frame': frame_b64,
                'width': self.settings.width,
                'height': self.settings.height,
                'quality': self.quality.value,
                'frame_number': self.frames_sent,
                'timestamp': time.time(),
            }
            self.on_frame(frame_info)

    def _process_frame(self, raw_png: bytes) -> bytes:
        """Resize and compress screenshot"""
        # Open PNG image
        img = Image.open(io.BytesIO(raw_png))

        # Resize to target resolution
        img = img.resize(
            (self.settings.width, self.settings.height),
            Image.Resampling.LANCZOS
        )

        # Convert to JPEG with compression
        output = io.BytesIO()
        img.save(
            output,
            format='JPEG',
            quality=self.settings.jpeg_quality,
            optimize=True
        )

        return output.getvalue()


class StreamManager:
    """
    Manages multiple phone screen streams

    Features:
    - Start/stop streams for multiple phones
    - Quality management
    - Aggregate statistics
    - Bandwidth monitoring

    Example:
        manager = StreamManager(
            on_frame=lambda frame: socketio.emit('screen_frame', frame)
        )

        # Start thumbnails for all phones
        manager.start_all(phone_configs, StreamQuality.THUMBNAIL)

        # Upgrade one phone to full quality
        manager.upgrade_quality("phone_01", StreamQuality.FULL)

        # Get stats
        stats = manager.get_aggregate_stats()
    """

    def __init__(self, on_frame: Optional[Callable[[Dict], None]] = None):
        """
        Initialize stream manager

        Args:
            on_frame: Callback function for frames from any phone
        """
        self.on_frame = on_frame
        self.streamers: Dict[str, PhoneScreenStreamer] = {}

    def start_stream(
        self,
        phone_name: str,
        device_id: str,
        quality: StreamQuality = StreamQuality.THUMBNAIL
    ):
        """Start stream for one phone"""
        if phone_name in self.streamers:
            self.stop_stream(phone_name)

        streamer = PhoneScreenStreamer(
            device_id=device_id,
            quality=quality,
            on_frame=self.on_frame
        )
        streamer.start()

        self.streamers[phone_name] = streamer

    def stop_stream(self, phone_name: str):
        """Stop stream for one phone"""
        if phone_name in self.streamers:
            self.streamers[phone_name].stop()
            del self.streamers[phone_name]

    def start_all(self, phones: list, quality: StreamQuality = StreamQuality.THUMBNAIL):
        """
        Start streams for all phones

        Args:
            phones: List of phone configs with 'name' and 'device_id'
            quality: Quality for all streams
        """
        for phone in phones:
            self.start_stream(
                phone_name=phone['name'],
                device_id=phone['device_id'],
                quality=quality
            )

    def stop_all(self):
        """Stop all streams"""
        for phone_name in list(self.streamers.keys()):
            self.stop_stream(phone_name)

    def pause_all(self):
        """Pause all streams"""
        for streamer in self.streamers.values():
            streamer.pause()

    def resume_all(self):
        """Resume all streams"""
        for streamer in self.streamers.values():
            streamer.resume()

    def upgrade_quality(self, phone_name: str, quality: StreamQuality):
        """Upgrade quality for specific phone"""
        if phone_name in self.streamers:
            self.streamers[phone_name].set_quality(quality)

    def downgrade_others(self, selected_phone: str):
        """Downgrade all phones except selected one to thumbnail"""
        for phone_name, streamer in self.streamers.items():
            if phone_name != selected_phone:
                streamer.set_quality(StreamQuality.THUMBNAIL)

    def get_stats(self, phone_name: str) -> Optional[Dict]:
        """Get stats for specific phone"""
        if phone_name in self.streamers:
            return self.streamers[phone_name].get_stats()
        return None

    def get_aggregate_stats(self) -> Dict:
        """Get aggregate statistics for all streams"""
        total_frames = 0
        total_bytes = 0
        total_errors = 0
        active_streams = 0

        for streamer in self.streamers.values():
            stats = streamer.get_stats()
            total_frames += stats['frames_sent']
            total_bytes += stats['bytes_sent']
            total_errors += stats['errors']
            if stats['running'] and not stats['paused']:
                active_streams += 1

        # Calculate aggregate bandwidth
        total_runtime = max(
            (s.get_stats()['runtime_seconds'] for s in self.streamers.values()),
            default=0
        )

        return {
            'total_streams': len(self.streamers),
            'active_streams': active_streams,
            'total_frames': total_frames,
            'total_bytes': total_bytes,
            'total_errors': total_errors,
            'bandwidth_mbps': (total_bytes * 8 / 1_000_000) / total_runtime if total_runtime > 0 else 0,
            'average_fps': total_frames / total_runtime if total_runtime > 0 else 0,
        }


# Bandwidth estimation helper
def estimate_bandwidth(num_phones: int, quality: StreamQuality) -> float:
    """
    Estimate total bandwidth for N phones

    Args:
        num_phones: Number of phones streaming
        quality: Stream quality

    Returns:
        Estimated bandwidth in Mbps
    """
    settings = QUALITY_PRESETS[quality]
    total_kbps = settings.bandwidth_kbps * num_phones
    return total_kbps / 1000  # Convert to Mbps


if __name__ == '__main__':
    # Test streaming
    import sys

    if len(sys.argv) < 2:
        print("Usage: python phone_screen_streaming.py <device_id>")
        print("Example: python phone_screen_streaming.py 192.168.1.100:5555")
        sys.exit(1)

    device_id = sys.argv[1]

    # Test callback
    frame_count = 0
    def on_frame(frame_info):
        global frame_count
        frame_count += 1
        print(f"Frame {frame_count}: {len(frame_info['frame'])} bytes (base64)")

    # Start streaming
    print(f"Starting stream for {device_id}...")
    streamer = PhoneScreenStreamer(
        device_id=device_id,
        quality=StreamQuality.THUMBNAIL,
        on_frame=on_frame
    )
    streamer.start()

    try:
        # Stream for 10 seconds
        time.sleep(10)

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        streamer.stop()
        stats = streamer.get_stats()

        print("\nStreaming Statistics:")
        print(f"  Frames captured: {stats['frames_captured']}")
        print(f"  Frames sent: {stats['frames_sent']}")
        print(f"  Data sent: {stats['bytes_sent'] / 1024:.2f} KB")
        print(f"  Average FPS: {stats['fps']:.2f}")
        print(f"  Bandwidth: {stats['bandwidth_kbps']:.2f} Kbps")
        print(f"  Errors: {stats['errors']}")
