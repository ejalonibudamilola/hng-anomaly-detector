import time
import requests


class Notifier:
    """
    Sends Slack webhook alerts for ban, unban, and global
    anomaly events. All alerts include condition, rate,
    baseline, timestamp, and ban duration where applicable.
    """

    def __init__(self, config):
        self.webhook_url = config["slack"]["webhook_url"]

        # Track last alert time per IP to avoid spam
        # Key: ip, Value: timestamp of last alert
        self.last_alert = {}

        # Minimum seconds between alerts for the same IP
        self.cooldown = 60

    def send_ban_alert(self, ip, condition, rate, baseline, duration):
        """
        Send a Slack alert when an IP is banned.
        Must be called within 10 seconds of detection.

        duration is in minutes, or -1 for permanent.
        """
        # Check cooldown to avoid spamming
        now = time.time()
        if ip in self.last_alert:
            if now - self.last_alert[ip] < self.cooldown:
                return
        self.last_alert[ip] = now

        duration_label = (
            f"{duration} minutes" if duration > 0 else "PERMANENT"
        )

        message = {
            "text": "🚨 *IP BANNED — Anomaly Detected*",
            "attachments": [
                {
                    "color": "#FF0000",
                    "fields": [
                        {
                            "title": "Banned IP",
                            "value": f"`{ip}`",
                            "short": True
                        },
                        {
                            "title": "Ban Duration",
                            "value": duration_label,
                            "short": True
                        },
                        {
                            "title": "Condition Fired",
                            "value": condition,
                            "short": False
                        },
                        {
                            "title": "Current Rate",
                            "value": f"{rate:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Baseline Mean",
                            "value": f"{baseline:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "short": False
                        }
                    ],
                    "footer": "HNG Anomaly Detector"
                }
            ]
        }

        self._send(message)

    def send_unban_alert(
        self, ip, duration, offense, next_duration, condition, rate, baseline
    ):
        """
        Send a Slack alert when an IP is unbanned.
        Includes how many times this IP has offended and
        what the next ban duration will be if it reoffends.
        """
        message = {
            "text": "✅ *IP UNBANNED*",
            "attachments": [
                {
                    "color": "#36A64F",
                    "fields": [
                        {
                            "title": "Unbanned IP",
                            "value": f"`{ip}`",
                            "short": True
                        },
                        {
                            "title": "Served Duration",
                            "value": duration,
                            "short": True
                        },
                        {
                            "title": "Total Offenses",
                            "value": str(offense),
                            "short": True
                        },
                        {
                            "title": "Next Ban If Reoffends",
                            "value": next_duration,
                            "short": True
                        },
                        {
                            "title": "Original Condition",
                            "value": condition,
                            "short": False
                        },
                        {
                            "title": "Original Rate",
                            "value": f"{rate:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Baseline At Time Of Ban",
                            "value": f"{baseline:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "short": False
                        }
                    ],
                    "footer": "HNG Anomaly Detector"
                }
            ]
        }

        self._send(message)

    def send_global_alert(self, condition, rate, baseline):
        """
        Send a Slack alert for a global traffic spike.
        No IP ban is issued — Slack alert only.
        """
        # Use a fixed key for global alerts cooldown
        now = time.time()
        if "global" in self.last_alert:
            if now - self.last_alert["global"] < self.cooldown:
                return
        self.last_alert["global"] = now

        message = {
            "text": "⚠️ *GLOBAL TRAFFIC ANOMALY DETECTED*",
            "attachments": [
                {
                    "color": "#FF8C00",
                    "fields": [
                        {
                            "title": "Condition Fired",
                            "value": condition,
                            "short": False
                        },
                        {
                            "title": "Global Rate",
                            "value": f"{rate:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Baseline Mean",
                            "value": f"{baseline:.2f} req/s",
                            "short": True
                        },
                        {
                            "title": "Action Taken",
                            "value": "Slack alert only — "
                                     "no single IP responsible",
                            "short": False
                        },
                        {
                            "title": "Timestamp",
                            "value": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "short": False
                        }
                    ],
                    "footer": "HNG Anomaly Detector"
                }
            ]
        }

        self._send(message)

    def _send(self, message):
        """
        Send a message to the Slack webhook.
        Handles errors gracefully so a Slack failure never
        crashes the main detector loop.
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                timeout=5
            )

            if response.status_code != 200:
                print(
                    f"[notifier] Slack returned {response.status_code}: "
                    f"{response.text}"
                )
            else:
                print("[notifier] Slack alert sent successfully")

        except requests.exceptions.Timeout:
            print("[notifier] Slack webhook timed out")

        except requests.exceptions.ConnectionError:
            print("[notifier] Could not connect to Slack webhook")

        except Exception as e:
            print(f"[notifier] Unexpected error sending alert: {e}")
