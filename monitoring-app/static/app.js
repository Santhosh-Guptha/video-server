// VMS Monitoring Front-End Client

let socket = null;
let reconnectTimeout = null;
let currentTelemetry = null;
let autoscroll = true;

// UI Elements
const wsStatus = document.getElementById("ws-status");
const systemTime = document.getElementById("system-time");
const cpuRing = document.getElementById("cpu-ring");
const cpuValue = document.getElementById("cpu-value");
const cpuCores = document.getElementById("cpu-cores");
const ramRing = document.getElementById("ram-ring");
const ramValue = document.getElementById("ram-value");
const ramGB = document.getElementById("ram-gb");
const diskRootPercent = document.getElementById("disk-root-percent");
const diskRootFill = document.getElementById("disk-root-fill");
const diskRootGB = document.getElementById("disk-root-gb");
const diskStoragePercent = document.getElementById("disk-storage-percent");
const diskStorageFill = document.getElementById("disk-storage-fill");
const diskStorageGB = document.getElementById("disk-storage-gb");
const netIn = document.getElementById("net-in");
const netOut = document.getElementById("net-out");
const diskRead = document.getElementById("disk-read");
const diskWrite = document.getElementById("disk-write");
const servicesContainer = document.getElementById("services-container");
const logConsole = document.getElementById("log-console");
const logServiceSelector = document.getElementById("log-service-selector");
const logSearch = document.getElementById("log-search");
const toggleAutoscroll = document.getElementById("toggle-autoscroll");
const issuesList = document.getElementById("issues-list");
const issuesCount = document.getElementById("issues-count");

// Filter Tabs
const filterTabs = document.querySelectorAll(".filter-tab");
let activeLogFilter = "all";

// Setup SVG dasharrays (circumference is 2 * PI * radius = 2 * 3.14159 * 50 = 314.16)
const CIRCUMFERENCE = 314.16;

function setProgress(circleElement, percent) {
    const offset = CIRCUMFERENCE - (percent / 100) * CIRCUMFERENCE;
    circleElement.style.strokeDashoffset = offset;
}

// Format bytes to human readable sizes
function formatBytes(bytes) {
    if (bytes === 0) return '0.00 GB';
    const gbs = bytes / (1024 ** 3);
    return gbs.toFixed(2) + ' GB';
}

// Connect to WebSocket Server
function connectWebSocket() {
    // Determine target host based on browser URL
    const loc = window.location;
    let wsUri = "";
    if (loc.protocol === "https:") {
        wsUri = `wss://${loc.host}/ws`;
    } else {
        wsUri = `ws://${loc.host}/ws`;
    }

    // Handle local testing fallback
    if (loc.hostname === "" || loc.hostname === "localhost") {
        wsUri = "ws://127.0.0.1:8010/ws";
    }

    console.log(`Connecting to WebSocket: ${wsUri}`);
    
    // Clear status classes
    wsStatus.className = "connection-pill";
    wsStatus.querySelector(".indicator").className = "indicator red";
    wsStatus.querySelector(".text").textContent = "Connecting...";

    socket = new WebSocket(wsUri);

    socket.onopen = () => {
        console.log("WebSocket connected.");
        wsStatus.querySelector(".indicator").className = "indicator green";
        wsStatus.querySelector(".text").textContent = "Live Telemetry";
        
        if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
            reconnectTimeout = null;
        }
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            currentTelemetry = data;
            updateDashboard(data);
        } catch (err) {
            console.error("Failed to parse telemetry message:", err);
        }
    };

    socket.onclose = () => {
        console.warn("WebSocket connection lost. Reconnecting in 3s...");
        wsStatus.querySelector(".indicator").className = "indicator red";
        wsStatus.querySelector(".text").textContent = "Offline (Reconnecting)";
        
        socket = null;
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
    };

    socket.onerror = (error) => {
        console.error("WebSocket error:", error);
    };
}

// Update UI Layout
function updateDashboard(telemetry) {
    // 1. Hardware metrics
    const sys = telemetry.system;
    
    // System Time
    const dt = new Date(telemetry.timestamp * 1000);
    systemTime.textContent = dt.toLocaleTimeString();

    // CPU
    cpuValue.textContent = `${Math.round(sys.cpu_percent)}%`;
    setProgress(cpuRing, sys.cpu_percent);
    cpuCores.textContent = `${sys.cpu_count} Cores`;
    
    // RAM
    ramValue.textContent = `${Math.round(sys.ram_percent)}%`;
    setProgress(ramRing, sys.ram_percent);
    ramGB.textContent = `${sys.ram_used_gb.toFixed(1)} / ${sys.ram_total_gb.toFixed(1)} GB`;

    // Disk ROMs
    diskRootPercent.textContent = `${sys.disk_root.percent}%`;
    diskRootFill.style.width = `${sys.disk_root.percent}%`;
    diskRootGB.textContent = `${formatBytes(sys.disk_root.used)} / ${formatBytes(sys.disk_root.total)}`;

    diskStoragePercent.textContent = `${sys.disk_storage.percent}%`;
    diskStorageFill.style.width = `${sys.disk_storage.percent}%`;
    diskStorageGB.textContent = `${formatBytes(sys.disk_storage.used)} / ${formatBytes(sys.disk_storage.total)}`;

    // I/O Speeds
    netIn.textContent = `${sys.speeds.net_in_mb_s.toFixed(2)} MB/s`;
    netOut.textContent = `${sys.speeds.net_out_mb_s.toFixed(2)} MB/s`;
    diskRead.textContent = `${sys.speeds.disk_read_mb_s.toFixed(2)} MB/s`;
    diskWrite.textContent = `${sys.speeds.disk_write_mb_s.toFixed(2)} MB/s`;

    // 2. Services List
    renderServices(telemetry.services);

    // 3. System logs console
    renderLogs(telemetry.logs);

    // 4. Alerts
    renderIssues(telemetry.issues);
}

// Render service cards
function renderServices(services) {
    servicesContainer.innerHTML = "";
    
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
            
            <div class="service-metrics">
                <div class="sub-metric">
                    <span class="val">${info.cpu_percent}%</span>
                    <span class="lbl">CPU</span>
                </div>
                <div class="sub-metric">
                    <span class="val">${info.memory_mb} MB</span>
                    <span class="lbl">RAM</span>
                </div>
                <div class="sub-metric">
                    <span class="val">${info.rom_usage || 'Calculating...'}</span>
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
                <button class="btn btn-stop" onclick="triggerServiceAction('${name}', '${isActive ? 'stop' : 'start'}')">
                    <i class="fa-solid ${isActive ? 'fa-stop' : 'fa-play'}"></i> ${isActive ? 'Stop' : 'Start'}
                </button>
            </div>
        `;
        servicesContainer.appendChild(card);
    }
}

// Call Service API action
async function triggerServiceAction(serviceName, action) {
    if (!confirm(`Are you sure you want to ${action} service ${serviceName}?`)) {
        return;
    }
    
    console.log(`Executing ${action} on service ${serviceName}...`);
    try {
        const resp = await fetch(`/api/services/${serviceName}/action`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ action: action })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert(data.message);
        } else {
            alert(`Error: ${data.detail || 'Failed to control service'}`);
        }
    } catch (err) {
        console.error("Control service network failure:", err);
        alert("Failed to communicate with the service API.");
    }
}

// Render log console logs
function renderLogs(logs) {
    const selectedService = logServiceSelector.value;
    const searchText = logSearch.value.toLowerCase();
    
    let combinedLogs = [];
    
    // Aggregate logs
    if (selectedService === "all") {
        for (const [srv, lines] of Object.entries(logs)) {
            lines.forEach(line => {
                combinedLogs.push({ service: srv, text: line });
            });
        }
        // Sort combined logs (most journalctl entries contain timestamps)
        combinedLogs.sort((a, b) => a.text.localeCompare(b.text));
    } else {
        const lines = logs[selectedService] || [];
        lines.forEach(line => {
            combinedLogs.push({ service: selectedService, text: line });
        });
    }

    logConsole.innerHTML = "";
    let matchCount = 0;

    combinedLogs.forEach(logObj => {
        const lineText = logObj.text;
        const lineTextLower = lineText.toLowerCase();
        
        // Search filter
        if (searchText && !lineTextLower.includes(searchText)) {
            return;
        }

        // Level validation
        let isError = lineTextLower.includes("error") || lineTextLower.includes("exception") || lineTextLower.includes("failed");
        let isWarning = lineTextLower.includes("warning") || lineTextLower.includes("warn");
        
        if (activeLogFilter === "error" && !isError) return;
        if (activeLogFilter === "warning" && !isWarning && !isError) return;

        let styleClass = "info";
        if (isError) styleClass = "err";
        else if (isWarning) styleClass = "warn";

        const logSpan = document.createElement("div");
        logSpan.className = `log-line ${styleClass}`;
        logSpan.textContent = `[${logObj.service}] ${lineText}`;
        logConsole.appendChild(logSpan);
        matchCount++;
    });

    if (matchCount === 0) {
        logConsole.innerHTML = '<div class="no-logs">No matching logs found.</div>';
    }

    if (autoscroll) {
        logConsole.scrollTop = logConsole.scrollHeight;
    }
}

// Render Warning Issues
function renderIssues(issues) {
    issuesList.innerHTML = "";
    issuesCount.textContent = issues.length;
    
    if (issues.length === 0) {
        issuesList.innerHTML = `
            <div class="no-issues">
                <i class="fa-solid fa-circle-check"></i>
                <p>All services healthy. No active alerts.</p>
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
            <i class="fa-solid ${iconClass} issue-icon"></i>
            <div class="issue-content">
                <span class="issue-message">${issue.message}</span>
                <span class="issue-meta">[Service: ${issue.service}] @ ${dateStr}</span>
            </div>
        `;
        issuesList.appendChild(item);
    });
}

// Filter button tab click listeners
filterTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        filterTabs.forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        activeLogFilter = tab.getAttribute("data-filter");
        
        if (currentTelemetry) {
            renderLogs(currentTelemetry.logs);
        }
    });
});

logServiceSelector.addEventListener("change", () => {
    if (currentTelemetry) {
        renderLogs(currentTelemetry.logs);
    }
});

logSearch.addEventListener("input", () => {
    if (currentTelemetry) {
        renderLogs(currentTelemetry.logs);
    }
});

toggleAutoscroll.addEventListener("click", () => {
    autoscroll = !autoscroll;
    toggleAutoscroll.classList.toggle("active", autoscroll);
    if (autoscroll && logConsole) {
        logConsole.scrollTop = logConsole.scrollHeight;
    }
});

// Run
window.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
});
