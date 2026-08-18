"""Entry point. Pins cwd to this script's folder so auto-start (or any
launch method) can't break relative paths (.env, config.yaml, logs)."""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

from tether.bot import main

if __name__ == "__main__":
    main()
