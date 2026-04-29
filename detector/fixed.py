import time
import subprocess
import os


class Blocker:
    """
    Manages iptables bans for anomalous IPs.
    Records ban time and offense count for the unbanner.
    Writes structured audit log entries for every ban.
    """

    def __init__(self, config):
        # Backoff schedule in minutes from config
        self.unban_schedule = config["blocking"]["unban_schedule"]

        # Audit log path
        self.audit_path = config["audit"]["log_path"]

        # Active bans
        # Key: ip
        # Value: {
        #   "banned_at": timestamp,
        #   "offense": int,
        #   "duration": int (minutes),
        #   "condition": str,
        #   "rate": float,
        #   "baseline": float
        # }
        self.active_bans = {}

    def ban(self, ip, condition, rate, baseline):
        """
        Ban an IP using iptables DROP rule.
        Called within 10 seconds of anomaly detection.

        Returns ban duration in minutes, or None if already banned.
        """
        # Skip if already banned
        if ip in self.active_bans:
            return None

        # Skip private/internal IPs — never ban localhost or
        # internal Docker network addresses
        if self._is_private(ip):
            print(f"[blocker] Skipping private IP: {ip}")
            return None

        # Determine ban duration based on offense count
        offense = self._get_offense_count(ip)
        if offense < len(self.unban_schedule):
            duration = self.unban_schedule[offense]
        else:
            # Permanent ban — no more chances
            duration = -1

        # Add iptables rule
        success = self._add_iptables_rule(ip)

        if not success:
            print(f"[blocker] Failed to add iptables rule for {ip}")
            return None

        # Record the ban
        self.active_bans[ip] = {
            "banned_at": time.time(),
            "offense": offense,
            "duration": duration,
            "condition": condition,
            "rate": rate,
            "baseline": baseline
        }

        duration_label = (
            f"{duration} min" if duration > 0 else "permanent"
        )

        print(
            f"[blocker] Banned {ip} | "
            f"condition: {condition} | "
            f"duration: {duration_label}"
        )

        # Write audit log
        self._audit_log(
            action="BAN",
            ip=ip,
            condition=condition,
            rate=rate,
            baseline=baseline,
            duration=duration_label
        )

        return duration

    def unban(self, ip):
        """
        Remove iptables rule and clear ban record.
        Called by the unbanner on schedule.
        """
        if ip not in self.active_bans:
            return False

        ban_info = self.active_bans[ip]

        # Remove iptables rule
        success = self._remove_iptables_rule(ip)

        if not success:
            print(f"[blocker] Failed to remove iptables rule for {ip}")
            return False

        # Remove from active bans
        del self.active_bans[ip]

        duration_label = (
            f"{ban_info['duration']} min"
            if ban_info["duration"] > 0
            else "permanent"
        )

        print(f"[blocker] Unbanned {ip}")

        # Write audit log
        self._audit_log(
            action="UNBAN",
            ip=ip,
            condition=ban_info["condition"],
            rate=ban_info["rate"],
            baseline=ban_info["baseline"],
            duration=duration_label
        )

        return True

    def _add_iptables_rule(self, ip):
        """
        Add an iptables DROP rule for the given IP.
        Requires root/sudo privileges.
        """
        try:
            subprocess.run(
                ["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"],
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"[blocker] iptables error: {e.stderr.decode()}")
            return False
        except FileNotFoundError:
            print("[blocker] iptables not found — are you running as root?")
            return False

    def _remove_iptables_rule(self, ip):
        """
        Remove the iptables DROP rule for the given IP.
        """
        try:
            subprocess.run(
                ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"[blocker] iptables remove error: {e.stderr.decode()}")
            return False
        except FileNotFoundError:
            print("[blocker] iptables not found")
            return False

    def _get_offense_count(self, ip):
        """
        Return how many times this IP has been banned before.
        For now returns 0 — in a production system this would
        persist to disk across restarts.
        """
        return 0

    def _is_private(self, ip):
        """
        Return True if the IP is a private/internal address.
        We never want to ban localhost or Docker internal IPs.
        """

     private_prefixes = (
            "127.",
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "192.168.",
            "::1",
            "unknown"
         )

        return ip.startswith(private_prefixes)

    def _audit_log(self, action, ip, condition, rate, baseline, duration):
        """
        Write a structured audit log entry.
        Format: [timestamp] ACTION ip | condition | rate | baseline | duration
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = (
            f"[{timestamp}] {action} {ip} | "
            f"{condition} | "
            f"rate={rate:.2f} | "
            f"baseline={baseline:.2f} | "
            f"{duration}\n"
        )

        # Make sure the audit log directory exists
        os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)

        try:
            with open(self.audit_path, "a") as f:
                f.write(line)
        except Exception as e:
            print(f"[blocker] Could not write audit log: {e}")

    def get_active_bans(self):
        """
        Return list of active bans for the dashboard.
        """
        bans = []
        now = time.time()
        for ip, info in self.active_bans.items():
            elapsed = int(now - info["banned_at"])
            bans.append({
                "ip": ip,
                "banned_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S",
                    time.localtime(info["banned_at"])
                ),
                "duration": info["duration"],
                "elapsed_seconds": elapsed,
                "condition": info["condition"],
                "offense": info["offense"]
            })
        return bans
