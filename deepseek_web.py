#!/usr/bin/env python3
"""
DeepSeek Web launcher for Cassandra.

The main CLI historically required CASSANDRA_API_KEY even when the selected
backend was the browser-authenticated DeepSeek Web client. This launcher marks
the legacy API-key check as satisfied with a local sentinel value, while the
actual chat transport still uses the saved DeepSeek Web session.

It does not solve, bypass, or automate CAPTCHA challenges.
"""

import os

# agent.py only uses this variable for its legacy startup guard and --poll mode.
# Normal DeepSeek Web chat continues through deepseek.client.
os.environ.setdefault("CASSANDRA_API_KEY", "deepseek-web-session")

import agent


if __name__ == "__main__":
    agent.main()
