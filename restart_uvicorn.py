#!/usr/bin/env python3
import subprocess, os, time, signal

def main():
    # Kill existing
    subprocess.run(["pkill", "-f", "uvicorn main:app --host 0.0.0.0 --port 3456"])
    time.sleep(1)
    # Start fresh in detached session
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3456"],
        cwd="/home/administrator/github/johncolling/thumbtack",
        stdout=open("/tmp/uvicorn.out", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env
    )
    print(f"Started uvicorn with PID {proc.pid}")

if __name__ == "__main__":
    main()
