import json
import time
import os


def tail_log(log_path):
    """
    Continuously tail the nginx log file line by line.
    Yields each parsed JSON log entry as a dictionary.
    Handles file rotation and missing file gracefully.
    """
    # Wait until the log file exists before starting
    while not os.path.exists(log_path):
        print(f"[monitor] Waiting for log file at {log_path} ...")
        time.sleep(2)

    print(f"[monitor] Log file found. Starting to tail: {log_path}")

    with open(log_path, "r") as f:
        # Move to the end of the file so we only read NEW lines
        f.seek(0, 2)

        while True:
            line = f.readline()

            if not line:
                # No new line yet — wait a little and try again
                time.sleep(0.1)
                continue

            line = line.strip()

            if not line:
                continue

            # Parse the JSON log line
            entry = parse_line(line)

            if entry:
                yield entry


def parse_line(line):
    """
    Parse a single JSON log line from Nginx.
    Returns a dictionary or None if the line is invalid.

    Expected fields:
        source_ip, timestamp, method, path,
        status, response_size
    """
    try:
        entry = json.loads(line)

        # Make sure all required fields are present
        required = ["source_ip", "timestamp", "method",
                    "path", "status", "response_size"]

        for field in required:
            if field not in entry:
                print(f"[monitor] Missing field '{field}' in log line")
                return None

        # Convert types to make sure they are correct
        entry["status"] = int(entry["status"])
        entry["response_size"] = int(entry["response_size"])

        # Clean up source_ip — X-Forwarded-For can contain
        # multiple IPs like "1.2.3.4, 5.6.7.8"
        # We only want the first one (the real client IP)
        raw_ip = entry["source_ip"]
        if raw_ip and "," in raw_ip:
            entry["source_ip"] = raw_ip.split(",")[0].strip()

        # If source_ip is empty or "-", fall back to a label
        if not entry["source_ip"] or entry["source_ip"] == "-":
            entry["source_ip"] = "unknown"

        return entry

    except json.JSONDecodeError:
        # Line was not valid JSON — skip it silently
        return None

    except Exception as e:
        print(f"[monitor] Error parsing line: {e}")
        return None
