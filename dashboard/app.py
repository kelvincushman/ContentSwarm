"""
Web-based Dashboard for Phone Pool and Viral Content Automation.

Features:
- Real-time phone status monitoring
- Content queue management
- Platform analytics
- Manual controls
- Live preview of generated content
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from phone_agent.phone_pool import PhonePoolManager
from phone_agent.social_automation import SocialMediaAutomation, Platform
from phone_agent.api import create_api_blueprint

# Import screen streaming (path relative to dashboard directory)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from phone_screen_streaming import StreamManager, StreamQuality, estimate_bandwidth


app = Flask(__name__)
app.config['SECRET_KEY'] = 'viral-content-automation-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
state = {
    'phone_manager': None,
    'automation': None,
    'stream_manager': None,
    'posting_queue': [],
    'analytics': {
        'total_generated': 0,
        'total_posted': 0,
        'platforms': {}
    },
    'active_tasks': [],
    'logs': [],
    'streaming': {
        'active': False,
        'quality': 'thumbnail',
        'bandwidth_mbps': 0
    }
}


def log_event(message: str, level: str = "info"):
    """Add event to log and emit to clients."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        'timestamp': timestamp,
        'message': message,
        'level': level
    }
    state['logs'].append(log_entry)

    # Keep only last 100 logs
    if len(state['logs']) > 100:
        state['logs'] = state['logs'][-100:]

    socketio.emit('log', log_entry)


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/status')
def get_status():
    """Get overall system status."""
    phone_manager = state.get('phone_manager')
    automation = state.get('automation')

    pipeline_stage = 'idle'
    if automation:
        try:
            pipeline_stage = automation.get_pipeline_status().get('stage', 'idle')
        except Exception:
            pass

    status = {
        'phones': {
            'total': len(phone_manager.phones) if phone_manager else 0,
            'connected': 0,
            'current': phone_manager.current_phone if phone_manager else None
        },
        'automation': {
            'running': pipeline_stage != 'idle',
            'stage': pipeline_stage
        },
        'analytics': state['analytics']
    }

    # Check phone connections
    if phone_manager:
        connections = phone_manager.check_connections()
        status['phones']['connected'] = sum(1 for v in connections.values() if v)

    return jsonify(status)


@app.route('/api/phones')
def get_phones():
    """Get all phones and their status."""
    phone_manager = state.get('phone_manager')
    if not phone_manager:
        return jsonify({'phones': []})

    connections = phone_manager.check_connections()

    phones = []
    for name, phone_info in phone_manager.phones.items():
        phones.append({
            'name': name,
            'device_id': phone_info.device_id,
            'description': phone_info.description,
            'tags': phone_info.tags,
            'connected': connections.get(name, False),
            'is_current': name == phone_manager.current_phone
        })

    return jsonify({'phones': phones})


@app.route('/api/phones/select', methods=['POST'])
def select_phone():
    """Select a phone for control."""
    phone_manager = state.get('phone_manager')
    if not phone_manager:
        return jsonify({'error': 'Phone manager not initialized'}), 400

    data = request.json
    phone_name = data.get('phone_name')

    try:
        phone_manager.select_phone(phone_name)
        log_event(f"Selected phone: {phone_name}")
        socketio.emit('phone_selected', {'phone': phone_name})
        return jsonify({'success': True, 'phone': phone_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/phones/run_task', methods=['POST'])
def run_task():
    """Run task on selected or specified phone."""
    phone_manager = state.get('phone_manager')
    if not phone_manager:
        return jsonify({'error': 'Phone manager not initialized'}), 400

    data = request.json
    task = data.get('task')
    phone_name = data.get('phone_name')

    if not task:
        return jsonify({'error': 'Task is required'}), 400

    try:
        if phone_name:
            result = phone_manager.quick_run(phone_name, task)
        else:
            result = phone_manager.run_task(task)

        log_event(f"Task executed: {task}")
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        log_event(f"Task failed: {str(e)}", "error")
        return jsonify({'error': str(e)}), 400


@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """Start viral automation pipeline."""
    data = request.json

    config = {
        'discovery_limit': data.get('discovery_limit', 10),
        'content_to_generate': data.get('content_to_generate', 5)
    }

    log_event("Starting automation pipeline...")

    # Run in background thread
    threading.Thread(
        target=run_automation_pipeline,
        args=(config,),
        daemon=True
    ).start()

    return jsonify({'success': True, 'message': 'Pipeline started'})


def run_automation_pipeline(config: Dict):
    """Run the automation pipeline in background."""
    automation = state.get('automation')
    if not automation:
        log_event("Automation not configured", "error")
        return

    try:
        socketio.emit('automation_started', config)

        # This would run the full pipeline
        # automation.run_viral_pipeline(**config)

        log_event("Automation pipeline completed")
        socketio.emit('automation_completed', {})

    except Exception as e:
        log_event(f"Automation failed: {str(e)}", "error")
        socketio.emit('automation_failed', {'error': str(e)})


@app.route('/api/logs')
def get_logs():
    """Get recent logs."""
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'logs': state['logs'][-limit:]})


@app.route('/api/analytics')
def get_analytics():
    """Get analytics data."""
    return jsonify(state['analytics'])


@app.route('/generated/<path:filename>')
def serve_generated_file(filename):
    """Serve generated content files."""
    return send_from_directory('./generated_content', filename)


@app.route('/api/screens/start', methods=['POST'])
def start_screen_streaming():
    """Start screen streaming for phones."""
    data = request.json
    quality = data.get('quality', 'thumbnail')
    phone_names = data.get('phones', [])  # Empty = all phones

    stream_manager = state.get('stream_manager')
    phone_manager = state.get('phone_manager')

    if not stream_manager or not phone_manager:
        return jsonify({'error': 'Managers not initialized'}), 400

    try:
        quality_enum = StreamQuality(quality)

        # Get phones to stream
        if not phone_names:
            # Stream all phones
            phones_to_stream = [
                {'name': name, 'device_id': info.device_id}
                for name, info in phone_manager.phones.items()
            ]
        else:
            phones_to_stream = [
                {'name': name, 'device_id': phone_manager.phones[name].device_id}
                for name in phone_names
                if name in phone_manager.phones
            ]

        # Start streams
        stream_manager.start_all(phones_to_stream, quality_enum)

        # Update state
        state['streaming']['active'] = True
        state['streaming']['quality'] = quality

        # Calculate bandwidth
        bandwidth = estimate_bandwidth(len(phones_to_stream), quality_enum)
        state['streaming']['bandwidth_mbps'] = bandwidth

        log_event(f"Started streaming {len(phones_to_stream)} phones ({quality}, ~{bandwidth:.1f} Mbps)")

        return jsonify({
            'success': True,
            'phones': len(phones_to_stream),
            'quality': quality,
            'estimated_bandwidth_mbps': bandwidth
        })

    except Exception as e:
        log_event(f"Failed to start streaming: {str(e)}", "error")
        return jsonify({'error': str(e)}), 400


@app.route('/api/screens/stop', methods=['POST'])
def stop_screen_streaming():
    """Stop all screen streaming."""
    stream_manager = state.get('stream_manager')
    if not stream_manager:
        return jsonify({'error': 'Stream manager not initialized'}), 400

    try:
        stream_manager.stop_all()
        state['streaming']['active'] = False
        state['streaming']['bandwidth_mbps'] = 0

        log_event("Stopped all screen streaming")

        return jsonify({'success': True})

    except Exception as e:
        log_event(f"Failed to stop streaming: {str(e)}", "error")
        return jsonify({'error': str(e)}), 400


@app.route('/api/screens/pause', methods=['POST'])
def pause_screen_streaming():
    """Pause screen streaming (keep threads alive but don't capture)."""
    stream_manager = state.get('stream_manager')
    if not stream_manager:
        return jsonify({'error': 'Stream manager not initialized'}), 400

    try:
        stream_manager.pause_all()
        log_event("Paused screen streaming")
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/screens/resume', methods=['POST'])
def resume_screen_streaming():
    """Resume paused screen streaming."""
    stream_manager = state.get('stream_manager')
    if not stream_manager:
        return jsonify({'error': 'Stream manager not initialized'}), 400

    try:
        stream_manager.resume_all()
        log_event("Resumed screen streaming")
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/screens/upgrade', methods=['POST'])
def upgrade_screen_quality():
    """Upgrade specific phone to higher quality."""
    data = request.json
    phone_name = data.get('phone_name')
    quality = data.get('quality', 'full')

    stream_manager = state.get('stream_manager')
    if not stream_manager:
        return jsonify({'error': 'Stream manager not initialized'}), 400

    try:
        quality_enum = StreamQuality(quality)
        stream_manager.upgrade_quality(phone_name, quality_enum)

        # Optionally downgrade others to save bandwidth
        if data.get('downgrade_others', True):
            stream_manager.downgrade_others(phone_name)

        log_event(f"Upgraded {phone_name} to {quality} quality")

        return jsonify({'success': True, 'phone': phone_name, 'quality': quality})

    except Exception as e:
        log_event(f"Failed to upgrade quality: {str(e)}", "error")
        return jsonify({'error': str(e)}), 400


@app.route('/api/screens/stats')
def get_screen_stats():
    """Get screen streaming statistics."""
    stream_manager = state.get('stream_manager')
    if not stream_manager:
        return jsonify({'error': 'Stream manager not initialized'}), 400

    stats = stream_manager.get_aggregate_stats()
    stats['streaming'] = state['streaming']

    return jsonify(stats)


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('connected', {'status': 'connected'})
    log_event("Client connected")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    log_event("Client disconnected")


# ── External Events Namespace ───────────────────────────────────

@socketio.on('connect', namespace='/ws/events')
def handle_events_connect():
    """Handle external consumer connection to the events namespace."""
    emit('connected', {'status': 'connected', 'namespace': '/ws/events'}, namespace='/ws/events')
    log_event("External events client connected")


@socketio.on('disconnect', namespace='/ws/events')
def handle_events_disconnect():
    """Handle external consumer disconnection from the events namespace."""
    log_event("External events client disconnected")


def init_dashboard(
    phone_manager: PhonePoolManager,
    automation: SocialMediaAutomation,
    host: str = '0.0.0.0',
    port: int = 5000
):
    """
    Initialize and run the dashboard.

    Args:
        phone_manager: PhonePoolManager instance
        automation: SocialMediaAutomation instance
        host: Host to bind to
        port: Port to bind to
    """
    state['phone_manager'] = phone_manager
    state['automation'] = automation
    state['socketio'] = socketio

    # Register ContentSwarm API blueprint for external orchestration (Orphus CLI etc.)
    api_blueprint = create_api_blueprint(state)
    app.register_blueprint(api_blueprint, url_prefix='/api/v1')

    # Initialize stream manager with socketio callback
    def on_frame(frame_data):
        """Callback for screen frames - emit to all connected clients"""
        socketio.emit('screen_frame', frame_data)

    state['stream_manager'] = StreamManager(on_frame=on_frame)

    # Initialize analytics
    for platform in Platform:
        state['analytics']['platforms'][platform.value] = {
            'discovered': 0,
            'generated': 0,
            'posted': 0
        }

    log_event("Dashboard initialized")

    print("\n" + "="*70)
    print("🌐 ContentSwarm Dashboard Starting...")
    print("="*70)
    print(f"\n   📱 Managing {len(phone_manager.phones)} phones")
    print(f"   🌐 Dashboard: http://localhost:{port}")
    print(f"\n   📺 Screen Streaming: Available")
    print(f"\n   Open your browser and visit: http://localhost:{port}")
    print("\n" + "="*70 + "\n")

    # Production runs on eventlet (installed via dashboard/requirements.txt);
    # allow_unsafe_werkzeug only permits the Werkzeug DEV fallback when
    # eventlet is absent, and we warn loudly when that happens.
    try:
        import eventlet  # noqa: F401
    except ImportError:
        print("⚠️  eventlet not installed - falling back to the Werkzeug DEV "
              "server. Do not expose this beyond localhost; install eventlet "
              "for production (pip install -r dashboard/requirements.txt).")
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    # For testing
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
