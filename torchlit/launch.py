import os
import subprocess
import sys
from pathlib import Path


def launch_web(
    *,
    run_root: str = "runs",
    host: str = "127.0.0.1",
    port: int = 8501,
    open_browser: bool = True,
    wait: bool = True,
) -> int | subprocess.Popen[str]:
    app_path = Path(__file__).resolve().parent / "web" / "Home.py"
    env = os.environ.copy()
    env["TORCHLIT_RUN_ROOT"] = str(Path(run_root).expanduser().resolve())

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        str(host),
        "--server.port",
        str(port),
        "--server.headless",
        "false" if open_browser else "true",
    ]

    if wait:
        completed = subprocess.run(cmd, env=env, check=False)
        return int(completed.returncode)

    return subprocess.Popen(cmd, env=env, text=True)
