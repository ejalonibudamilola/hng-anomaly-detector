import time
from collections import deque, defaultdict


class Detector:
    """
    Detects anomalies using two deque-based sliding windows:
    - One global window tracking total requests per second
    - One per-IP window tracking each IP's requests per second

    Fires if z-score exceeds threshold OR rate exceeds
    rate_multiplier times the baseline mean.
    """

    def __init__(self, config, baseline):
        # Store reference to baseline so we can read mean/stddev
        self.baseline = baseline

        # Detection thresholds from config
        self.zscore_threshold = config["detection"]["zscore_threshold"]
        self.rate_multiplier = config["detection"]["rate_multiplier"]
        self.error_rate_multiplier = config["detection"]["error_rate_multiplier"]

        # Sliding window size in seconds
        self.window_size = config["window"]["size_seconds"]

        # Global sliding window — tracks (timestamp, count) per second
        self.global_window = deque()
        self.global_current_second = int(time.time())
        self.global_current_count = 0

        # Per-IP sliding windows
        # Key: ip address
        # Value: deque of (timestamp, count) tuples
        self.ip_windows = defaultdict(deque)
        self.ip_current_second = defaultdict(lambda: int(time.time()))
        self.ip_current_count = defaultdict(int)

        # Per-IP error tracking
        self.ip_error_windows = defaultdict(deque)
        self.ip_current_error_count = defaultdict(int)

        # Top IPs tracker — stores total request count per IP
        self.ip_totals = defaultdict(int)

        # Currently banned IPs — set of IP strings
        self.banned_ips = set()

    def record(self, entry):
        """
        Record one request. Updates both global and per-IP windows.
        Returns a tuple: (anomaly_type, ip, rate, reason) or None.

        anomaly_type is one of: "ip", "global", None
        """
        now = int(time.time())
        ip = entry.get("source_ip", "unknown")
        status = entry.get("status", 0)

        # Skip already banned IPs
        if ip in self.banned_ips:
            return None

        # Update IP total counter
        self.ip_totals[ip] += 1

        # ── Update global window ──────────────────────────────
        if now != self.global_current_second:
            self._flush_global(now)

        self.global_current_count += 1

        # ── Update per-IP window ──────────────────────────────
        if now != self.ip_current_second[ip]:
            self._flush_ip(ip, now)

        self.ip_current_count[ip] += 1

        # Track per-IP errors
        if status >= 400:
            self.ip_current_error_count[ip] += 1

        # ── Check for anomalies ───────────────────────────────
        # Check per-IP anomaly first
        ip_anomaly = self._check_ip(ip)
        if ip_anomaly:
            return ("ip", ip, ip_anomaly["rate"], ip_anomaly["reason"])

        # Check global anomaly
        global_anomaly = self._check_global()
        if global_anomaly:
            return (
                "global",
                None,
                global_anomaly["rate"],
                global_anomaly["reason"]
            )

        return None

    def _flush_global(self, now):
        """
        Save current second's global count to the window.
        Evict entries older than window_size seconds.
        """
        self.global_window.append(
            (self.global_current_second, self.global_current_count)
        )

        # Evict old entries from the left
        cutoff = now - self.window_size
        while self.global_window and self.global_window[0][0] < cutoff:
            self.global_window.popleft()

        self.global_current_second = now
        self.global_current_count = 0

    def _flush_ip(self, ip, now):
        """
        Save current second's IP count to that IP's window.
        Evict entries older than window_size seconds.
        """
        self.ip_windows[ip].append(
            (self.ip_current_second[ip], self.ip_current_count[ip])
        )

        # Evict old entries from the left
        cutoff = now - self.window_size
        while self.ip_windows[ip] and self.ip_windows[ip][0][0] < cutoff:
            self.ip_windows[ip].popleft()

        # Same for error window
        self.ip_error_windows[ip].append(
            (self.ip_current_second[ip], self.ip_current_error_count[ip])
        )
        while (self.ip_error_windows[ip] and
               self.ip_error_windows[ip][0][0] < cutoff):
            self.ip_error_windows[ip].popleft()

        self.ip_current_second[ip] = now
        self.ip_current_count[ip] = 0
        self.ip_current_error_count[ip] = 0

    def _get_rate(self, window):
        """
        Calculate average requests per second from a window.
        """
        if not window:
            return 0.0
        counts = [count for _, count in window]
        return sum(counts) / len(counts)

    def _get_zscore(self, rate):
        """
        Calculate z-score for a given rate against the baseline.
        z = (current_rate - mean) / stddev
        """
        mean = self.baseline.effective_mean
        stddev = self.baseline.effective_stddev

        # Avoid division by zero
        if stddev == 0:
            stddev = self.baseline.floor_stddev

        return (rate - mean) / stddev

    def _check_ip(self, ip):
        """
        Check if a single IP's request rate is anomalous.
        Also checks error surge — tightens threshold if
        error rate is 3x the baseline error mean.
        Returns dict with rate and reason, or None.
        """
        window = self.ip_windows[ip]
        rate = self._get_rate(window)

        if rate == 0:
            return None

        mean = self.baseline.effective_mean
        zscore = self._get_zscore(rate)

        # Check if this IP has an error surge
        # If so, tighten the zscore threshold by 1.0
        error_window = self.ip_error_windows[ip]
        error_rate = self._get_rate(error_window)
        error_mean = self.baseline.effective_error_mean
        tightened = False

        if error_mean > 0 and error_rate >= (
            self.error_rate_multiplier * error_mean
        ):
            tightened = True

        # Use tightened threshold if error surge detected
        threshold = self.zscore_threshold
        if tightened:
            threshold = max(1.0, self.zscore_threshold - 1.0)

        # Fire if z-score exceeds threshold
        if zscore > threshold:
            reason = (
                f"zscore={zscore:.2f} > {threshold:.1f}"
                f"{' (tightened due to error surge)' if tightened else ''}"
            )
            return {"rate": rate, "reason": reason}

        # Fire if rate is more than rate_multiplier times the mean
        if mean > 0 and rate >= (self.rate_multiplier * mean):
            reason = (
                f"rate={rate:.2f} >= "
                f"{self.rate_multiplier}x mean={mean:.2f}"
            )
            return {"rate": rate, "reason": reason}

        return None

    def _check_global(self):
        """
        Check if global request rate is anomalous.
        Returns dict with rate and reason, or None.
        """
        rate = self._get_rate(self.global_window)

        if rate == 0:
            return None

        mean = self.baseline.effective_mean
        zscore = self._get_zscore(rate)

        # Fire if z-score exceeds threshold
        if zscore > self.zscore_threshold:
            reason = (
                f"global zscore={zscore:.2f} "
                f"> {self.zscore_threshold}"
            )
            return {"rate": rate, "reason": reason}

        # Fire if rate is more than rate_multiplier times the mean
        if mean > 0 and rate >= (self.rate_multiplier * mean):
            reason = (
                f"global rate={rate:.2f} >= "
                f"{self.rate_multiplier}x mean={mean:.2f}"
            )
            return {"rate": rate, "reason": reason}

        return None

    def add_banned_ip(self, ip):
        """Mark an IP as banned so we stop processing its requests."""
        self.banned_ips.add(ip)

    def remove_banned_ip(self, ip):
        """Remove an IP from the banned set when it is unbanned."""
        self.banned_ips.discard(ip)

    def get_top_ips(self, n=10):
        """
        Return top N IPs by total request count.
        Used by the dashboard.
        """
        sorted_ips = sorted(
            self.ip_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_ips[:n]

    def get_global_rate(self):
        """Return current global requests per second."""
        return round(self._get_rate(self.global_window), 2)
