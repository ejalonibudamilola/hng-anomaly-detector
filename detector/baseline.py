import time
import math
from collections import deque


class Baseline:
    """
    Tracks per-second request counts over a rolling 30-minute window.
    Recalculates mean and stddev every 60 seconds.
    Maintains per-hour slots and prefers the current hour's data
    when it has enough samples.
    """

    def __init__(self, config):
        # How many seconds to keep in the rolling window (30 min = 1800s)
        self.window_size = config["baseline"]["window_minutes"] * 60

        # How often to recalculate mean and stddev (every 60 seconds)
        self.recalc_interval = config["baseline"]["recalc_interval"]

        # Minimum number of requests before we trust the baseline
        self.min_requests = config["baseline"]["min_requests"]

        # Floor values — prevent mean/stddev from being zero
        self.floor_mean = config["baseline"]["floor_mean"]
        self.floor_stddev = config["baseline"]["floor_stddev"]

        # Rolling window of (timestamp, count) tuples
        # Each entry represents one second's request count
        self.window = deque()

        # Per-hour slots — store mean/stddev for each hour of the day
        # Key: hour (0-23), Value: {"mean": float, "stddev": float, "count": int}
        self.hourly_slots = {}

        # Current effective mean and stddev used by detector
        self.effective_mean = self.floor_mean
        self.effective_stddev = self.floor_stddev

        # Track requests in the current second
        self.current_second = int(time.time())
        self.current_count = 0

        # When we last recalculated
        self.last_recalc = time.time()

        # Total requests seen so far
        self.total_requests = 0

        # Per-second error counts for error surge detection
        self.error_window = deque()
        self.current_error_count = 0
        self.effective_error_mean = self.floor_mean
        self.effective_error_stddev = self.floor_stddev

    def record(self, entry):
        """
        Record one incoming request from the log monitor.
        Called for every log line parsed.
        """
        now = int(time.time())
        self.total_requests += 1

        # If we have moved into a new second, save the previous second's count
        if now != self.current_second:
            self._flush_current_second()
            self.current_second = now
            self.current_count = 0
            self.current_error_count = 0

        self.current_count += 1

        # Track error requests (4xx and 5xx status codes)
        status = entry.get("status", 0)
        if status >= 400:
            self.current_error_count += 1

        # Recalculate baseline every recalc_interval seconds
        if time.time() - self.last_recalc >= self.recalc_interval:
            self._recalculate()
            self.last_recalc = time.time()

    def _flush_current_second(self):
        """
        Save the current second's count into the rolling window.
        Evict entries older than window_size seconds.
        """
        now = int(time.time())
        timestamp = self.current_second

        # Add current second to window
        self.window.append((timestamp, self.current_count))
        self.error_window.append((timestamp, self.current_error_count))

        # Evict old entries from the LEFT of the deque
        # The deque is ordered oldest → newest
        # We remove from the left until all entries are within window_size
        cutoff = now - self.window_size
        while self.window and self.window[0][0] < cutoff:
            self.window.popleft()

        while self.error_window and self.error_window[0][0] < cutoff:
            self.error_window.popleft()

    def _recalculate(self):
        """
        Recalculate mean and stddev from the rolling window.
        Update hourly slots with current hour's data.
        Prefer current hour's baseline when it has enough data.
        """
        if not self.window:
            return

        counts = [count for _, count in self.window]
        total = sum(counts)

        # Not enough data yet — keep floor values
        if total < self.min_requests:
            return

        # Calculate mean
        mean = total / len(counts)

        # Calculate standard deviation manually (no libraries allowed)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        stddev = math.sqrt(variance)

        # Apply floor values
        mean = max(mean, self.floor_mean)
        stddev = max(stddev, self.floor_stddev)

        # Update current hour's slot
        current_hour = int(time.strftime("%H"))
        self.hourly_slots[current_hour] = {
            "mean": mean,
            "stddev": stddev,
            "count": total
        }

        # Use current hour's baseline if it has enough data
        # Otherwise fall back to the rolling window baseline
        if total >= self.min_requests * 10:
            self.effective_mean = mean
            self.effective_stddev = stddev
        elif current_hour in self.hourly_slots:
            slot = self.hourly_slots[current_hour]
            self.effective_mean = slot["mean"]
            self.effective_stddev = slot["stddev"]
        else:
            self.effective_mean = mean
            self.effective_stddev = stddev

        # Recalculate error baseline too
        error_counts = [count for _, count in self.error_window]
        if error_counts:
            error_mean = sum(error_counts) / len(error_counts)
            error_variance = sum(
                (c - error_mean) ** 2 for c in error_counts
            ) / len(error_counts)
            error_stddev = math.sqrt(error_variance)
            self.effective_error_mean = max(error_mean, self.floor_mean)
            self.effective_error_stddev = max(
                error_stddev, self.floor_stddev
            )

        # Write to audit log
        self._audit_log(mean, stddev)

    def _audit_log(self, mean, stddev):
        """
        Write a structured audit log entry for this recalculation.
        Format: [timestamp] ACTION ip | condition | rate | baseline | duration
        """
        import yaml
        try:
            with open("config.yaml") as f:
                config = yaml.safe_load(f)
            audit_path = config["audit"]["log_path"]
        except Exception:
            audit_path = "/app/audit.log"

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = (
            f"[{timestamp}] BASELINE_RECALC - | "
            f"rolling_window | "
            f"mean={mean:.2f} stddev={stddev:.2f} | "
            f"samples={len(self.window)} | -\n"
        )
        try:
            with open(audit_path, "a") as f:
                f.write(line)
        except Exception as e:
            print(f"[baseline] Could not write audit log: {e}")

    def get_window_rate(self):
        """
        Return the current request rate per second
        based on the sliding window.
        """
        if not self.window:
            return 0.0
        counts = [count for _, count in self.window]
        return sum(counts) / len(counts)

    def get_stats(self):
        """
        Return current baseline stats for the dashboard.
        """
        return {
            "effective_mean": round(self.effective_mean, 2),
            "effective_stddev": round(self.effective_stddev, 2),
            "effective_error_mean": round(self.effective_error_mean, 2),
            "window_size": len(self.window),
            "total_requests": self.total_requests,
            "hourly_slots": self.hourly_slots,
        }
