# ContentSwarm Dashboard

Real-time web dashboard for managing the phone fleet and social media automation.

## Features

- **📱 Phone Management**: Monitor and control all 20 phones from one interface
- **🚀 Automation Pipeline**: Start/stop viral content automation workflows
- **📊 Analytics**: Track performance across all platforms
- **📝 Live Logs**: Real-time system logs and events
- **🔄 Real-time Updates**: WebSocket-based live updates

## Screenshots

### Overview Tab
- Quick stats (total phones, active phones, queue length)
- Phone grid with status indicators
- System status at a glance

### Phones Tab
- Complete list of all 20 phones
- Connection status for each phone
- Select and control individual phones
- Run tasks directly from the UI


### Automation Tab
- Start/stop viral content pipeline
- Configure discovery and generation settings
- Monitor pipeline progress (Discovery → Analysis → Generation → Posting)
- View automation logs

### Analytics Tab
- Total generated content
- Total posts across platforms
- Success rate metrics
- Per-platform statistics

### Logs Tab
- Real-time system logs
- Filter by log level (info, warning, error)
- Timestamps for all events

## Installation

### 1. Install Dependencies

```bash
cd dashboard
pip install -r requirements.txt
```

### 2. Configure Phone Manager

Make sure your `phones_config.json` is configured with all 20 phones:

```json
{
  "phones": [
    {
      "device_id": "192.168.1.100:5555",
      "name": "phone_01",
      "description": "TikTok Account 1",
      "tags": ["tiktok"]
    },
    // ... 19 more phones
  ]
}
```

### 3. Setup Model API

Configure your model API in the dashboard:

**Option A: Novita AI (Recommended for 20 phones)**
```python
model_config = ModelConfig(
    base_url="https://api.novita.ai/openai",
    model_name="zai-org/autoglm-phone-9b-multilingual",
    api_key="your-novita-api-key"
)
```

**Option B: Self-hosted (RTX 5060 16GB)**
```python
model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b-multilingual"
)
```

## Usage

### Start the Dashboard

```bash
cd dashboard
python app.py
```

The dashboard will be available at: **http://localhost:5000**

### Access from Other Devices

To access from other devices on your network:

```bash
# Find your IP address
ip addr show | grep inet

# Dashboard will be accessible at:
# http://YOUR_IP:5000
```

For example: `http://192.168.1.50:5000`

### Basic Workflow

1. **Check Phone Status**
   - Go to Overview tab
   - Verify all phones are connected
   - Green = connected, Red = disconnected

2. **Select and Test a Phone**
   - Go to Phones tab
   - Click "Select" on a phone
   - Enter a task: "Open TikTok"
   - Click "Run Task"

3. **Generate Content**
   - Go to Generation tab
   - Enter a prompt: "viral tiktok dance, colorful, trending"
   - Select platform: TikTok
   - Click "Generate"
   - Watch progress in the queue

4. **Run Automation Pipeline**
   - Go to Automation tab
   - Configure settings (discovery limit, content to generate)
   - Click "Start Pipeline"
   - Monitor progress through 4 stages:
     - 🔍 Discovery
     - 📊 Analysis
     - 🎨 Generation
     - 📱 Posting

5. **Monitor Analytics**
   - Go to Analytics tab
   - View total generated content
   - Check success rate
   - See per-platform statistics

6. **Check Logs**
   - Go to Logs tab
   - Real-time system events
   - Error tracking
   - Task results

## API Endpoints

The dashboard exposes a REST API:

### Status
```bash
GET /api/status
# Returns: { total_phones, active_phones, queue_length, connected }
```

### Phones
```bash
GET /api/phones
# Returns: [ { name, device_id, status, description, tags }, ... ]

POST /api/phones/select
# Body: { phone_name: "phone_01" }
# Returns: { success, message }

POST /api/phones/run_task
# Body: { phone_name: "phone_01", task: "Open TikTok" }
# Returns: { success, result }
```

### Generation
```bash
POST /api/generation/start
# Body: { prompt, platform, type }
# Returns: { success, job_id }

GET /api/generation/queue
# Returns: [ { job_id, prompt, status, progress }, ... ]
```

### Automation
```bash
POST /api/automation/start
# Body: { discovery_limit, content_to_generate }
# Returns: { success, pipeline_id }

POST /api/automation/stop
# Returns: { success }
```

### Analytics
```bash
GET /api/analytics
# Returns: { total_generated, total_posted, success_rate, platforms }
```

## WebSocket Events

Real-time updates via SocketIO:

### Client → Server
```javascript
socket.emit('connect')  // Connect to dashboard
```

### Server → Client
```javascript
socket.on('phone_status_update', (data) => {
    // { phone_name, status }
})

socket.on('generation_progress', (data) => {
    // { job_id, progress, status }
})

socket.on('automation_status', (data) => {
    // { discovery_complete, analyzed, generated, posted }
})

socket.on('log_message', (data) => {
    // { level, message }
})

socket.on('analytics_update', (data) => {
    // { total_generated, total_posted, success_rate }
})
```

## Configuration

### Port Configuration

Change the port in `app.py`:

```python
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
```

### Security (Production)

For production use, add authentication:

```python
from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    # Implement your authentication
    return username == 'admin' and password == 'your-password'

@app.route('/api/phones')
@auth.login_required
def get_phones():
    # ...
```

### CORS Configuration

To allow access from other domains:

```python
from flask_cors import CORS

CORS(app, origins=['http://your-domain.com'])
```

## Troubleshooting

### Dashboard Won't Start

**Error**: `ModuleNotFoundError: No module named 'flask'`
```bash
pip install -r requirements.txt
```

### Phones Not Showing

1. Check phones are connected via ADB:
```bash
adb devices
```

2. Verify `phones_config.json` exists and is valid

3. Check phone status in Overview tab

### Generation Not Working

1. Ensure ComfyUI is running:
```bash
curl http://127.0.0.1:8188/system_stats
```

2. Check ComfyUI logs for errors

3. Verify models are downloaded (see `../COMFYUI_SETUP.md`)

### Real-time Updates Not Working

1. Check browser console for WebSocket errors
2. Ensure firewall allows port 5000
3. Try refreshing the page

### Phone Tasks Failing

1. Select the phone first (Phones tab → Select)
2. Check phone is connected (green status)
3. Verify task syntax is correct
4. Check logs tab for error details

## Advanced Usage

### Custom CSS Themes

Modify `static/css/dashboard.css` to change colors:

```css
:root {
    --primary: #6366f1;  /* Change to your brand color */
    --bg: #0f172a;       /* Background color */
    --success: #10b981;  /* Success indicators */
}
```

### Adding Custom Tabs

1. Add nav item in `templates/dashboard.html`:
```html
<button class="nav-item" data-tab="custom">Custom</button>
```

2. Add tab content:
```html
<div class="tab-content" id="custom-tab">
    <h2>Custom Tab</h2>
</div>
```

3. Add JavaScript handler in `static/js/dashboard.js`:
```javascript
if (tabName === 'custom') {
    loadCustomData();
}
```

### Embedding in Other Applications

The dashboard can be embedded using iframe:

```html
<iframe src="http://localhost:5000" width="100%" height="800px"></iframe>
```

## Performance

### Browser Requirements

- Modern browser (Chrome, Firefox, Safari, Edge)
- JavaScript enabled
- WebSocket support

### Resource Usage

- **Server**: ~100MB RAM, negligible CPU when idle
- **Browser**: ~50-100MB RAM per tab
- **Network**: ~1KB/s for real-time updates

### Scaling

For more than 20 phones, consider:

1. **Database**: Store phone configs in SQLite/PostgreSQL
2. **Redis**: Use Redis for real-time state management
3. **Load Balancer**: Run multiple dashboard instances
4. **Monitoring**: Add Prometheus metrics

## Integration Examples

### With Existing Scripts

```python
from dashboard.app import create_app, socketio

# Start dashboard in background thread
app = create_app()
thread = Thread(target=lambda: socketio.run(app, port=5000))
thread.daemon = True
thread.start()

# Continue with your automation script
automation.run_viral_pipeline()
```

### API Integration

```python
import requests

# Select phone via API
requests.post('http://localhost:5000/api/phones/select',
    json={'phone_name': 'phone_01'})

# Run task via API
response = requests.post('http://localhost:5000/api/phones/run_task',
    json={'phone_name': 'phone_01', 'task': 'Open TikTok'})

print(response.json())
```

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review logs in the Logs tab
3. Check browser console for JavaScript errors
4. See main project documentation in `../PHONE_POOL_GUIDE.md`

## Next Steps

- [ ] Add authentication for production use
- [ ] Implement phone control history
- [ ] Add content preview before posting
- [ ] Create analytics charts and graphs
- [ ] Add email/SMS notifications
- [ ] Implement scheduled automation
- [ ] Add phone screen mirroring

---

**🎨 Manage your viral content empire from one beautiful dashboard!**
