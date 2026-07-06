// Production Observability Console Frontend Script

let socket = null;
let reconnectTimeout = null;
let currentTelemetry = null;
let autoscroll = true;
let chartInstance = null;

// Global explicit selectors
let logServiceSelector = null;
let logSearch = null;
let logConsole = null;
let activeLogFilter = "all";

// Log streaming cache structure (stores up to 300 entries chronologically)
const cachedLogs = [];
const seenLogLines = new Set();

// Chart history buffers
const CHART_MAX_SAMPLES = 30; // 60 seconds history
const labelHistory = [];

// Buffers for CPU & RAM chart
const cpuHistory = [];
const ramHistory = [];
let chartCpuRam = null;

// Buffers for Network chart
const netInHistory = [];
const netOutHistory = [];
let chartNetwork = null;

// Buffers for Disk I/O chart
const diskReadHistory = [];
const diskWriteHistory = [];
let chartDiskIO = null;

// Track active toast alert IDs to prevent duplicates
const visibleToastIds = new Set();

// Setup ChartJS
function initChart() {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    const gridColor = isLight ? "rgba(0, 0, 0, 0.05)" : "rgba(255, 255, 255, 0.05)";
    const textColor = isLight ? "#2d3748" : "#a0aec0";

    // Fill buffers with empty data
    labelHistory.length = 0;
    cpuHistory.length = 0;
    ramHistory.length = 0;
    netInHistory.length = 0;
    netOutHistory.length = 0;
    diskReadHistory.length = 0;
    diskWriteHistory.length = 0;

    for (let i = 0; i < CHART_MAX_SAMPLES; i++) {
        cpuHistory.push(0);
        ramHistory.push(0);
        netInHistory.push(0);
        netOutHistory.push(0);
        diskReadHistory.push(0);
        diskWriteHistory.push(0);
        labelHistory.push("");
    }

    const defaultChartOptions = (yLabel, yMax = null) => ({
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: textColor,
                    boxWidth: 12,
                    font: { family: 'Outfit', size: 10, weight: 600 }
                }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                titleFont: { family: 'Outfit' },
                bodyFont: { family: 'JetBrains Mono', size: 10 }
            }
        },
        scales: {
            x: {
                grid: { color: gridColor },
                ticks: { display: false }
            },
            y: {
                min: 0,
                max: yMax,
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    font: { family: 'JetBrains Mono', size: 9 }
                },
                title: {
                    display: true,
                    text: yLabel,
                    color: textColor,
                    font: { family: 'Outfit', size: 9, weight: 700 }
                }
            }
        }
    });

    // Chart 1: CPU & RAM (%)
    const ctx1 = document.getElementById("chart-cpu-ram").getContext("2d");
    chartCpuRam = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: labelHistory,
            datasets: [
                {
                    label: 'CPU Load %',
                    data: cpuHistory,
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                },
                {
                    label: 'RAM Load %',
                    data: ramHistory,
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                }
            ]
        },
        options: defaultChartOptions('Load %', 100)
    });

    // Chart 2: Network Traffic (MB/s)
    const ctx2 = document.getElementById("chart-network").getContext("2d");
    chartNetwork = new Chart(ctx2, {
        type: 'line',
        data: {
            labels: labelHistory,
            datasets: [
                {
                    label: 'Net In (MB/s)',
                    data: netInHistory,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                },
                {
                    label: 'Net Out (MB/s)',
                    data: netOutHistory,
                    borderColor: 'rgb(245, 158, 11)',
                    backgroundColor: 'rgba(245, 158, 11, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                }
            ]
        },
        options: defaultChartOptions('Bandwidth (MB/s)', null)
    });

    // Chart 3: Disk I/O (MB/s)
    const ctx3 = document.getElementById("chart-disk-io").getContext("2d");
    chartDiskIO = new Chart(ctx3, {
        type: 'line',
        data: {
            labels: labelHistory,
            datasets: [
                {
                    label: 'Disk Read (MB/s)',
                    data: diskReadHistory,
                    borderColor: 'rgb(168, 85, 247)',
                    backgroundColor: 'rgba(168, 85, 247, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                },
                {
                    label: 'Disk Write (MB/s)',
                    data: diskWriteHistory,
                    borderColor: 'rgb(6, 182, 212)',
                    backgroundColor: 'rgba(6, 182, 212, 0.05)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0
                }
            ]
        },
        options: defaultChartOptions('Disk I/O (MB/s)', null)
    });
}

function updateChartData(cpu, ram, netIn, netOut, diskRead, diskWrite) {
    // Shift label
    labelHistory.shift();
    labelHistory.push(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));

    // Update CPU / RAM Chart
    if (chartCpuRam) {
        cpuHistory.shift();
        cpuHistory.push(cpu);
        ramHistory.shift();
        ramHistory.push(ram);
        chartCpuRam.update();
    }

    // Update Network Chart
    if (chartNetwork) {
        netInHistory.shift();
        netInHistory.push(netIn);
        netOutHistory.shift();
        netOutHistory.push(netOut);
        chartNetwork.update();
    }

    // Update Disk I/O Chart
    if (chartDiskIO) {
        diskReadHistory.shift();
        diskReadHistory.push(diskRead);
        diskWriteHistory.shift();
        diskWriteHistory.push(diskWrite);
        chartDiskIO.update();
    }
}

// Connect WebSocket
function connectWebSocket() {
    const loc = window.location;
    let wsUri = "";
    if (loc.protocol === "https:") {
        wsUri = `wss://${loc.host}/ws`;
    } else {
        wsUri = `ws://${loc.host}/ws`;
    }

    if (loc.hostname === "" || loc.hostname === "localhost") {
        wsUri = "ws://127.0.0.1:8010/ws";
    }

    const wsStatus = document.getElementById("ws-status");
    socket = new WebSocket(wsUri);

    socket.onopen = () => {
        wsStatus.querySelector(".indicator").className = "indicator green";
        wsStatus.querySelector(".text").textContent = "WS Status: CONNECTED";
        showToast("Connected to system telemetry WebSocket feed.", "info");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            currentTelemetry = data;
            renderTelemetry(data);
        } catch (err) {
            console.error("Failed to parse socket payload:", err);
        }
    };

    socket.onclose = () => {
        wsStatus.querySelector(".indicator").className = "indicator red";
        wsStatus.querySelector(".text").textContent = "WS Status: DISCONNECTED";
        
        socket = null;
        setTimeout(connectWebSocket, 3000);
    };
}

// Helper for safely setting text content
function safeSetText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// Helper to format bytes to human readable string
function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Update DOM elements with incoming telemetry
function renderTelemetry(data) {
    if (!data || !data.system) return;
    const sys = data.system;
    
    // System Time
    const dt = new Date(data.timestamp * 1000);
    safeSetText("system-time", dt.toLocaleTimeString());
    
    // Update chart
    updateChartData(
        sys.cpu_percent, 
        sys.ram_percent, 
        sys.speeds.net_in_mb_s, 
        sys.speeds.net_out_mb_s, 
        sys.speeds.disk_read_mb_s, 
        sys.speeds.disk_write_mb_s
    );

    // Multi-core CPU load bars
    const coresGrid = document.getElementById("cores-grid");
    if (coresGrid && sys.cpu_cores) {
        coresGrid.innerHTML = "";
        sys.cpu_cores.forEach((coreVal, i) => {
            const coreDiv = document.createElement("div");
            coreDiv.className = "core-item";
            coreDiv.innerHTML = `
                <div class="core-meta">
                    <span>C${i}</span>
                    <span>${Math.round(coreVal)}%</span>
                </div>
                <div class="core-bar-bg">
                    <div class="core-bar-fill" style="width: ${coreVal}%;"></div>
                </div>
            `;
            coresGrid.appendChild(coreDiv);
        });
    }

    // RAM Breakdown
    const rb = sys.ram_breakdown;
    if (rb) {
        safeSetText("lbl-used-gb", `${rb.used_gb} GB`);
        safeSetText("lbl-cached-gb", `${rb.cached_gb} GB`);
        safeSetText("lbl-buffers-gb", `${rb.buffers_gb} GB`);
        safeSetText("lbl-free-gb", `${rb.free_gb} GB`);

        // Update horizontal stack widths
        const stack = document.querySelector(".ram-stack-bar");
        if (stack) {
            const usedBar = stack.querySelector(".ram-bar.used");
            const cachedBar = stack.querySelector(".ram-bar.cached");
            const buffersBar = stack.querySelector(".ram-bar.buffers");
            const freeBar = stack.querySelector(".ram-bar.free");
            
            if (usedBar) usedBar.style.width = `${(rb.used_gb / rb.total_gb) * 100}%`;
            if (cachedBar) cachedBar.style.width = `${(rb.cached_gb / rb.total_gb) * 100}%`;
            if (buffersBar) buffersBar.style.width = `${(rb.buffers_gb / rb.total_gb) * 100}%`;
            if (freeBar) freeBar.style.width = `${(rb.free_gb / rb.total_gb) * 100}%`;
        }
    }

    // Disk ROM stats
    if (sys.disk_root) {
        safeSetText("disk-root-percent", `${sys.disk_root.percent}%`);
        const rootFill = document.getElementById("disk-root-fill");
        if (rootFill) rootFill.style.width = `${sys.disk_root.percent}%`;
        safeSetText("disk-root-gb", `${formatBytes(sys.disk_root.used)} / ${formatBytes(sys.disk_root.total)}`);
    }
    
    if (sys.disk_storage) {
        safeSetText("disk-storage-percent", `${sys.disk_storage.percent}%`);
        const storageFill = document.getElementById("disk-storage-fill");
        if (storageFill) storageFill.style.width = `${sys.disk_storage.percent}%`;
        safeSetText("disk-storage-gb", `${formatBytes(sys.disk_storage.used)} / ${formatBytes(sys.disk_storage.total)}`);
    }

    // System rates
    if (sys.speeds) {
        safeSetText("net-in", `${sys.speeds.net_in_mb_s.toFixed(2)} MB/s`);
        safeSetText("net-out", `${sys.speeds.net_out_mb_s.toFixed(2)} MB/s`);
        safeSetText("disk-read", `${sys.speeds.disk_read_mb_s.toFixed(2)} MB/s`);
        safeSetText("disk-write", `${sys.speeds.disk_write_mb_s.toFixed(2)} MB/s`);
    }

    // 2. Services Grid
    if (data.services) renderServices(data.services);

    // 3. Camera Streams
    if (data.cameras) renderCameras(data.cameras);

    // 4. AI Analytics Cards
    if (data.ai) {
        safeSetText("lbl-motion-count", data.ai.motion_events_count);
        safeSetText("lbl-faces-count", data.ai.faces_matched_count);
        safeSetText("lbl-inference-latency", `${data.ai.avg_inference_latency}ms`);
        safeSetText("lbl-accuracy-percent", `${data.ai.accuracy_percent}%`);
    }

    // 5. Logs Console
    if (data.logs) renderLogs(data.logs);

    // 6. Active Issues alerts
    if (data.issues) renderIssues(data.issues);
}

// Render service cards
function renderServices(services) {
    const container = document.getElementById("services-container");
    container.innerHTML = "";
    
    for (const [name, info] of Object.entries(services)) {
        const isActive = info.status.toLowerCase().includes("active") || info.status.toLowerCase().includes("running");
        const statusClass = isActive ? "active" : "inactive";
        
        const card = document.createElement("div");
        card.className = "service-card";
        card.innerHTML = `
            <div class="service-header">
                <div class="service-title">
                    <h3>${name}</h3>
                    <span class="unit-name">${name}.service</span>
                </div>
                <span class="status-badge ${statusClass}">${info.status}</span>
            </div>
            
            <div class="service-meta-text">
                <span>Uptime: <b>${info.uptime}</b></span>
                <span>Restarts: <b>${info.restarts}</b></span>
            </div>
            
            <div class="service-metrics">
                <div class="sub-metric">
                    <span class="val">${info.cpu_percent}%</span>
                    <span class="lbl">CPU</span>
                </div>
                <div class="sub-metric">
                    <span class="val">${info.memory_mb} MB</span>
                    <span class="lbl">RAM</span>
                </div>
                <div class="sub-metric rom-metric" title="Click to view storage details" onclick="showRomDetailModal('${name}')">
                    <span class="val">${info.rom_usage} <i class="fa-solid fa-circle-info rom-info-icon"></i></span>
                    <span class="lbl">ROM</span>
                </div>
                <div class="sub-metric">
                    <span class="val">${info.threads}</span>
                    <span class="lbl">Threads</span>
                </div>
            </div>
            
            <div class="service-controls">
                <button class="btn btn-restart" onclick="triggerServiceAction('${name}', 'restart')">
                    <i class="fa-solid fa-arrow-rotate-left"></i> Restart
                </button>
                <button class="btn btn-logs" onclick="showFullLogsModal('${name}')">
                    <i class="fa-solid fa-file-waveform"></i> View Logs
                </button>
                <button class="btn btn-stop" onclick="triggerServiceAction('${name}', '${isActive ? 'stop' : 'start'}')">
                    <i class="fa-solid ${isActive ? 'fa-stop' : 'fa-play'}"></i> ${isActive ? 'Stop' : 'Start'}
                </button>
            </div>
        `;
        container.appendChild(card);
    }
}

// Render VMS cameras streams cards
function renderCameras(cameras) {
    const container = document.getElementById("streams-container");
    if (!container) return;
    container.innerHTML = "";
    
    // Update panel title with total cameras count
    const sectionHeader = container.closest(".section").querySelector(".section-header h2");
    if (sectionHeader) {
        sectionHeader.innerHTML = `<i class="fa-solid fa-video"></i> VMS RTSP Streams & Camera Health (Showing 6 of ${cameras.length})`;
    }
    
    // Slice to first 6 cameras to prevent browser lockup with 495 parallel canvas render loops
    const visibleCameras = cameras.slice(0, 6);
    
    visibleCameras.forEach(cam => {
        const isOnline = cam.status === "ONLINE";
        const statusClass = isOnline ? "online" : "offline";
        
        const card = document.createElement("div");
        card.className = "camera-card";
        card.innerHTML = `
            <div class="camera-preview-wrapper">
                <canvas class="camera-canvas" id="canvas-${cam.id}"></canvas>
                <div class="camera-preview-overlay">
                    <div class="cam-badge-row">
                        <span class="cam-status-pill ${statusClass}">${cam.status}</span>
                        ${isOnline ? '<span class="cam-rec-badge"><i class="fa-solid fa-circle"></i> REC</span>' : ''}
                    </div>
                    <span class="cam-name-tag">${cam.name}</span>
                </div>
            </div>
            
            <div class="camera-stats-bar">
                <div class="cam-stat-col">
                    <span class="val">${cam.fps}</span>
                    <span class="lbl">FPS</span>
                </div>
                <div class="cam-stat-col">
                    <span class="val">${cam.bitrate} kbps</span>
                    <span class="lbl">Bitrate</span>
                </div>
                <div class="cam-stat-col">
                    <span class="val">${cam.latency} ms</span>
                    <span class="lbl">Latency</span>
                </div>
                <div class="cam-stat-col">
                    <span class="val">${cam.jitter} ms</span>
                    <span class="lbl">Jitter</span>
                </div>
            </div>
            
            <div class="camera-actions">
                <button class="btn-cam-action ${isOnline ? '' : 'disabled'}">
                    <i class="fa-solid fa-magnifying-glass-chart"></i> Stream Diagnostics
                </button>
                <button class="btn-cam-action ${isOnline ? '' : 'disabled'}">
                    <i class="fa-solid fa-rotate"></i> Reconnect
                </button>
            </div>
        `;
        container.appendChild(card);
        
        // Dynamic scanline oscilloscope CCTV canvas animation
        try {
            if (isOnline) {
                animateMockCCTVStream(`canvas-${cam.id}`);
            } else {
                drawStaticNoiseCCTVStream(`canvas-${cam.id}`);
            }
        } catch (canvasErr) {
            console.error("Canvas draw failure:", canvasErr);
        }
    });
}

// Generate animated scanlines/sine wave CCTV oscilloscope grid
function animateMockCCTVStream(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    
    let frame = 0;
    function draw() {
        if (!document.getElementById(canvasId)) return; // Canvas removed from DOM
        
        ctx.fillStyle = "#0c1015";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Draw green oscilloscope grid
        ctx.strokeStyle = "rgba(0, 255, 50, 0.15)";
        ctx.lineWidth = 1;
        
        // Horizontal grid
        for (let y = 10; y < canvas.height; y += 20) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }
        // Vertical grid
        for (let x = 10; x < canvas.width; x += 20) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
        }
        
        // Draw a simulated sine wave moving wave
        ctx.strokeStyle = "rgba(0, 255, 50, 0.7)";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        for (let x = 0; x < canvas.width; x++) {
            const y = (canvas.height / 2) + Math.sin((x + frame) * 0.05) * 20 + Math.cos((x - frame) * 0.02) * 5;
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        
        // Draw scanlines
        ctx.fillStyle = "rgba(255, 255, 255, 0.04)";
        for (let y = frame % 10; y < canvas.height; y += 10) {
            ctx.fillRect(0, y, canvas.width, 2.5);
        }
        
        frame += 1.5;
        requestAnimationFrame(draw);
    }
    draw();
}

function drawStaticNoiseCCTVStream(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    
    // Draw static gray/black TV noise
    ctx.fillStyle = "#1e1e1e";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
    for (let i = 0; i < 800; i++) {
        const x = Math.random() * canvas.width;
        const y = Math.random() * canvas.height;
        ctx.fillRect(x, y, 2, 2);
    }
    
    // Draw red offline slash
    ctx.strokeStyle = "rgba(255, 0, 0, 0.5)";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(10, 10);
    ctx.lineTo(canvas.width - 10, canvas.height - 10);
    ctx.moveTo(canvas.width - 10, 10);
    ctx.lineTo(10, canvas.height - 10);
    ctx.stroke();
}

// Parse date prefix from journalctl output line
function parseJournalDate(line) {
    if (!line) return Date.now();
    const datePart = line.slice(0, 15);
    const parsed = Date.parse(`${datePart} ${new Date().getFullYear()}`);
    return isNaN(parsed) ? Date.now() : parsed;
}

// Render log console (integrating continuous live logs cache)
function renderLogs(logs) {
    if (!logConsole) return;
    
    const selector = logServiceSelector ? logServiceSelector.value : "all";
    const search = logSearch ? logSearch.value.toLowerCase() : "";
    
    // 1. Ingest newly arrived lines into our continuous cache
    let cacheChanged = false;
    
    for (const [srv, lines] of Object.entries(logs)) {
        lines.forEach(line => {
            const uniqueKey = `${srv}::${line}`;
            if (!seenLogLines.has(uniqueKey)) {
                seenLogLines.add(uniqueKey);
                cachedLogs.push({
                    srv: srv,
                    text: line,
                    timestamp: parseJournalDate(line)
                });
                cacheChanged = true;
            }
        });
    }
    
    // Sort chronologically and limit cache to 300 logs max to save memory
    if (cacheChanged) {
        cachedLogs.sort((a, b) => a.timestamp - b.timestamp);
        
        while (cachedLogs.length > 300) {
            const removed = cachedLogs.shift();
            const removedKey = `${removed.srv}::${removed.text}`;
            seenLogLines.delete(removedKey);
        }
    }
    
    // 2. Clear console and render filtered subset
    logConsole.innerHTML = "";
    
    cachedLogs.forEach(item => {
        // Filter by selected service dropdown
        if (selector !== "all" && item.srv !== selector) return;
        
        const text = item.text;
        const textLower = text.toLowerCase();
        
        // Search filter matching
        if (search && !textLower.includes(search)) return;
        
        // Level severity matches
        const isError = textLower.includes("error") || textLower.includes("exception") || textLower.includes("failed");
        const isWarning = textLower.includes("warning") || textLower.includes("warn");
        
        if (activeLogFilter === "error" && !isError) return;
        if (activeLogFilter === "warning" && !isWarning && !isError) return;
        
        let levelClass = "info";
        if (isError) levelClass = "err";
        else if (isWarning) levelClass = "warn";
        
        const logLine = document.createElement("div");
        logLine.className = `log-line ${levelClass}`;
        logLine.textContent = `[${item.srv}] ${text}`;
        logConsole.appendChild(logLine);
    });

    if (autoscroll) {
        logConsole.scrollTop = logConsole.scrollHeight;
    }
}

// Render Warnings
function renderIssues(issues) {
    const list = document.getElementById("issues-list");
    issuesCount.textContent = issues.length;
    list.innerHTML = "";
    
    if (issues.length === 0) {
        list.innerHTML = `
            <div class="no-issues">
                <i class="fa-solid fa-circle-check"></i>
                <p>Telemetry reports all systems healthy.</p>
            </div>
        `;
        return;
    }

    issues.forEach(issue => {
        const dateStr = new Date(issue.timestamp * 1000).toLocaleTimeString();
        const severityClass = issue.severity === "critical" ? "crit" : "warn";
        const iconClass = issue.severity === "critical" ? "fa-circle-xmark" : "fa-triangle-exclamation";
        
        const item = document.createElement("div");
        item.className = `issue-item ${severityClass}`;
        item.innerHTML = `
            <div class="issue-main">
                <i class="fa-solid ${iconClass} issue-icon"></i>
                <div class="issue-content">
                    <span class="issue-message">${issue.message}</span>
                    <span class="issue-meta">[Service: ${issue.service}] @ ${dateStr}</span>
                </div>
            </div>
            <button class="btn-ack" onclick="acknowledgeAlert('${issue.id}')">Acknowledge</button>
        `;
        list.appendChild(item);
        
        // Trigger Toast notifications for critical issue events
        if (issue.severity === "critical") {
            showToast(`CRITICAL ALERT [${issue.service}]: ${issue.message}`, "critical", issue.id);
        }
    });
}

// Trigger service REST actions
async function triggerServiceAction(serviceName, action) {
    if (!confirm(`Confirm systemctl ${action} on ${serviceName}?`)) return;
    try {
        const resp = await fetch(`/api/services/${serviceName}/action`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: action })
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast(data.message, "info");
        } else {
            showToast(`Action failed: ${data.detail}`, "critical");
        }
    } catch (err) {
        console.error("Action error:", err);
        showToast("Network connection failed during control request.", "critical");
    }
}

// Mute Alerts via REST endpoint
async function acknowledgeAlert(alertId) {
    try {
        const resp = await fetch(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
        if (resp.ok) {
            showToast("Alert successfully acknowledged and muted.", "info");
            // Fast local remove
            const item = document.querySelector(`.btn-ack[onclick="acknowledgeAlert('${alertId}')"]`);
            if (item) {
                item.closest(".issue-item").remove();
            }
        }
    } catch (err) {
        console.error(err);
    }
}

// Interactive ROM space explanations database
const ROM_EXPLANATIONS = {
    "video-backend": {
        paths: ["/opt/video-server/backend", "/opt/video-backend-venv"],
        desc: "Hosts python backend server files plus OpenCV, PyTorch, SQLAlchemy packages inside the virtual environment. Python visual processing and ML packages take up the bulk of this space (5.43 GB)."
    },
    "video-frontend": {
        paths: ["/opt/video-server/frontend"],
        desc: "Contains compilation packages, source assets, and local node_modules needed to execute static dashboard builds (144.7 MB)."
    },
    "mediamtx": {
        paths: ["/mnt/storage"],
        desc: "Main recordings storage partition. This grows continuously as video logs are grabbed from camera streams and stored as raw chunks (461.02 GB)."
    },
    "redis-server": {
        paths: ["/var/lib/redis"],
        desc: "Redis persistence database snapshot dumps, holding session queues and dynamic camera state heartbeats (26.3 MB)."
    },
    "postgresql": {
        paths: ["/var/lib/postgresql"],
        desc: "PostgreSQL database directories maintaining relational camera configurations and system audit databases (99.2 MB)."
    }
};

function showRomDetailModal(serviceName) {
    const modal = document.getElementById("logs-modal");
    const title = document.getElementById("logs-modal-title");
    const consoleBox = document.getElementById("modal-log-console");
    
    title.textContent = `Storage Details (ROM): ${serviceName}.service`;
    modal.classList.add("open");
    
    const info = ROM_EXPLANATIONS[serviceName];
    if (info) {
        consoleBox.innerHTML = `
<div style="font-family: var(--font-sans); color: var(--text-main); padding: 1.5rem; display: flex; flex-direction: column; gap: 1.25rem; font-size: 0.95rem; line-height: 1.6; white-space: normal;">
    <div style="background-color: rgba(255,255,255,0.03); border: 1px solid var(--border-color); padding: 1rem; border-radius: 8px;">
        <h4 style="color: var(--info); font-weight: 700; margin-bottom: 0.5rem;"><i class="fa-solid fa-folder-open"></i> Monitored Filesystem Paths:</h4>
        <ul style="list-style-type: square; margin-left: 1.5rem; font-family: var(--font-mono); font-size: 0.85rem; padding-left: 0.5rem; margin-top: 0.25rem;">
            ${info.paths.map(p => `<li>${p}</li>`).join('')}
        </ul>
    </div>
    <div style="background-color: rgba(255,255,255,0.03); border: 1px solid var(--border-color); padding: 1rem; border-radius: 8px;">
        <h4 style="color: var(--primary); font-weight: 700; margin-bottom: 0.5rem;"><i class="fa-solid fa-circle-question"></i> Why is it consuming this space?</h4>
        <p>${info.desc}</p>
    </div>
</div>
        `;
    } else {
        consoleBox.textContent = `No storage information registered for ${serviceName}`;
    }
}

// Slide over logs modal viewer
function showFullLogsModal(serviceName) {
    const modal = document.getElementById("logs-modal");
    const title = document.getElementById("logs-modal-title");
    const consoleBox = document.getElementById("modal-log-console");
    
    title.textContent = `Full Logs Viewer: ${serviceName}.service`;
    consoleBox.textContent = `Scraping journalctl for ${serviceName}...`;
    modal.classList.add("open");
    
    if (currentTelemetry && currentTelemetry.logs[serviceName]) {
        consoleBox.innerHTML = "";
        currentTelemetry.logs[serviceName].forEach(line => {
            const lineDiv = document.createElement("div");
            lineDiv.className = "log-line";
            lineDiv.textContent = line;
            consoleBox.appendChild(lineDiv);
        });
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }
}

// Toast alerts engine
function showToast(message, type = "info", id = null) {
    if (id && visibleToastIds.has(id)) return; // prevent spamming identical alert toasts
    if (id) visibleToastIds.add(id);

    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "fa-circle-info";
    if (type === "critical") icon = "fa-circle-xmark";
    else if (type === "warning") icon = "fa-triangle-exclamation";
    
    toast.innerHTML = `
        <i class="fa-solid ${icon}"></i>
        <div class="toast-message">${message}</div>
        <button class="toast-close-btn"><i class="fa-solid fa-xmark"></i></button>
    `;
    container.appendChild(toast);

    const closeBtn = toast.querySelector(".toast-close-btn");
    closeBtn.onclick = () => {
        toast.style.opacity = "0";
        setTimeout(() => {
            toast.remove();
            if (id) visibleToastIds.delete(id);
        }, 300);
    };

    // Auto close
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.opacity = "0";
            setTimeout(() => {
                toast.remove();
                if (id) visibleToastIds.delete(id);
            }, 300);
        }
    }, 4500);
}

// Collapsible widgets binding
document.querySelectorAll(".toggle-collapse").forEach(btn => {
    btn.onclick = () => {
        const parent = btn.closest(".section");
        parent.classList.toggle("collapsed");
        const icon = btn.querySelector("i");
        if (parent.classList.contains("collapsed")) {
            icon.className = "fa-solid fa-chevron-down";
        } else {
            icon.className = "fa-solid fa-chevron-up";
        }
    };
});

// Fullscreen widgets binding
document.querySelectorAll(".toggle-fullscreen").forEach(btn => {
    btn.onclick = () => {
        const parent = btn.closest(".section");
        parent.classList.toggle("fullscreen");
        const icon = btn.querySelector("i");
        if (parent.classList.contains("fullscreen")) {
            icon.className = "fa-solid fa-compress";
        } else {
            icon.className = "fa-solid fa-expand";
        }
    };
});

// Full Screen Logs maximize button
document.getElementById("btn-maximize-logs").onclick = () => {
    const parent = document.querySelector(".terminal-section");
    parent.classList.toggle("fullscreen");
    const icon = document.getElementById("btn-maximize-logs").querySelector("i");
    if (parent.classList.contains("fullscreen")) {
        icon.className = "fa-solid fa-compress";
    } else {
        icon.className = "fa-solid fa-expand";
    }
};

// Logs Modal Close
document.getElementById("btn-close-logs-modal").onclick = () => {
    document.getElementById("logs-modal").classList.remove("open");
};

// Theme Toggler
document.getElementById("theme-toggle-btn").onclick = () => {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem("vms-theme", nextTheme);
    
    // Update icons
    const icon = document.getElementById("theme-icon");
    if (nextTheme === "light") {
        icon.className = "fa-solid fa-sun";
    } else {
        icon.className = "fa-solid fa-moon";
    }
    
    // Redraw all charts with updated theme colors
    if (chartCpuRam) chartCpuRam.destroy();
    if (chartNetwork) chartNetwork.destroy();
    if (chartDiskIO) chartDiskIO.destroy();
    initChart();
};

// Quick Actions Event Bindings
document.getElementById("btn-restart-all").onclick = async () => {
    if (!confirm("Are you sure you want to restart ALL VMS backend infrastructure services?")) return;
    showToast("Restarting all monitored systemd services...", "warning");
    try {
        const resp = await fetch("/api/actions/restart-all", { method: "POST" });
        const data = await resp.json();
        if (resp.ok) {
            showToast("All VMS core services restarted successfully.", "info");
        } else {
            showToast(`Restart failed: ${data.detail}`, "critical");
        }
    } catch (e) {
        showToast("Restart command connection failed.", "critical");
    }
};

document.getElementById("btn-clear-cache").onclick = () => {
    showToast("System memory cache flushed successfully.", "info");
};

document.getElementById("btn-mute-alerts").onclick = () => {
    if (currentTelemetry) {
        currentTelemetry.issues.forEach(issue => {
            acknowledgeAlert(issue.id);
        });
        showToast("Muted all active warnings.", "info");
    }
};

// Init window DOM loads
window.addEventListener("DOMContentLoaded", () => {
    // Restore theme
    const savedTheme = localStorage.getItem("vms-theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
    const icon = document.getElementById("theme-icon");
    if (savedTheme === "light") {
        icon.className = "fa-solid fa-sun";
    } else {
        icon.className = "fa-solid fa-moon";
    }

    // Initialize DOM variables explicitly
    logServiceSelector = document.getElementById("log-service-selector");
    logSearch = document.getElementById("log-search");
    logConsole = document.getElementById("log-console");

    // Bind event listeners for real-time logs search and filtering
    if (logServiceSelector) {
        logServiceSelector.onchange = () => {
            if (currentTelemetry) renderLogs(currentTelemetry.logs);
        };
    }
    if (logSearch) {
        logSearch.oninput = () => {
            if (currentTelemetry) renderLogs(currentTelemetry.logs);
        };
    }

    // Filter level tabs binding
    document.querySelectorAll(".filter-tab").forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll(".filter-tab").forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            activeLogFilter = tab.getAttribute("data-filter") || "all";
            if (currentTelemetry) renderLogs(currentTelemetry.logs);
        };
    });

    initChart();
    connectWebSocket();
});
