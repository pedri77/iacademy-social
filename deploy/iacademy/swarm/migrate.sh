#!/bin/sh
# Migración one-shot tras arrancar PostgreSQL con app/worker a cero.
# Se conserva el servicio terminado como evidencia; nunca elimina datos.
set -eu
BB_IMAGE="${1:?uso: migrate.sh <BB_IMAGE> <BB_TRUSTED_PROXIES>}"
BB_TRUSTED_PROXIES="${2:?indica la subred de iacademy_social_front}"
BB_RUNTIME_SECRET="${BB_RUNTIME_SECRET:-brightbean_runtime}"
: "${BB_TLS_CA_SECRET:?indica el secreto de la CA interna}"
NAME="brightbean-migrate-$(date +%Y%m%d%H%M%S)"
job=$(docker service create --detach --quiet --name "$NAME" \
  --restart-condition none --limit-memory 512m --limit-cpu 0.75 \
  --network iacademy_brightbean_backend \
  --secret "source=$BB_RUNTIME_SECRET,target=brightbean_runtime.env,uid=1001,gid=0,mode=0400" \
  --secret "source=$BB_TLS_CA_SECRET,target=brightbean_ca.crt,uid=1001,gid=0,mode=0444" \
  --mount type=volume,source=brightbean_bb_media_data,target=/app/media \
  --env DJANGO_SETTINGS_MODULE=config.settings.production \
  --env DJANGO_ENV_FILE=/run/secrets/brightbean_runtime.env \
  --env APP_URL=https://social.iacedemy.com \
  --env ALLOWED_HOSTS=social.iacedemy.com \
  --env "TRUSTED_PROXIES=$BB_TRUSTED_PROXIES" \
  --constraint 'node.role == manager' \
  "$BB_IMAGE" python manage.py migrate --noinput)
python3 - "$job" <<'PY'
import json
import subprocess
import sys
import time

job = sys.argv[1]
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    ids = subprocess.check_output(["docker", "service", "ps", "--no-trunc", "--quiet", job], text=True).split()
    if ids:
        tasks = json.loads(subprocess.check_output(["docker", "inspect", "--type", "task", *ids]))
        task = max(tasks, key=lambda item: item["CreatedAt"])
        status = task["Status"]
        state = status["State"]
        code = status.get("ContainerStatus", {}).get("ExitCode")
        if state == "complete" and code == 0:
            print(f"Migración completada: servicio={job} tarea={task['ID']} exit=0")
            sys.exit(0)
        if state in {"failed", "rejected", "orphaned", "shutdown"} or (state == "complete" and code != 0):
            print(f"Migración fallida: servicio={job} estado={state} exit={code}", file=sys.stderr)
            sys.exit(1)
    time.sleep(2)
print(f"Timeout de migración; conservar servicio={job} para revisión", file=sys.stderr)
sys.exit(1)
PY
