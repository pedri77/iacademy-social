#!/usr/bin/env python3
"""Deliver an operations alert through a one-shot task with native Swarm secrets.

The host holds public references only. The token never enters argv, environment,
service logs or an on-disk host configuration. Failed tasks remain inspectable.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

TASK_PROGRAM = """
import base64,json,sys,urllib.parse,urllib.request
try:
    config=json.loads(open('/run/secrets/notify.json').read())
    message=base64.b64decode(sys.argv[1]).decode('utf-8')
    payload=urllib.parse.urlencode({'chat_id':config['chat_id'],'text':message}).encode()
    req=urllib.request.Request('https://api.telegram.org/bot'+config['token']+'/sendMessage',data=payload,method='POST')
    with urllib.request.urlopen(req,timeout=20) as response:
        accepted=json.load(response).get('ok') is True
    if not accepted:
        raise RuntimeError('not accepted')
except Exception:
    print('Telegram operations notification failed',file=sys.stderr)
    raise SystemExit(1)
print('Telegram operations notification accepted')
"""


def main() -> int:
    refs = json.loads(Path("/etc/iacademy-social/notify-refs.json").read_text())
    message = sys.stdin.read(2001)
    if not message.strip() or len(message) > 2000:
        print("Operations alert must contain 1–2000 characters", file=sys.stderr)
        return 64
    name = "iacademy-social-alert-" + uuid.uuid4().hex[:16]
    command = [
        "/usr/bin/docker",
        "service",
        "create",
        "--detach",
        "--quiet",
        "--name",
        name,
        "--restart-condition",
        "none",
        "--limit-memory",
        "64m",
        "--limit-cpu",
        "0.25",
        "--user",
        "0",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--network",
        refs["network"],
        "--secret",
        "source=" + refs["secret"] + ",target=notify.json,mode=0400",
        refs["image"],
        "python",
        "-c",
        TASK_PROGRAM,
        base64.b64encode(message.encode()).decode(),
    ]
    # Fixed executable and argv; refs are root-managed, stdin is base64 data, never shell code.
    created = subprocess.run(command, capture_output=True, text=True)  # noqa: S603
    if created.returncode:
        print("Cannot create native operations notification task", file=sys.stderr)
        return 1
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ids = subprocess.check_output(["/usr/bin/docker", "service", "ps", "--quiet", name], text=True).split()  # noqa: S603 — generated service name, no shell
        if ids:
            tasks = json.loads(
                subprocess.check_output(["/usr/bin/docker", "inspect", "--type", "task", *ids], text=True)  # noqa: S603 — IDs returned by Docker
            )
            task = max(tasks, key=lambda row: row["CreatedAt"])
            status = task["Status"]
            if status["State"] == "complete" and status.get("ContainerStatus", {}).get("ExitCode") == 0:
                subprocess.run(["/usr/bin/docker", "service", "rm", name], check=True, stdout=subprocess.DEVNULL)  # noqa: S603 — only this function's completed service
                print("Operations notification delivered")
                return 0
            if status["State"] in {"failed", "rejected", "shutdown", "orphaned", "complete"}:
                print("Operations notification failed; evidence task: " + name, file=sys.stderr)
                return 1
        time.sleep(1)
    print("Operations notification timed out; evidence task: " + name, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
