import time
import threading


class Unbanner:
    """
    Runs in a background thread.
    Checks every 30 seconds if any banned IP is due for release.
    Follows the backoff schedule: 10min, 30min, 2hrs, permanent.
    Sends a Slack notification on every unban.
    """

    def __init__(self, config, blocker, detector, notifier):
        # Backoff schedule in minutes
        self.unban_schedule = config["blocking"]["unban_schedule"]

        # References to other components
        self.blocker = blocker
        self.detector = detector
        self.notifier = notifier

        # How often to check for expired bans (seconds)
        self.check_interval = 30

        # Track offense counts per IP across bans
        # Key: ip, Value: int (number of times banned)
        self.offense_counts = {}

        # Running flag — set to False to stop the thread
        self.running = False

        # Background thread
        self.thread = None

    def start(self):
        """Start the unbanner background thread."""
        self.running = True
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="unbanner-thread"
        )
        self.thread.start()
        print("[unbanner] Background thread started")

    def stop(self):
        """Stop the unbanner background thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[unbanner] Stopped")

    def _run(self):
        """
        Main loop — runs every check_interval seconds.
        Checks all active bans and releases expired ones.
        """
        while self.running:
            try:
                self._check_bans()
            except Exception as e:
                print(f"[unbanner] Error during check: {e}")

            time.sleep(self.check_interval)

    def _check_bans(self):
        """
        Go through all active bans and unban any that have expired.
        Permanent bans (duration = -1) are never released.
        """
        now = time.time()

        # Get a copy of active bans to avoid modifying
        # the dict while iterating
        active_bans = dict(self.blocker.active_bans)

        for ip, ban_info in active_bans.items():
            duration = ban_info["duration"]

            # Permanent ban — never release
            if duration == -1:
                continue

            # Calculate when this ban should expire
            banned_at = ban_info["banned_at"]
            expires_at = banned_at + (duration * 60)

            # Not expired yet — skip
            if now < expires_at:
                remaining = int((expires_at - now) / 60)
                print(
                    f"[unbanner] {ip} still banned — "
                    f"{remaining} min remaining"
                )
                continue

            # Ban has expired — unban the IP
            print(f"[unbanner] Ban expired for {ip} — unbanning")
            self._unban_ip(ip, ban_info)

    def _unban_ip(self, ip, ban_info):
        """
        Unban an IP, update offense count, notify Slack.
        """
        # Increment offense count for this IP
        self.offense_counts[ip] = self.offense_counts.get(ip, 0) + 1
        offense = self.offense_counts[ip]

        # Tell the blocker to remove the iptables rule
        success = self.blocker.unban(ip)

        if not success:
            print(f"[unbanner] Failed to unban {ip}")
            return

        # Tell the detector to start processing this IP again
        self.detector.remove_banned_ip(ip)

        # Calculate what the NEXT ban duration will be
        # if this IP attacks again
        if offense < len(self.unban_schedule):
            next_duration = self.unban_schedule[offense]
            next_label = f"{next_duration} min"
        else:
            next_duration = -1
            next_label = "permanent"

        duration_label = (
            f"{ban_info['duration']} min"
            if ban_info["duration"] > 0
            else "permanent"
        )

        print(
            f"[unbanner] {ip} unbanned after {duration_label} | "
            f"offense #{offense} | "
            f"next ban if reoffends: {next_label}"
        )

        # Send Slack notification
        self.notifier.send_unban_alert(
            ip=ip,
            duration=duration_label,
            offense=offense,
            next_duration=next_label,
            condition=ban_info.get("condition", "unknown"),
            rate=ban_info.get("rate", 0),
            baseline=ban_info.get("baseline", 0)
        )

    def register_reoffense(self, ip):
        """
        Called by the detector when a previously banned IP
        attacks again after being unbanned.
        Updates offense count so next ban is longer.
        """
        current = self.offense_counts.get(ip, 0)
        self.offense_counts[ip] = current + 1

        offense = self.offense_counts[ip]

        if offense < len(self.unban_schedule):
            next_duration = self.unban_schedule[offense]
            return next_duration
        else:
            return -1

    def get_offense_count(self, ip):
        """Return how many times an IP has been banned."""
        return self.offense_counts.get(ip, 0)
