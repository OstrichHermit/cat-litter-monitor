"""Kill all cat-litter-monitor related Python processes.

Usage:
    python kill_monitor.py              # kill all
    python kill_monitor.py main manager # skip processes matching these strings
"""
import subprocess
import sys


def main():
    excludes = sys.argv[1:]

    result = subprocess.run(
        ["wmic", "process", "where",
         "name='python.exe' or name='pythonw.exe'",
         "get", "processid,commandline", "/format:csv"],
        capture_output=True, text=True
    )

    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if "cat-litter-monitor" not in line:
            continue
        if any(exc in line for exc in excludes):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3 and parts[2].isdigit():
            pid = int(parts[2])
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True
                )
            except Exception:
                pass


if __name__ == "__main__":
    main()
