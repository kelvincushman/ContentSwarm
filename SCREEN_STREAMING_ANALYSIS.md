# Phone Screen Streaming - Technical Analysis

## Bandwidth Analysis for 20 Phones

### Per-Phone Bandwidth Requirements

**High Quality Stream (1080×1920 @ 30fps):**
- Bitrate: ~5-8 Mbps per phone
- 20 phones: 100-160 Mbps total
- **Status: ⚠️ High bandwidth - not recommended**

**Medium Quality Stream (720×1280 @ 15fps):**
- Bitrate: ~1-2 Mbps per phone
- 20 phones: 20-40 Mbps total
- **Status: ✅ Acceptable for gigabit networks**

**Low Quality Stream (480×854 @ 10fps):**
- Bitrate: ~500 Kbps per phone
- 20 phones: 10 Mbps total
- **Status: ✅ Recommended for dashboard monitoring**

**Thumbnail Mode (240×427 @ 5fps):**
- Bitrate: ~200 Kbps per phone
- 20 phones: 4 Mbps total
- **Status: ✅ Best for overview grid**

### Network Capacity Check

```bash
# Test your network speed
# Upload speed is critical (phones → server → browser)
speedtest-cli

# Recommended minimum:
# - 100 Mbps for medium quality (all 20 phones)
# - 50 Mbps for low quality
# - 10 Mbps for thumbnail mode
```

## Implementation Options

### Option 1: Thumbnail Grid (Recommended)

**Show all 20 phones at once in small previews**

**Pros:**
- ✅ Low bandwidth (4 Mbps total)
- ✅ See all phones at once
- ✅ Good for monitoring
- ✅ Works on most networks

**Cons:**
- ⚠️ Small screens, hard to see details
- Need to click to enlarge

**Implementation:**
- 240×427 resolution @ 5fps
- JPEG compression for each frame
- Update every 200ms (5fps)
- Click to view full screen

### Option 2: Selective Streaming (Smart Choice)

**Only stream the currently selected phone(s)**

**Pros:**
- ✅ Very low bandwidth (1-2 Mbps for 1 phone)
- ✅ High quality possible
- ✅ Full resolution (1080×1920 @ 30fps)
- ✅ No performance issues

**Cons:**
- ⚠️ Can't see all phones at once
- Only monitor active phone

**Implementation:**
- Full quality stream for selected phone
- Thumbnails for others (click to switch)
- 1080×1920 @ 30fps for active phone
- 240×427 @ 2fps for inactive phones

### Option 3: Hybrid Approach (Best Balance)

**Thumbnail grid + enlarged view**

**Bandwidth:**
- Thumbnails: 4 Mbps (all 20 phones)
- Full stream: 2 Mbps (selected phone)
- **Total: ~6 Mbps**

**UI Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Left Side (30%)        │  Right Side (70%)            │
│  ────────────────       │  ────────────────            │
│  Phone Grid (5×4)       │  Enlarged View               │
│                         │                              │
│  [P1] [P2] [P3] [P4]    │  ┌────────────────────┐     │
│  [P5] [P6] [P7] [P8]    │  │                    │     │
│  [P9] [10] [11] [12]    │  │  Selected Phone    │     │
│  [13] [14] [15] [16]    │  │  Full Resolution   │     │
│  [17] [18] [19] [20]    │  │  1080×1920         │     │
│                         │  │                    │     │
│  Click to select        │  └────────────────────┘     │
│                         │                              │
│                         │  Controls: ⏸ 📸 📹 🔄       │
└─────────────────────────────────────────────────────────┘
```

## Technical Implementation

### Method 1: ADB Screenshot Polling (Simplest)

**How it works:**
- Take screenshots via ADB every 200ms
- Compress to JPEG
- Send to browser via WebSocket

**Code:**
```python
# In dashboard/app.py
import subprocess
import base64
from threading import Thread
import time

class PhoneScreenStreamer:
    def __init__(self, device_id, quality='thumbnail'):
        self.device_id = device_id
        self.quality = quality
        self.running = False
        self.latest_frame = None

    def start(self):
        self.running = True
        Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while self.running:
            try:
                # Capture screenshot
                result = subprocess.run(
                    ['adb', '-s', self.device_id, 'exec-out', 'screencap', '-p'],
                    capture_output=True,
                    timeout=1
                )

                if result.returncode == 0:
                    # Resize based on quality
                    if self.quality == 'thumbnail':
                        # Resize to 240×427
                        frame = self._resize_image(result.stdout, 240, 427)
                    elif self.quality == 'medium':
                        # Resize to 720×1280
                        frame = self._resize_image(result.stdout, 720, 1280)
                    else:
                        # Full resolution
                        frame = result.stdout

                    # Convert to base64 for WebSocket
                    self.latest_frame = base64.b64encode(frame).decode()

                    # Emit to connected clients
                    socketio.emit('screen_frame', {
                        'device_id': self.device_id,
                        'frame': self.latest_frame
                    })

            except Exception as e:
                print(f"Screen capture error: {e}")

            # Frame rate control
            if self.quality == 'thumbnail':
                time.sleep(0.2)  # 5fps
            elif self.quality == 'medium':
                time.sleep(0.067)  # 15fps
            else:
                time.sleep(0.033)  # 30fps

    def _resize_image(self, image_data, width, height):
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_data))
        img = img.resize((width, height), Image.LANCZOS)

        # Convert to JPEG with compression
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=70)
        return output.getvalue()

    def stop(self):
        self.running = False
```

**Bandwidth:**
- Thumbnail: ~200 Kbps per phone
- Medium: ~1 Mbps per phone
- Full: ~2 Mbps per phone

**Pros:**
- ✅ Simple implementation
- ✅ Works with standard ADB
- ✅ No additional dependencies

**Cons:**
- ⚠️ Higher CPU usage (constant screenshots)
- ⚠️ Slight lag (~200ms)

### Method 2: scrcpy (Better Performance)

**How it works:**
- Use scrcpy (screen copy) for efficient streaming
- Hardware-accelerated video encoding on phone
- H.264 stream via ADB

**Installation:**
```bash
# Install scrcpy
sudo apt install scrcpy  # Linux
brew install scrcpy      # macOS
# Windows: Download from https://github.com/Genymobile/scrcpy/releases

# Test single phone
scrcpy -s 192.168.1.100:5555 --video-codec=h264 --max-fps=15 --max-size=720
```

**Code:**
```python
# More efficient streaming with scrcpy
class ScrcpyStreamer:
    def __init__(self, device_id, quality='thumbnail'):
        self.device_id = device_id
        self.quality = quality
        self.process = None

    def start(self):
        # scrcpy parameters based on quality
        params = {
            'thumbnail': ['--max-size=240', '--max-fps=5', '--video-bit-rate=200K'],
            'medium': ['--max-size=720', '--max-fps=15', '--video-bit-rate=1M'],
            'full': ['--max-size=1080', '--max-fps=30', '--video-bit-rate=2M']
        }

        cmd = [
            'scrcpy',
            '-s', self.device_id,
            '--video-codec=h264',
            '--no-audio',
            '--no-control',  # View only, no control
            '--video-encoder=OMX.google.h264.encoder',  # Hardware encoder
        ] + params.get(self.quality, params['thumbnail'])

        # Pipe output to WebSocket
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
```

**Bandwidth:**
- Thumbnail: ~200 Kbps per phone (hardware encoded)
- Medium: ~1 Mbps per phone
- Full: ~2 Mbps per phone

**Pros:**
- ✅ Hardware encoding (low CPU)
- ✅ Lower latency (~50ms)
- ✅ Efficient H.264 streaming
- ✅ Better quality per bitrate

**Cons:**
- ⚠️ Requires scrcpy installation
- ⚠️ More complex setup

### Method 3: WebRTC (Advanced)

**For real-time interaction:**
- Ultra-low latency (<50ms)
- Two-way communication
- Browser-native streaming

**Bandwidth:** Similar to scrcpy but better quality

**Best for:** Full phone control from browser

## Recommended Implementation

### Phase 1: Thumbnail Grid (Start Here)

```python
# dashboard/app.py additions

from phone_screen_streaming import PhoneScreenStreamer

# Store streamers
screen_streamers = {}

@app.route('/api/screens/start', methods=['POST'])
def start_screen_streaming():
    """Start thumbnail streaming for all phones"""
    data = request.json
    mode = data.get('mode', 'thumbnail')  # thumbnail, selective, hybrid

    if mode == 'thumbnail':
        # Start thumbnail streams for all phones
        for phone in phones:
            streamer = PhoneScreenStreamer(phone['device_id'], 'thumbnail')
            streamer.start()
            screen_streamers[phone['name']] = streamer

    return jsonify({'success': True})

@app.route('/api/screens/stop', methods=['POST'])
def stop_screen_streaming():
    """Stop all screen streaming"""
    for streamer in screen_streamers.values():
        streamer.stop()
    screen_streamers.clear()

    return jsonify({'success': True})

@app.route('/api/screens/upgrade', methods=['POST'])
def upgrade_screen_quality():
    """Upgrade specific phone to full quality"""
    data = request.json
    phone_name = data['phone_name']

    if phone_name in screen_streamers:
        # Stop thumbnail
        screen_streamers[phone_name].stop()

        # Start full quality
        phone = next(p for p in phones if p['name'] == phone_name)
        streamer = PhoneScreenStreamer(phone['device_id'], 'full')
        streamer.start()
        screen_streamers[phone_name] = streamer

    return jsonify({'success': True})
```

### Phase 2: Add to Dashboard HTML

```html
<!-- In dashboard/templates/dashboard.html -->

<!-- Add new tab -->
<button class="nav-item" data-tab="screens" onclick="showTab('screens')">
    📱 Screens
</button>

<!-- Add tab content -->
<div class="tab-content" id="screens-tab">
    <div class="tab-header">
        <h2>Phone Screens</h2>
        <div class="controls">
            <button class="btn btn-success" onclick="startScreens()">▶ Start Streaming</button>
            <button class="btn btn-danger" onclick="stopScreens()">⏹ Stop Streaming</button>
            <select id="screen-quality">
                <option value="thumbnail">Thumbnail (Low Bandwidth)</option>
                <option value="medium">Medium Quality</option>
                <option value="full">Full Quality (Selected Only)</option>
            </select>
        </div>
    </div>

    <!-- Hybrid layout -->
    <div class="screen-container">
        <!-- Left: Thumbnail grid -->
        <div class="screen-grid">
            <!-- Will be populated with 20 phone thumbnails -->
        </div>

        <!-- Right: Enlarged view -->
        <div class="screen-viewer">
            <div id="selected-screen">
                <p>Select a phone to view full screen</p>
            </div>
            <div class="viewer-controls">
                <button onclick="pauseStream()">⏸ Pause</button>
                <button onclick="screenshotStream()">📸 Screenshot</button>
                <button onclick="recordStream()">📹 Record</button>
                <button onclick="refreshStream()">🔄 Refresh</button>
            </div>
        </div>
    </div>

    <div class="bandwidth-monitor">
        <span>Bandwidth: <span id="bandwidth-usage">0 Mbps</span></span>
        <span>FPS: <span id="stream-fps">0</span></span>
    </div>
</div>
```

### Phase 3: JavaScript Implementation

```javascript
// In dashboard/static/js/dashboard.js

// Screen streaming state
let screenStreaming = false;
let screenQuality = 'thumbnail';
let selectedScreen = null;

// Start screen streaming
async function startScreens() {
    const quality = document.getElementById('screen-quality').value;

    try {
        const response = await fetch('/api/screens/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: quality })
        });

        const data = await response.json();
        if (data.success) {
            screenStreaming = true;
            screenQuality = quality;
            showToast('Screen streaming started', 'success');
            initializeScreenGrid();
        }
    } catch (error) {
        showToast('Failed to start streaming', 'error');
    }
}

// Stop screen streaming
async function stopScreens() {
    try {
        const response = await fetch('/api/screens/stop', {
            method: 'POST'
        });

        const data = await response.json();
        if (data.success) {
            screenStreaming = false;
            showToast('Screen streaming stopped', 'success');
        }
    } catch (error) {
        showToast('Failed to stop streaming', 'error');
    }
}

// Initialize screen grid
function initializeScreenGrid() {
    const grid = document.querySelector('.screen-grid');
    grid.innerHTML = '';

    phones.forEach(phone => {
        const item = document.createElement('div');
        item.className = 'screen-item';
        item.dataset.phoneName = phone.name;
        item.innerHTML = `
            <canvas id="screen-${phone.name}" width="240" height="427"></canvas>
            <div class="screen-label">${phone.name}</div>
        `;
        item.addEventListener('click', () => selectScreenView(phone.name));
        grid.appendChild(item);
    });
}

// Select screen for enlarged view
async function selectScreenView(phoneName) {
    selectedScreen = phoneName;

    // Upgrade to full quality
    await fetch('/api/screens/upgrade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_name: phoneName })
    });

    // Update UI
    document.querySelectorAll('.screen-item').forEach(item => {
        item.classList.remove('selected');
    });
    document.querySelector(`[data-phone-name="${phoneName}"]`).classList.add('selected');
}

// Handle incoming screen frames
socket.on('screen_frame', (data) => {
    const canvas = document.getElementById(`screen-${data.device_id}`);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const img = new Image();
    img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = 'data:image/jpeg;base64,' + data.frame;

    // If this is the selected phone, also update enlarged view
    if (selectedScreen && data.device_id.includes(selectedScreen)) {
        updateEnlargedView(data.frame);
    }
});

// Update enlarged viewer
function updateEnlargedView(frameData) {
    const viewer = document.getElementById('selected-screen');
    viewer.innerHTML = `<img src="data:image/jpeg;base64,${frameData}" style="max-width: 100%; height: auto;">`;
}
```

## Bandwidth Optimization Strategies

### 1. Adaptive Quality

```python
# Auto-adjust based on network conditions
def adjust_stream_quality(network_speed_mbps):
    if network_speed_mbps < 10:
        return 'thumbnail'  # 4 Mbps total
    elif network_speed_mbps < 50:
        return 'medium'  # 20 Mbps total
    else:
        return 'full'  # 40 Mbps total
```

### 2. On-Demand Streaming

- Only stream phones that are visible on screen
- Pause streams when tab is not active
- Use lower frame rate when idle

### 3. Compression

```python
# Higher JPEG compression for thumbnails
img.save(output, format='JPEG', quality=60)  # Thumbnail
img.save(output, format='JPEG', quality=80)  # Full view
```

### 4. Frame Rate Throttling

```javascript
// Client-side frame rate limit
let lastFrameTime = 0;
const minFrameInterval = 200; // 5fps max

socket.on('screen_frame', (data) => {
    const now = Date.now();
    if (now - lastFrameTime < minFrameInterval) {
        return; // Skip frame
    }
    lastFrameTime = now;
    // Render frame...
});
```

## Performance Impact

### Server CPU Usage
- **Thumbnail (20 phones):** 10-20% CPU
- **Medium (20 phones):** 30-50% CPU
- **Selective (1 phone):** 5-10% CPU

### Memory Usage
- **Per phone stream:** ~50MB
- **20 phones:** ~1GB total

### Battery Impact on Phones
- **Screen on:** Normal (screens already on for automation)
- **ADB:** Minimal (<5% battery drain)

## Recommended Setup

For your use case (20 phones, viral content automation):

**Best Configuration:**
```
Mode: Hybrid
- Thumbnail grid: 240×427 @ 5fps for all 20 phones
- Enlarged view: 1080×1920 @ 30fps for selected phone
- Total bandwidth: ~6 Mbps
- Server CPU: ~15-20%
- Works on: 100 Mbps network or better
```

**Implementation Priority:**
1. ✅ Phase 1: Thumbnail grid (monitoring)
2. ✅ Phase 2: Click to enlarge (detailed view)
3. ⏭️ Phase 3: Screen recording (optional)
4. ⏭️ Phase 4: Remote control (advanced)

## Network Requirements

**Minimum:**
- 10 Mbps upload (from server)
- 10 Mbps download (to browser)
- Low latency (<50ms)

**Recommended:**
- 100 Mbps network
- Gigabit router
- Phones and server on same subnet
- 5GHz WiFi for phones

**Test Your Network:**
```bash
# Test bandwidth from server
iperf3 -s

# From another device
iperf3 -c <server-ip>

# Should show > 50 Mbps for smooth streaming
```

## Next Steps

1. **Test network capacity** (run iperf3)
2. **Start with thumbnail grid** (lowest bandwidth)
3. **Monitor performance** (check CPU, bandwidth)
4. **Scale up** if network allows

Would you like me to implement the thumbnail grid first?
