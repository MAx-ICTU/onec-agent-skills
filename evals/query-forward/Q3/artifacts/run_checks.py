"""Run the saved model and preserve its actual output and exit status."""
import json
import subprocess
import sys
from pathlib import Path

artifacts = Path(__file__).resolve().parent
command = [sys.executable, str(artifacts / "check_model.py")]
result = subprocess.run(command, cwd=artifacts, capture_output=True)
stdout = result.stdout.decode("utf-8", errors="strict")
stderr = result.stderr.decode("utf-8", errors="strict")
(artifacts / "checks.txt").write_text(
    "Runner: run_checks.py (saved exact source)\n"
    "Model: check_model.py (saved exact source)\n"
    "Executed child command argv (shell=False): " + json.dumps(command) + "\n"
    "Working directory: " + str(artifacts) + "\n"
    "--- actual stdout ---\n" + stdout +
    "--- actual stderr ---\n" + stderr +
    "--- exit code ---\n" + str(result.returncode) + "\n",
    encoding="utf-8",
)
sys.stdout.write(stdout)
sys.stderr.write(stderr)
raise SystemExit(result.returncode)
