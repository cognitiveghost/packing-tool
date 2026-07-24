#!/usr/bin/env python3
"""Local dev runner: launches Packer's Assistant against the shared dev-server
used by shopify-fulfillment-tool (sibling repo), instead of the production
network share in config.ini.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DEV_SERVER = ROOT.parent / "shopify-fulfillment-tool" / "dev-server"
CONFIG_DEV = ROOT / "config.dev.ini"

if not DEV_SERVER.is_dir():
    sys.exit(
        f"Dev server not found at {DEV_SERVER}\n"
        "Run shopify-fulfillment-tool's run_dev.py first to create it."
    )

CONFIG_DEV.write_text(f"""[Network]
FileServerPath = {DEV_SERVER}
ConnectionTimeout = 5
LocalCachePath =

[Logging]
LogLevel = INFO
LogRetentionDays = 30
MaxLogSizeMB = 10

[General]
Environment = development
DebugMode = true

[UI]
RememberLastClient = true
AutoRefreshInterval = 0
""")

if __name__ == "__main__":
    subprocess.run(
        [sys.executable, str(ROOT / "src" / "main.py"), "--config", str(CONFIG_DEV)]
    )
