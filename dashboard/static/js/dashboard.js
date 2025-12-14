// Dashboard JavaScript - Viral Content Automation

// SocketIO Connection
const socket = io();

// State
let currentPhone = null;
let phones = [];
let automationRunning = false;
let generationQueue = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    setupSocketListeners();
    setupEventListeners();
    startStatusUpdates();
});

// Initialize application
async function initializeApp() {
    await loadPhones();
    await loadStatus();
    showTab('overview');
}

// Setup SocketIO listeners
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
        showToast('Connected to dashboard', 'success');
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        showToast('Disconnected from dashboard', 'error');
    });

    socket.on('phone_status_update', (data) => {
        updatePhoneStatus(data);
    });

    socket.on('generation_progress', (data) => {
        updateGenerationProgress(data);
    });

    socket.on('automation_status', (data) => {
        updateAutomationStatus(data);
    });

    socket.on('log_message', (data) => {
        addLogEntry(data);
    });

    socket.on('analytics_update', (data) => {
        updateAnalytics(data);
    });
}

// Setup event listeners
function setupEventListeners() {
    // Nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const tabName = e.target.dataset.tab;
            showTab(tabName);
        });
    });

    // Phone selection
    const phoneSelect = document.getElementById('phone-select');
    if (phoneSelect) {
        phoneSelect.addEventListener('change', (e) => {
            selectPhone(e.target.value);
        });
    }
}

// Tab Navigation
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Remove active from nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Show selected tab
    const tab = document.getElementById(`${tabName}-tab`);
    if (tab) {
        tab.classList.add('active');
    }

    // Activate nav item
    const navItem = document.querySelector(`[data-tab="${tabName}"]`);
    if (navItem) {
        navItem.classList.add('active');
    }

    // Load tab-specific data
    if (tabName === 'phones') {
        renderPhoneTable();
    } else if (tabName === 'generation') {
        loadGenerationQueue();
    } else if (tabName === 'analytics') {
        loadAnalytics();
    }
}

// Load system status
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update header stats
        updateStat('total-phones', data.total_phones || 0);
        updateStat('active-phones', data.active_phones || 0);
        updateStat('queue-length', data.queue_length || 0);

        // Update status indicator
        const statusIndicator = document.querySelector('.status-indicator');
        if (data.connected && statusIndicator) {
            statusIndicator.classList.add('connected');
            statusIndicator.querySelector('span').textContent = 'Connected';
        }

    } catch (error) {
        console.error('Failed to load status:', error);
        showToast('Failed to load status', 'error');
    }
}

// Load phones
async function loadPhones() {
    try {
        const response = await fetch('/api/phones');
        phones = await response.json();

        // Update phone select dropdown
        const phoneSelect = document.getElementById('phone-select');
        if (phoneSelect) {
            phoneSelect.innerHTML = '<option value="">Select phone...</option>';
            phones.forEach(phone => {
                const option = document.createElement('option');
                option.value = phone.name;
                option.textContent = `${phone.name} - ${phone.description}`;
                phoneSelect.appendChild(option);
            });
        }

        // Update overview phone grid
        renderPhoneGrid();

    } catch (error) {
        console.error('Failed to load phones:', error);
        showToast('Failed to load phones', 'error');
    }
}

// Render phone grid (overview)
function renderPhoneGrid() {
    const grid = document.getElementById('phone-grid');
    if (!grid) return;

    grid.innerHTML = '';

    phones.forEach(phone => {
        const item = document.createElement('div');
        item.className = 'phone-item';
        if (phone.status === 'connected') {
            item.classList.add('connected');
        }
        if (phone.name === currentPhone) {
            item.classList.add('active');
        }

        item.innerHTML = `
            <div>${phone.name}</div>
            <small>${phone.status || 'unknown'}</small>
        `;

        item.addEventListener('click', () => selectPhone(phone.name));

        grid.appendChild(item);
    });
}

// Render phone table (phones tab)
function renderPhoneTable() {
    const tbody = document.querySelector('.phone-table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    phones.forEach(phone => {
        const row = document.createElement('tr');

        const statusClass = phone.status === 'connected' ? 'badge-success' : 'badge-danger';
        const statusText = phone.status === 'connected' ? 'Connected' : 'Disconnected';

        row.innerHTML = `
            <td>${phone.name}</td>
            <td>${phone.device_id}</td>
            <td>${phone.description}</td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>${phone.tags ? phone.tags.join(', ') : '-'}</td>
            <td>
                <button class="btn btn-primary" onclick="selectPhone('${phone.name}')">
                    Select
                </button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

// Select phone
async function selectPhone(phoneName) {
    if (!phoneName) return;

    try {
        const response = await fetch('/api/phones/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_name: phoneName })
        });

        const data = await response.json();

        if (data.success) {
            currentPhone = phoneName;
            showToast(`Selected ${phoneName}`, 'success');

            // Update UI
            renderPhoneGrid();

            // Update phone select dropdown
            const phoneSelect = document.getElementById('phone-select');
            if (phoneSelect) {
                phoneSelect.value = phoneName;
            }

            // Update current phone display
            const currentPhoneSpan = document.getElementById('current-phone');
            if (currentPhoneSpan) {
                currentPhoneSpan.textContent = phoneName;
            }
        } else {
            showToast(`Failed to select ${phoneName}: ${data.error}`, 'error');
        }

    } catch (error) {
        console.error('Failed to select phone:', error);
        showToast('Failed to select phone', 'error');
    }
}

// Run task on current phone
async function runTask() {
    const taskInput = document.getElementById('task-input');
    const task = taskInput ? taskInput.value.trim() : '';

    if (!task) {
        showToast('Please enter a task', 'error');
        return;
    }

    if (!currentPhone) {
        showToast('Please select a phone first', 'error');
        return;
    }

    try {
        const button = document.querySelector('#phones-tab .btn-primary');
        if (button) {
            button.disabled = true;
            button.textContent = 'Running...';
        }

        const response = await fetch('/api/phones/run_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone_name: currentPhone,
                task: task
            })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Task completed successfully', 'success');
            // Show result in a modal or log
            addLogEntry({
                level: 'info',
                message: `Task result: ${data.result}`
            });
        } else {
            showToast(`Task failed: ${data.error}`, 'error');
        }

    } catch (error) {
        console.error('Failed to run task:', error);
        showToast('Failed to run task', 'error');
    } finally {
        const button = document.querySelector('#phones-tab .btn-primary');
        if (button) {
            button.disabled = false;
            button.textContent = '▶ Run Task';
        }
    }
}

// Generate content with ComfyUI
async function generateContent() {
    const prompt = document.getElementById('generation-prompt')?.value.trim();
    const platform = document.getElementById('generation-platform')?.value;

    if (!prompt) {
        showToast('Please enter a prompt', 'error');
        return;
    }

    try {
        const button = document.querySelector('#generation-tab .btn-success');
        if (button) {
            button.disabled = true;
            button.textContent = 'Generating...';
        }

        const response = await fetch('/api/generation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt,
                platform: platform,
                type: 'image'  // or 'video' based on selection
            })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Generation started', 'success');
            // Add to queue display
            addToGenerationQueue(data.job_id, prompt);
        } else {
            showToast(`Generation failed: ${data.error}`, 'error');
        }

    } catch (error) {
        console.error('Failed to start generation:', error);
        showToast('Failed to start generation', 'error');
    } finally {
        const button = document.querySelector('#generation-tab .btn-success');
        if (button) {
            button.disabled = false;
            button.textContent = '🎨 Generate';
        }
    }
}

// Load generation queue
async function loadGenerationQueue() {
    try {
        const response = await fetch('/api/generation/queue');
        const queue = await response.json();

        const queueList = document.getElementById('generation-queue');
        if (!queueList) return;

        queueList.innerHTML = '';

        if (queue.length === 0) {
            queueList.innerHTML = '<div class="empty-state">No items in queue</div>';
            return;
        }

        queue.forEach(item => {
            const queueItem = document.createElement('div');
            queueItem.className = `queue-item ${item.status}`;
            queueItem.innerHTML = `
                <div class="queue-item-header">
                    <strong>${item.prompt}</strong>
                    <span class="badge badge-${item.status === 'completed' ? 'success' : 'warning'}">
                        ${item.status}
                    </span>
                </div>
                <div class="queue-item-meta">
                    <small>${item.type} • ${item.platform}</small>
                    ${item.progress ? `<small>${item.progress}%</small>` : ''}
                </div>
            `;
            queueList.appendChild(queueItem);
        });

    } catch (error) {
        console.error('Failed to load queue:', error);
    }
}

// Add to generation queue display
function addToGenerationQueue(jobId, prompt) {
    const queueList = document.getElementById('generation-queue');
    if (!queueList) return;

    const queueItem = document.createElement('div');
    queueItem.className = 'queue-item generating';
    queueItem.dataset.jobId = jobId;
    queueItem.innerHTML = `
        <div class="queue-item-header">
            <strong>${prompt}</strong>
            <span class="badge badge-warning">Generating</span>
        </div>
        <div class="queue-item-meta">
            <small>Progress: <span class="progress-text">0%</span></small>
        </div>
    `;

    queueList.insertBefore(queueItem, queueList.firstChild);
}

// Update generation progress
function updateGenerationProgress(data) {
    const queueItem = document.querySelector(`[data-job-id="${data.job_id}"]`);
    if (!queueItem) return;

    const progressText = queueItem.querySelector('.progress-text');
    if (progressText) {
        progressText.textContent = `${data.progress}%`;
    }

    if (data.status === 'completed') {
        queueItem.className = 'queue-item completed';
        const badge = queueItem.querySelector('.badge');
        if (badge) {
            badge.className = 'badge badge-success';
            badge.textContent = 'Completed';
        }
    } else if (data.status === 'failed') {
        queueItem.className = 'queue-item failed';
        const badge = queueItem.querySelector('.badge');
        if (badge) {
            badge.className = 'badge badge-danger';
            badge.textContent = 'Failed';
        }
    }
}

// Start automation pipeline
async function startAutomation() {
    try {
        const button = document.querySelector('#automation-tab .btn-success');
        if (button) {
            button.disabled = true;
            button.textContent = 'Starting...';
        }

        const response = await fetch('/api/automation/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                discovery_limit: 10,
                content_to_generate: 3
            })
        });

        const data = await response.json();

        if (data.success) {
            automationRunning = true;
            showToast('Automation pipeline started', 'success');
            updateAutomationButton(true);
        } else {
            showToast(`Failed to start automation: ${data.error}`, 'error');
        }

    } catch (error) {
        console.error('Failed to start automation:', error);
        showToast('Failed to start automation', 'error');
    } finally {
        const button = document.querySelector('#automation-tab .btn-success');
        if (button) {
            button.disabled = false;
            button.textContent = '▶ Start Pipeline';
        }
    }
}

// Stop automation pipeline
async function stopAutomation() {
    try {
        const response = await fetch('/api/automation/stop', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            automationRunning = false;
            showToast('Automation pipeline stopped', 'success');
            updateAutomationButton(false);
        }

    } catch (error) {
        console.error('Failed to stop automation:', error);
        showToast('Failed to stop automation', 'error');
    }
}

// Update automation status
function updateAutomationStatus(data) {
    const statusDiv = document.getElementById('automation-status');
    if (!statusDiv) return;

    statusDiv.innerHTML = `
        <div class="progress-container">
            <div class="progress-step">
                <div class="step-icon">${data.discovery_complete ? '✅' : '⏳'}</div>
                <div class="step-label">Discovery</div>
                <div class="step-status">${data.discovered || 0} items</div>
            </div>
            <div class="progress-step">
                <div class="step-icon">${data.analysis_complete ? '✅' : '⏳'}</div>
                <div class="step-label">Analysis</div>
                <div class="step-status">${data.analyzed || 0} items</div>
            </div>
            <div class="progress-step">
                <div class="step-icon">${data.generation_complete ? '✅' : '⏳'}</div>
                <div class="step-label">Generation</div>
                <div class="step-status">${data.generated || 0} items</div>
            </div>
            <div class="progress-step">
                <div class="step-icon">${data.posting_complete ? '✅' : '⏳'}</div>
                <div class="step-label">Posting</div>
                <div class="step-status">${data.posted || 0} items</div>
            </div>
        </div>
    `;
}

// Update automation button
function updateAutomationButton(running) {
    const button = document.querySelector('#automation-tab .btn-success');
    if (!button) return;

    if (running) {
        button.textContent = '⏹ Stop Pipeline';
        button.onclick = stopAutomation;
    } else {
        button.textContent = '▶ Start Pipeline';
        button.onclick = startAutomation;
    }
}

// Load analytics
async function loadAnalytics() {
    try {
        const response = await fetch('/api/analytics');
        const data = await response.json();

        renderAnalytics(data);

    } catch (error) {
        console.error('Failed to load analytics:', error);
    }
}

// Render analytics
function renderAnalytics(data) {
    // Stats grid
    const statsGrid = document.querySelector('#analytics-tab .stats-grid');
    if (statsGrid) {
        statsGrid.innerHTML = `
            <div class="stat-card">
                <div class="stat-label">Total Generated</div>
                <div class="stat-number">${data.total_generated || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Posted</div>
                <div class="stat-number">${data.total_posted || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-number">${data.success_rate || 0}%</div>
            </div>
        `;
    }

    // Platform stats
    const platformStats = document.querySelector('#analytics-tab .platform-stats');
    if (platformStats && data.platforms) {
        platformStats.innerHTML = '';
        Object.entries(data.platforms).forEach(([platform, stats]) => {
            const item = document.createElement('div');
            item.className = 'platform-stat';
            item.innerHTML = `
                <strong>${platform}</strong>
                <span>${stats.posts || 0} posts</span>
            `;
            platformStats.appendChild(item);
        });
    }
}

// Update analytics (from SocketIO)
function updateAnalytics(data) {
    renderAnalytics(data);
}

// Add log entry
function addLogEntry(data) {
    const logsList = document.querySelector('.logs-list');
    if (!logsList) return;

    const entry = document.createElement('div');
    entry.className = `log-entry ${data.level || 'info'}`;

    const timestamp = new Date().toLocaleTimeString();
    entry.innerHTML = `
        <span class="log-timestamp">${timestamp}</span>
        <span>${data.message}</span>
    `;

    logsList.insertBefore(entry, logsList.firstChild);

    // Keep only last 100 entries
    while (logsList.children.length > 100) {
        logsList.removeChild(logsList.lastChild);
    }
}

// Update phone status (from SocketIO)
function updatePhoneStatus(data) {
    const phone = phones.find(p => p.name === data.phone_name);
    if (phone) {
        phone.status = data.status;
        renderPhoneGrid();
        renderPhoneTable();
    }
}

// Update stat display
function updateStat(statId, value) {
    const elem = document.getElementById(statId);
    if (elem) {
        elem.textContent = value;
    }
}

// Start periodic status updates
function startStatusUpdates() {
    // Update status every 5 seconds
    setInterval(() => {
        loadStatus();
    }, 5000);

    // Update phones every 10 seconds
    setInterval(() => {
        loadPhones();
    }, 10000);
}

// Show toast notification
function showToast(message, type = 'info') {
    const container = document.querySelector('.toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;

    container.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            container.removeChild(toast);
        }, 300);
    }, 3000);
}

// Add slideOut animation to CSS if not present
const style = document.createElement('style');
style.textContent = `
@keyframes slideOut {
    from {
        transform: translateX(0);
        opacity: 1;
    }
    to {
        transform: translateX(400px);
        opacity: 0;
    }
}
`;
document.head.appendChild(style);

// ===== SCREEN STREAMING FUNCTIONS =====

// Screen streaming state
let screenStreamingActive = false;
let selectedScreenPhone = null;
let phoneScreenStates = {}; // Track which phones have streaming enabled
let frameStats = { count: 0, lastTime: Date.now() };

// Initialize phone screen items when phones are loaded
function initializePhoneScreens() {
    const grid = document.getElementById('screens-grid');
    if (!grid) return;

    grid.innerHTML = '';

    phones.forEach(phone => {
        // Initialize phone state (enabled by default)
        phoneScreenStates[phone.name] = true;

        const item = document.createElement('div');
        item.className = 'screen-item';
        item.dataset.phoneName = phone.name;

        item.innerHTML = `
            <div class="screen-toggle" onclick="event.stopPropagation(); togglePhoneStream('${phone.name}')">
                <div class="toggle-switch active" id="toggle-${phone.name}">
                    <div class="toggle-slider"></div>
                </div>
            </div>
            <canvas class="screen-canvas" id="screen-${phone.name}" width="240" height="520"></canvas>
            <div class="screen-label">${phone.name}</div>
        `;

        item.addEventListener('click', () => selectScreenForViewing(phone.name));

        grid.appendChild(item);
    });
}

// Toggle individual phone stream on/off
function togglePhoneStream(phoneName) {
    const toggle = document.getElementById(`toggle-${phoneName}`);
    const item = document.querySelector(`[data-phone-name="${phoneName}"]`);

    phoneScreenStates[phoneName] = !phoneScreenStates[phoneName];

    if (phoneScreenStates[phoneName]) {
        toggle.classList.add('active');
        item.classList.remove('disabled');
    } else {
        toggle.classList.remove('active');
        item.classList.add('disabled');

        // Clear canvas
        const canvas = document.getElementById(`screen-${phoneName}`);
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    updateActiveStreamsCount();
}

// Toggle all phones on/off
function toggleAllPhones() {
    const allEnabled = Object.values(phoneScreenStates).every(s => s);
    const newState = !allEnabled;

    Object.keys(phoneScreenStates).forEach(phoneName => {
        phoneScreenStates[phoneName] = newState;

        const toggle = document.getElementById(`toggle-${phoneName}`);
        const item = document.querySelector(`[data-phone-name="${phoneName}"]`);

        if (newState) {
            toggle?.classList.add('active');
            item?.classList.remove('disabled');
        } else {
            toggle?.classList.remove('active');
            item?.classList.add('disabled');
        }
    });

    updateActiveStreamsCount();
}

// Adjust grid size with slider
function adjustGridSize(size) {
    const grid = document.getElementById('screens-grid');
    const label = document.getElementById('grid-size-value');

    if (grid) {
        grid.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
    }

    if (label) {
        label.textContent = `${size}px`;
    }
}

// Start screen streaming
async function startStreaming() {
    const quality = document.getElementById('stream-quality')?.value || 'thumbnail';

    try {
        const response = await fetch('/api/screens/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quality: quality })
        });

        const data = await response.json();

        if (data.success) {
            screenStreamingActive = true;
            showToast(`Started streaming ${data.phones} phones (${quality})`, 'success');

            // Update UI
            document.getElementById('start-streaming-btn').style.display = 'none';
            document.getElementById('stop-streaming-btn').style.display = 'inline-block';
            document.getElementById('pause-streaming-btn').style.display = 'inline-block';

            // Update bandwidth display
            updateStat('bandwidth-usage', `${data.estimated_bandwidth_mbps.toFixed(1)} Mbps`);

            // Initialize phone screens if not already done
            if (!phones.length) {
                await loadPhones();
            }
            initializePhoneScreens();

        } else {
            showToast(`Failed to start streaming: ${data.error}`, 'error');
        }

    } catch (error) {
        console.error('Failed to start streaming:', error);
        showToast('Failed to start streaming', 'error');
    }
}

// Stop screen streaming
async function stopStreaming() {
    try {
        const response = await fetch('/api/screens/stop', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            screenStreamingActive = false;
            selectedScreenPhone = null;
            showToast('Stopped streaming', 'success');

            // Update UI
            document.getElementById('start-streaming-btn').style.display = 'inline-block';
            document.getElementById('stop-streaming-btn').style.display = 'none';
            document.getElementById('pause-streaming-btn').style.display = 'none';

            // Clear stats
            updateStat('bandwidth-usage', '0 Mbps');
            updateStat('stream-fps', '0');
            updateStat('active-streams', '0');

            // Clear all canvases
            phones.forEach(phone => {
                const canvas = document.getElementById(`screen-${phone.name}`);
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                }
            });

            // Clear viewer
            const viewer = document.getElementById('screen-viewer');
            if (viewer) {
                viewer.innerHTML = `
                    <div class="empty-state">
                        <p>Click a phone in the grid to view full screen</p>
                        <p class="hint">Start streaming to see phone screens</p>
                    </div>
                `;
            }
        }

    } catch (error) {
        console.error('Failed to stop streaming:', error);
        showToast('Failed to stop streaming', 'error');
    }
}

// Pause streaming
async function pauseStreaming() {
    try {
        const response = await fetch('/api/screens/pause', {
            method: 'POST'
        });

        if (response.ok) {
            showToast('Streaming paused', 'success');
            document.getElementById('pause-streaming-btn').textContent = '▶ Resume';
            document.getElementById('pause-streaming-btn').onclick = resumeStreaming;
        }

    } catch (error) {
        console.error('Failed to pause streaming:', error);
    }
}

// Resume streaming
async function resumeStreaming() {
    try {
        const response = await fetch('/api/screens/resume', {
            method: 'POST'
        });

        if (response.ok) {
            showToast('Streaming resumed', 'success');
            document.getElementById('pause-streaming-btn').textContent = '⏸ Pause';
            document.getElementById('pause-streaming-btn').onclick = pauseStreaming;
        }

    } catch (error) {
        console.error('Failed to resume streaming:', error);
    }
}

// Select phone for enlarged viewing
async function selectScreenForViewing(phoneName) {
    if (!screenStreamingActive) {
        showToast('Start streaming first', 'error');
        return;
    }

    if (!phoneScreenStates[phoneName]) {
        showToast('This phone stream is disabled', 'error');
        return;
    }

    selectedScreenPhone = phoneName;

    // Update UI - highlight selected item
    document.querySelectorAll('.screen-item').forEach(item => {
        item.classList.remove('selected');
    });
    document.querySelector(`[data-phone-name="${phoneName}"]`)?.classList.add('selected');

    // Update selected phone name
    document.getElementById('selected-phone-name').textContent = phoneName;

    // Upgrade to full quality
    try {
        const response = await fetch('/api/screens/upgrade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone_name: phoneName,
                quality: 'full',
                downgrade_others: true
            })
        });

        if (response.ok) {
            showToast(`Viewing ${phoneName} in full quality`, 'success');
        }

    } catch (error) {
        console.error('Failed to upgrade quality:', error);
    }
}

// Handle incoming screen frames
socket.on('screen_frame', (data) => {
    if (!screenStreamingActive) return;

    const phoneName = extractPhoneName(data.device_id);
    if (!phoneName || !phoneScreenStates[phoneName]) return;

    // Update FPS counter
    frameStats.count++;
    const now = Date.now();
    if (now - frameStats.lastTime >= 1000) {
        updateStat('stream-fps', frameStats.count);
        frameStats.count = 0;
        frameStats.lastTime = now;
    }

    // Render to thumbnail canvas
    const canvas = document.getElementById(`screen-${phoneName}`);
    if (canvas) {
        renderFrameToCanvas(canvas, data.frame);
    }

    // If this is the selected phone, also update the enlarged viewer
    if (phoneName === selectedScreenPhone) {
        updateEnlargedViewer(data.frame);
    }
});

// Extract phone name from device ID
function extractPhoneName(deviceId) {
    const phone = phones.find(p => p.device_id === deviceId);
    return phone ? phone.name : null;
}

// Render frame to canvas
function renderFrameToCanvas(canvas, frameBase64) {
    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };

    img.onerror = () => {
        console.error('Failed to load frame image');
    };

    img.src = 'data:image/jpeg;base64,' + frameBase64;
}

// Update enlarged viewer
function updateEnlargedViewer(frameBase64) {
    const viewer = document.getElementById('screen-viewer');
    if (!viewer) return;

    // Create or update canvas
    let canvas = viewer.querySelector('canvas');
    if (!canvas) {
        viewer.innerHTML = '<canvas id="viewer-canvas"></canvas>';
        canvas = document.getElementById('viewer-canvas');
    }

    // Set canvas size for full quality (aspect ratio 9:19.5)
    canvas.width = 1080;
    canvas.height = 1920;

    renderFrameToCanvas(canvas, frameBase64);
}

// Update active streams count
function updateActiveStreamsCount() {
    const activeCount = Object.values(phoneScreenStates).filter(s => s).length;
    updateStat('active-streams', activeCount);
}

// Capture screenshot from selected phone
function captureScreenshot() {
    if (!selectedScreenPhone) {
        showToast('Select a phone first', 'error');
        return;
    }

    const viewer = document.getElementById('screen-viewer');
    const canvas = viewer?.querySelector('canvas');

    if (!canvas) {
        showToast('No screen to capture', 'error');
        return;
    }

    // Convert canvas to blob and download
    canvas.toBlob((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${selectedScreenPhone}_${Date.now()}.png`;
        a.click();
        URL.revokeObjectURL(url);

        showToast('Screenshot saved', 'success');
    });
}

// Refresh screen (request new frame)
async function refreshScreen() {
    if (!selectedScreenPhone) {
        showToast('Select a phone first', 'error');
        return;
    }

    // Downgrade and upgrade to force refresh
    try {
        await fetch('/api/screens/upgrade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone_name: selectedScreenPhone,
                quality: 'full'
            })
        });

        showToast('Refreshing...', 'success');

    } catch (error) {
        console.error('Failed to refresh:', error);
    }
}

// Toggle fullscreen for viewer
function toggleFullscreen() {
    const viewer = document.getElementById('screen-viewer');

    if (!document.fullscreenElement) {
        viewer.requestFullscreen().catch(err => {
            showToast(`Fullscreen error: ${err.message}`, 'error');
        });
    } else {
        document.exitFullscreen();
    }
}

// Update showTab function to initialize screens when Screens tab is shown
const originalShowTab = showTab;
showTab = function(tabName) {
    originalShowTab(tabName);

    if (tabName === 'screens' && phones.length > 0 && !screenStreamingActive) {
        initializePhoneScreens();
    }
};
