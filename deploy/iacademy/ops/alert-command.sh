#!/usr/bin/env bash
# alert-command — hook público de notificación para iacademy-social-ops.
# Lee mensajes FIJOS sin PII por stdin (o usa el nombre de unidad de $1).
# Si existe un notificador externo configurado (IACADEMY_ALERT_COMMAND en
# /etc/iacademy-social/alert.conf), le entrega el mensaje por stdin.
# Sin notificador configurado NO hay acuse falso: registra en journald y sale != 0
# para que el fallo siga visible como error de unidad systemd.
set -euo pipefail

PREFIX="iacademy-social-ops-alert"
msg() { printf '%s %s\n' "$PREFIX" "$*"; }

ALERT_ENV="${IACADEMY_ALERT_ENV:-/etc/iacademy-social/alert.conf}"
[ -r "$ALERT_ENV" ] && . "$ALERT_ENV"

body="$(cat)"
[ -n "$body" ] || body="$PREFIX: unidad ${1:-desconocida} falló a las $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Siempre a journald (identificador fijo, auditable).
printf '%s\n' "$body" | systemd-cat -t "$PREFIX" 2>/dev/null || printf '%s\n' "$body" >&2

if [ -n "${IACADEMY_ALERT_COMMAND:-}" ] && [ -x "$IACADEMY_ALERT_COMMAND" ]; then
  printf '%s\n' "$body" | "$IACADEMY_ALERT_COMMAND"
  msg "notificación entregada vía $IACADEMY_ALERT_COMMAND"
  exit 0
fi

msg "SIN NOTIFICADOR EXTERNO configurado (IACADEMY_ALERT_COMMAND en $ALERT_ENV); solo journald. No se acusa recibo."
exit 1
