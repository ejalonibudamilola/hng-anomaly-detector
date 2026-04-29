# HNG Anomaly Detection Engine

A real-time DDoS and anomaly detection daemon built for HNG's cloud.ng
Nextcloud platform, powered by Nginx JSON logs, Python, iptables, and Slack.

## Server IP
3.87.99.128

## Dashboard URL
http://hng-detector.damiloladeborah.link:8080

## Language choice
Python — chosen for readability, fast iteration, and strong standard
library support for threading, subprocess, and collections.

## How the sliding window works
Two deque-based windows track requests — one global, one per IP.
Every second, the current count is appended to the right of the deque.
Entries older than 60 seconds are evicted from the left.
This means the deque always contains exactly the last 60 seconds of data.
The average of all values in the deque gives the current rate per second.

## How the baseline works
A rolling 30-minute window of per-second counts is maintained.
Every 60 seconds, mean and stddev are recalculated from this window.
Results are stored in per-hour slots (e.g. hour 15, hour 16).
The current hour's slot is preferred when it has enough data.
Floor values of mean=1.0 and stddev=0.5 prevent division by zero.

## Setup instructions

### Requirements
- Ubuntu 22.04 VPS, minimum 2 vCPU 2GB RAM
- Docker and docker-compose installed
- Python 3.11+

### Steps
```bash
# Clone the repo
git clone https://github.com/ejalonibudamilola/hng-anomaly-detector.git
cd hng-anomaly-detector

# Create your .env file
cp .env.example .env
nano .env  # fill in your credentials

# Start the stack
docker compose up -d

# Install Python dependencies
pip3 install -r detector/requirements.txt --break-system-packages

# Run the detector
cd detector
sudo python3 main.py
```

## Repository structure

https://github.com/ejalonibudamilola/hng-anomaly-detector.git


## Blog post

https://dev.to/damilola_ejalonibu_7f5cfd/how-i-built-a-real-time-ddos-detection-engine-from-scratch-54f4