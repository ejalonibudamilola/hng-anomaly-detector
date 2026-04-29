import time
import psutil
import threading
from flask import Flask, jsonify, render_template_string

# ── HTML template served at / ─────────────────────────────────
BASELINE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Baseline Graph — HNG Detector</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e2e8f0;
            padding: 24px;
        }
        h1 {
            font-size: 20px;
            color: #63b3ed;
            margin-bottom: 8px;
        }
        p {
            color: #718096;
            font-size: 13px;
            margin-bottom: 24px;
        }
        .chart-wrap {
            background: #1a202c;
            border: 1px solid #2d3748;
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 24px;
        }
        .chart-title {
            font-size: 13px;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 16px;
        }
        .bars {
            display: flex;
            align-items: flex-end;
            gap: 12px;
            height: 200px;
        }
        .bar-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            flex: 1;
        }
        .bar {
            width: 100%;
            border-radius: 4px 4px 0 0;
            transition: height 0.5s ease;
            min-height: 4px;
        }
        .bar.mean  { background: #63b3ed; }
        .bar.stddev { background: #f6ad55; opacity: 0.7; }
        .bar-label {
            font-size: 11px;
            color: #718096;
            text-align: center;
        }
        .bar-value {
            font-size: 11px;
            color: #a0aec0;
        }
        .legend {
            display: flex;
            gap: 20px;
            margin-top: 16px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: #a0aec0;
        }
        .legend-dot {
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: #1a202c;
            border: 1px solid #2d3748;
            border-radius: 10px;
            padding: 16px;
        }
        .stat-label {
            font-size: 11px;
            color: #718096;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: #63b3ed;
        }
        .no-data {
            color: #4a5568;
            font-style: italic;
            padding: 40px;
            text-align: center;
        }
        #last-updated {
            font-size: 12px;
            color: #4a5568;
            text-align: right;
        }
    </style>
</head>
<body>
    <h1>Baseline Graph — Hourly Slots</h1>
    <p>
        Shows effective mean and stddev per hour as the baseline
        learns from real traffic. Each slot updates every 60 seconds.
        Two visibly different bars confirm the baseline is adapting.
    </p>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Effective Mean</div>
            <div class="stat-value" id="eff-mean">—</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Effective Stddev</div>
            <div class="stat-value" id="eff-stddev">—</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Hourly Slots Collected</div>
            <div class="stat-value" id="slot-count">—</div>
        </div>
    </div>

    <div class="chart-wrap">
        <div class="chart-title">Mean requests/sec per hour</div>
        <div class="bars" id="mean-bars">
            <div class="no-data">
                Waiting for hourly data...
                Run the daemon for at least 2 hours to see slots here.
            </div>
        </div>
        <div class="legend">
            <div class="legend-item">
                <div class="legend-dot"
                     style="background:#63b3ed"></div>
                Mean req/s
            </div>
            <div class="legend-item">
                <div class="legend-dot"
                     style="background:#f6ad55"></div>
                Stddev
            </div>
        </div>
    </div>

    <div id="last-updated"></div>

<script>
async function fetchBaseline() {
    try {
        const res = await fetch('/api/baseline-history');
        const data = await res.json();
        updateGraph(data);
    } catch(e) {
        console.error('Failed to fetch baseline:', e);
    }
}

function updateGraph(data) {
    document.getElementById('eff-mean').textContent =
        data.effective_mean + ' req/s';
    document.getElementById('eff-stddev').textContent =
        data.effective_stddev;
    document.getElementById('slot-count').textContent =
        data.slots.length;

    const container = document.getElementById('mean-bars');

    if (data.slots.length === 0) {
        container.innerHTML =
            '<div class="no-data">Waiting for hourly data...' +
            'Run the daemon for at least 2 hours.</div>';
        return;
    }

    // Find max mean to scale bar heights
    const maxMean = Math.max(...data.slots.map(s => s.mean), 1);

    container.innerHTML = data.slots.map(slot => {
        const meanHeight = Math.max(
            (slot.mean / maxMean) * 180, 4
        );
        const stddevHeight = Math.max(
            (slot.stddev / maxMean) * 180, 4
        );
        return `
            <div class="bar-group">
                <div class="bar-value">${slot.mean}</div>
                <div style="display:flex;gap:3px;
                            align-items:flex-end;width:100%">
                    <div class="bar mean"
                         style="height:${meanHeight}px;
                                flex:1"></div>
                    <div class="bar stddev"
                         style="height:${stddevHeight}px;
                                flex:1"></div>
                </div>
                <div class="bar-label">${slot.hour}</div>
            </div>
        `;
    }).join('');

    document.getElementById('last-updated').textContent =
        'Last updated: ' + new Date().toLocaleTimeString();
}

fetchBaseline();
setInterval(fetchBaseline, 3000);
</script>
</body>
</html>
"""
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HNG Anomaly Detection Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Segoe UI', sans-serif;
            background: #0f1117;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 24px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #2d3748;
        }

        header h1 {
            font-size: 22px;
            font-weight: 600;
            color: #63b3ed;
        }

        #status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #48bb78;
            display: inline-block;
            margin-right: 8px;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.4; }
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .card {
            background: #1a202c;
            border: 1px solid #2d3748;
            border-radius: 10px;
            padding: 20px;
        }

        .card .label {
            font-size: 12px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }

        .card .value {
            font-size: 28px;
            font-weight: 700;
            color: #63b3ed;
        }

        .card .value.danger { color: #fc8181; }
        .card .value.warn   { color: #f6ad55; }
        .card .value.good   { color: #68d391; }

        .section {
            background: #1a202c;
            border: 1px solid #2d3748;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .section h2 {
            font-size: 14px;
            font-weight: 600;
            color: #a0aec0;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 16px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        th {
            text-align: left;
            padding: 8px 12px;
            color: #718096;
            font-weight: 500;
            border-bottom: 1px solid #2d3748;
            font-size: 12px;
            text-transform: uppercase;
        }

        td {
            padding: 10px 12px;
            border-bottom: 1px solid #1e2533;
            color: #cbd5e0;
        }

        tr:last-child td { border-bottom: none; }

        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }

        .badge.banned  { background: #742a2a; color: #fc8181; }
        .badge.active  { background: #1c4532; color: #68d391; }

        .ip-bar-wrap {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .ip-bar {
            height: 6px;
            background: #63b3ed;
            border-radius: 3px;
            min-width: 4px;
            transition: width 0.3s ease;
        }

        #last-updated {
            font-size: 12px;
            color: #4a5568;
            text-align: right;
            margin-top: 8px;
        }

        .empty {
            color: #4a5568;
            font-style: italic;
            font-size: 14px;
            padding: 8px 0;
        }
    </style>
</head>
<body>

<header>
    <h1>
        <span id="status-dot"></span>
        HNG Anomaly Detection Engine
    </h1>
    <div style="font-size:13px; color:#4a5568;">
        Auto-refreshes every 3 seconds
    </div>
</header>

<!-- Stat cards -->
<div class="grid">
    <div class="card">
        <div class="label">Global Req/s</div>
        <div class="value" id="global-rate">—</div>
    </div>
    <div class="card">
        <div class="label">Banned IPs</div>
        <div class="value danger" id="banned-count">—</div>
    </div>
    <div class="card">
        <div class="label">Baseline Mean</div>
        <div class="value good" id="baseline-mean">—</div>
    </div>
    <div class="card">
        <div class="label">Baseline Stddev</div>
        <div class="value good" id="baseline-stddev">—</div>
    </div>
    <div class="card">
        <div class="label">CPU Usage</div>
        <div class="value warn" id="cpu">—</div>
    </div>
    <div class="card">
        <div class="label">Memory Usage</div>
        <div class="value warn" id="memory">—</div>
    </div>
    <div class="card">
        <div class="label">Uptime</div>
        <div class="value" id="uptime">—</div>
    </div>
    <div class="card">
        <div class="label">Total Requests</div>
        <div class="value" id="total-requests">—</div>
    </div>
</div>

<!-- Banned IPs table -->
<div class="section">
    <h2>🚨 Currently Banned IPs</h2>
    <table>
        <thead>
            <tr>
                <th>IP Address</th>
                <th>Banned At</th>
                <th>Duration</th>
                <th>Condition</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody id="banned-table">
            <tr>
                <td colspan="5" class="empty">
                    No IPs currently banned
                </td>
            </tr>
        </tbody>
    </table>
</div>

<!-- Top 10 IPs table -->
<div class="section">
    <h2>📊 Top 10 Source IPs</h2>
    <table>
        <thead>
            <tr>
                <th>IP Address</th>
                <th>Total Requests</th>
                <th>Activity</th>
            </tr>
        </thead>
        <tbody id="top-ips-table">
            <tr>
                <td colspan="3" class="empty">
                    Waiting for traffic...
                </td>
            </tr>
        </tbody>
    </table>
</div>

<div id="last-updated"></div>

<script>
    // Fetch metrics from /api/metrics every 3 seconds
    async function fetchMetrics() {
        try {
            const res = await fetch('/api/metrics');
            const data = await res.json();
            updateDashboard(data);
        } catch (e) {
            console.error('Failed to fetch metrics:', e);
        }
    }

    function updateDashboard(data) {
        // Stat cards
        document.getElementById('global-rate').textContent =
            data.global_rate + ' req/s';
        document.getElementById('banned-count').textContent =
            data.banned_count;
        document.getElementById('baseline-mean').textContent =
            data.baseline_mean + ' req/s';
        document.getElementById('baseline-stddev').textContent =
            data.baseline_stddev;
        document.getElementById('cpu').textContent =
            data.cpu_percent + '%';
        document.getElementById('memory').textContent =
            data.memory_percent + '%';
        document.getElementById('uptime').textContent =
            data.uptime;
        document.getElementById('total-requests').textContent =
            data.total_requests.toLocaleString();

        // Banned IPs table
        const bannedTbody = document.getElementById('banned-table');
        if (data.banned_ips.length === 0) {
            bannedTbody.innerHTML =
                '<tr><td colspan="5" class="empty">' +
                'No IPs currently banned</td></tr>';
        } else {
            bannedTbody.innerHTML = data.banned_ips.map(ban => `
                <tr>
                    <td><code>${ban.ip}</code></td>
                    <td>${ban.banned_at}</td>
                    <td>${ban.duration === -1
                        ? 'Permanent'
                        : ban.duration + ' min'}</td>
                    <td>${ban.condition}</td>
                    <td>
                        <span class="badge banned">BANNED</span>
                    </td>
                </tr>
            `).join('');
        }

        // Top IPs table
        const topTbody = document.getElementById('top-ips-table');
        if (data.top_ips.length === 0) {
            topTbody.innerHTML =
                '<tr><td colspan="3" class="empty">' +
                'Waiting for traffic...</td></tr>';
        } else {
            const maxCount = data.top_ips[0][1];
            topTbody.innerHTML = data.top_ips.map(([ip, count]) => {
                const pct = maxCount > 0
                    ? Math.round((count / maxCount) * 200)
                    : 0;
                return `
                    <tr>
                        <td><code>${ip}</code></td>
                        <td>${count.toLocaleString()}</td>
                        <td>
                            <div class="ip-bar-wrap">
                                <div class="ip-bar"
                                     style="width:${pct}px">
                                </div>
                                <span style="font-size:12px;
                                             color:#718096">
                                    ${count}
                                </span>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Last updated
        document.getElementById('last-updated').textContent =
            'Last updated: ' + new Date().toLocaleTimeString();
    }

    // Start fetching immediately then every 3 seconds
    fetchMetrics();
    setInterval(fetchMetrics, 3000);
</script>

</body>
</html>
"""


class Dashboard:
    """
    Serves a live metrics web UI on port 8080.
    Exposes /api/metrics as JSON for the frontend to consume.
    Runs in a background thread so it does not block the main loop.
    """

    def __init__(self, config, baseline, detector, blocker):
        self.port = config["dashboard"]["port"]
        self.baseline = baseline
        self.detector = detector
        self.blocker = blocker
        self.start_time = time.time()

        self.app = Flask(__name__)
        self._register_routes()

    def _register_routes(self):
        """Register Flask URL routes."""

        @self.app.route("/")
        def index():
            return render_template_string(HTML)

        @self.app.route("/api/metrics")
        def metrics():
            return jsonify(self._collect_metrics())

        @self.app.route("/baseline-graph")
        def baseline_graph():
            return render_template_string(BASELINE_HTML)

        @self.app.route("/api/baseline-history")
        def baseline_history():
            return jsonify(self._collect_baseline_history())

    def _collect_baseline_history(self):
        """
        Return hourly baseline slots for the graph.
        """
        stats = self.baseline.get_stats()
        hourly = stats.get("hourly_slots", {})

        slots = []
        for hour, data in sorted(hourly.items()):
            slots.append({
                "hour": f"{int(hour):02d}:00",
                "mean": round(data["mean"], 2),
                "stddev": round(data["stddev"], 2),
                "count": data["count"]
            })

        return {
            "slots": slots,
            "effective_mean": stats["effective_mean"],
            "effective_stddev": stats["effective_stddev"]
        }


    def _collect_metrics(self):
        """
        Collect all metrics from the other components
        and return as a dictionary.
        """
        # Uptime calculation
        elapsed = int(time.time() - self.start_time)
        hours   = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        uptime  = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        baseline_stats = self.baseline.get_stats()

        return {
            "global_rate":      self.detector.get_global_rate(),
            "banned_count":     len(self.blocker.active_bans),
            "banned_ips":       self.blocker.get_active_bans(),
            "top_ips":          self.detector.get_top_ips(10),
            "baseline_mean":    baseline_stats["effective_mean"],
            "baseline_stddev":  baseline_stats["effective_stddev"],
            "cpu_percent":      psutil.cpu_percent(interval=None),
            "memory_percent":   psutil.virtual_memory().percent,
            "uptime":           uptime,
            "total_requests":   baseline_stats["total_requests"],
        }

    def start(self):
        """Start Flask in a background thread."""
        self.thread = threading.Thread(
            target=lambda: self.app.run(
                host="0.0.0.0",
                port=self.port,
                debug=False,
                use_reloader=False
            ),
            daemon=True,
            name="dashboard-thread"
        )
        self.thread.start()
        print(f"[dashboard] Running at http://0.0.0.0:{self.port}")
