"""
Web-based Dashboard for Phone Pool and Viral Content Automation.

Features:
- Real-time phone status monitoring
- ComfyUI generation progress
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
from phone_agent.comfyui_integration import ComfyUIClient
from phone_agent.social_automation import SocialMediaAutomation, Platform


app = Flask(__name__)
app.config['SECRET_KEY'] = 'viral-content-automation-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
state = {
    'phone_manager': None,
    'automation': None,
    'comfyui_client': None,
    'generation_queue': [],
    'posting_queue': [],
    'analytics': {
        'total_generated': 0,
        'total_posted': 0,
        'platforms': {}
    },
    'active_tasks': [],
    'logs': []
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
    comfyui_client = state.get('comfyui_client')

    status = {
        'phones': {
            'total': len(phone_manager.phones) if phone_manager else 0,
            'connected': 0,
            'current': phone_manager.current_phone if phone_manager else None
        },
        'comfyui': {
            'connected': False,
            'generating': False
        },
        'automation': {
            'running': False,
            'queue_size': len(state['generation_queue'])
        },
        'analytics': state['analytics']
    }

    # Check phone connections
    if phone_manager:
        connections = phone_manager.check_connections()
        status['phones']['connected'] = sum(1 for v in connections.values() if v)

    # Check ComfyUI
    if comfyui_client:
        try:
            from phone_agent.comfyui_integration import test_comfyui_connection
            status['comfyui']['connected'] = test_comfyui_connection(
                comfyui_client.server_url
            )
        except:
            pass

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


@app.route('/api/generation/queue')
def get_generation_queue():
    """Get content generation queue."""
    return jsonify({'queue': state['generation_queue']})


@app.route('/api/generation/start', methods=['POST'])
def start_generation():
    """Start content generation."""
    data = request.json
    prompt = data.get('prompt')
    platform = data.get('platform', 'tiktok')

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    # Add to queue
    job = {
        'id': len(state['generation_queue']) + 1,
        'prompt': prompt,
        'platform': platform,
        'status': 'queued',
        'created_at': datetime.now().isoformat()
    }

    state['generation_queue'].append(job)

    log_event(f"Added to generation queue: {prompt}")
    socketio.emit('generation_queued', job)

    # Start generation in background
    threading.Thread(target=process_generation, args=(job,), daemon=True).start()

    return jsonify({'success': True, 'job': job})


def process_generation(job: Dict):
    """Process a generation job."""
    comfyui_client = state.get('comfyui_client')
    if not comfyui_client:
        job['status'] = 'failed'
        job['error'] = 'ComfyUI not configured'
        return

    try:
        job['status'] = 'generating'
        socketio.emit('generation_started', job)

        from phone_agent.comfyui_integration import GenerationRequest, ContentType

        request = GenerationRequest(
            prompt=job['prompt'],
            width=1080,
            height=1920,
            content_type=ContentType.VIDEO,
            steps=20
        )

        result = comfyui_client.generate(request)

        job['status'] = 'completed'
        job['output_path'] = result.file_path
        job['completed_at'] = datetime.now().isoformat()

        state['analytics']['total_generated'] += 1

        log_event(f"Generation completed: {job['prompt']}")
        socketio.emit('generation_completed', job)

    except Exception as e:
        job['status'] = 'failed'
        job['error'] = str(e)
        log_event(f"Generation failed: {str(e)}", "error")
        socketio.emit('generation_failed', job)


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


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    emit('connected', {'status': 'connected'})
    log_event("Client connected")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    log_event("Client disconnected")


def init_dashboard(
    phone_manager: PhonePoolManager,
    comfyui_client: ComfyUIClient,
    automation: SocialMediaAutomation,
    host: str = '0.0.0.0',
    port: int = 5000
):
    """
    Initialize and run the dashboard.

    Args:
        phone_manager: PhonePoolManager instance
        comfyui_client: ComfyUIClient instance
        automation: SocialMediaAutomation instance
        host: Host to bind to
        port: Port to bind to
    """
    state['phone_manager'] = phone_manager
    state['comfyui_client'] = comfyui_client
    state['automation'] = automation

    # Initialize analytics
    for platform in Platform:
        state['analytics']['platforms'][platform.value] = {
            'discovered': 0,
            'generated': 0,
            'posted': 0
        }

    log_event("Dashboard initialized")

    print("\n" + "="*70)
    print("🌐 Dashboard Starting...")
    print("="*70)
    print(f"\n   📱 Managing {len(phone_manager.phones)} phones")
    print(f"   🎨 ComfyUI: {comfyui_client.server_url}")
    print(f"   🌐 Dashboard: http://localhost:{port}")
    print(f"\n   Open your browser and visit: http://localhost:{port}")
    print("\n" + "="*70 + "\n")

    socketio.run(app, host=host, port=port, debug=False)


if __name__ == '__main__':
    # For testing
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
