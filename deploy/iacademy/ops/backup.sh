#!/usr/bin/env bash
# iacademy-social-ops — backup automático BrightBean + LIOS exclusivo.
# Subcomandos: backup | check | retention
# Fail-closed: cualquier pipeline que falte o falle aborta el conjunto sin marcarlo completo.
# Sin credenciales en argv ni logs. Cifrado GPG con la clave pública del keyring del servidor.
set -Eeuo pipefail
umask 077

SUBCMD="${1:-}"
case "$SUBCMD" in
  backup|check|retention) ;;
  *)
    echo "uso: $0 {backup|check|retention}" >&2
    exit 64
    ;;
esac

CONF="${IACADEMY_OPS_CONF:-/etc/iacademy-social/ops.conf}"
# shellcheck source=/dev/null
[ -r "$CONF" ] || { echo "iacademy-social-ops: config no legible: $CONF" >&2; exit 78; }
. "$CONF"

LOCK_FILE="${IACADEMY_OPS_LOCK:-/run/lock/iacademy-social-backup.lock}"
LOG_PREFIX="iacademy-social-ops"
log() { printf '%s: %s\n' "$LOG_PREFIX" "$*"; }

# Resuelve la ÚNICA réplica Running de un servicio Swarm por label.
# 0 réplicas o >1 ⇒ fail-closed (exit != 0). Nunca se fija un ID de contenedor volátil.
resolve_container() { # nombre de SERVICIO swarm -> imprime id de contenedor
  local svc="$1" ids n
  ids="$(docker ps -q --filter "label=com.docker.swarm.service.name=$svc" --filter status=running)" || return 1
  n="$(wc -w <<<"$ids")"
  [ "$n" -eq 1 ] || { log "ERROR fail-closed: servicio $svc sin réplica Running única (running=$n)"; return 1; }
  printf '%s' "$ids"
}

# GPG: homedir público del contrato (con su keyring por defecto dentro) validado al inicio.
check_gpg() {
  gpg --homedir "$GPG_HOMEDIR" --list-keys "$GPG_RECIPIENT" >/dev/null 2>&1 || {
    log "ERROR fail-closed: recipient $GPG_RECIPIENT no está en el keyring $GPG_HOMEDIR"
    return 1
  }
}
gpg_encrypt_to() { # stdin -> fichero cifrado $1 (directorio recién creado, sin overwrite)
  local dest="$1"
  [ -e "$dest" ] && { log "ERROR fail-closed: artefacto ya existe: $dest"; return 1; }
  gpg --homedir "$GPG_HOMEDIR" --trust-model always --batch --yes \
      --recipient "$GPG_RECIPIENT" --encrypt --output "$dest"
}

sha256_of() { sha256sum "$1" | awk '{print $1}'; }

latest_complete_set() { # solo conjuntos propios con COMPLETE; ignora INCOMPLETE, ajenos y symlinks
  local best="" name base
  for name in "$BACKUP_ROOT"/*/; do
    name="${name%/}"
    if [ -L "$name" ]; then continue; fi
    base="${name##*/}"
    case "$base" in
      "$BACKUP_SET_PREFIX"-????????T??????Z) ;;
      *) continue ;;
    esac
    if [ -f "$name/COMPLETE" ] && [ ! -L "$name/COMPLETE" ] && [ "$base" \> "${best##*/}" ]; then
      best="$name"
    fi
  done
  if [ -n "$best" ]; then printf '%s\n' "$best"; fi
}

do_backup() {
  # Single-flight: si otro backup corre, salir sin error (el timer no debe alertar).
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "otro backup en curso (lock $LOCK_FILE); se omite esta ejecución"
    return 0
  fi

  check_gpg || return 1

  local ts out
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$BACKUP_ROOT"
  out="$BACKUP_ROOT/${BACKUP_SET_PREFIX}-${ts}"
  # mkdir exclusivo: nunca reutilizar/reescribir un conjunto del mismo segundo.
  if ! mkdir "$out"; then
    log "ERROR fail-closed: colisión de conjunto $out (ya existe); aborta sin tocarlo"
    return 1
  fi
  chmod 700 "$out"
  printf 'INCOMPLETE %s\n' "$ts" > "$out/INCOMPLETE.txt"

  local artifacts=()
  fail() {
    log "ERROR backup incompleto en $out: $* (conjunto queda marcado INCOMPLETE)"
    printf 'INCOMPLETE %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$out/INCOMPLETE.txt"
    exit 1
  }
  trap 'fail "pipeline interrumpido (exit $?)"' ERR

  add_artifact() { # nombre relativo; productor entrega bytes por stdin
    local rel="$1"; shift
    local dest="$out/$rel"
    "$@" | gpg_encrypt_to "$dest" || fail "pipeline $rel"
    [ -s "$dest" ] || fail "artefacto vacío: $rel"
    artifacts+=("$rel")
  }

  # Archiva TODOS los secretos nativos montados en el contenedor (tar de /run/secrets completo):
  # web BB runtime/CA/crt+key; PG cert+key+password; LIOS runtime/API crt+key/CA y PG cert+key+password.
  require_secrets_nonempty() { # contenedor [uid]
    local ctr="$1" uid="${2:-}"
    if [ -n "$uid" ]; then
      docker exec -u "$uid" "$ctr" sh -c 'ls -A /run/secrets 2>/dev/null | grep -q .'
    else
      docker exec "$ctr" sh -c 'ls -A /run/secrets 2>/dev/null | grep -q .'
    fi || fail "contenedor sin secretos nativos montados: $ctr"
  }

  # --- BrightBean ---
  if [ "${BB_ENABLED:-true}" = true ]; then
    local bb_pg bb_app
    bb_pg="$(resolve_container "$BB_PG_SERVICE")" || fail "servicio BrightBean PG sin réplica única"
    bb_app="$(resolve_container "$BB_APP_SERVICE")" || fail "servicio BrightBean app sin réplica única"

    # Dump custom por pipe directo a GPG; nunca se escribe plaintext.
    add_artifact brightbean-db.dump.gpg \
      docker exec "$bb_pg" pg_dump -U "$BB_PG_USER" -Fc "$BB_DB"

    add_artifact brightbean-media.tar.gz.gpg \
      docker exec "$bb_app" tar -C "$BB_MEDIA_DIR" -czf - .

    # Secretos web: SIEMPRE como UID de la app (cap_drop ALL impide root).
    require_secrets_nonempty "$bb_app" "$BB_APP_UID"
    add_artifact brightbean-web-secrets.tar.gz.gpg \
      docker exec -u "$BB_APP_UID" "$bb_app" tar -C /run/secrets -czf - .

    # Secretos PG: el entrypoint de postgres conserva capacidades; exec normal (root).
    require_secrets_nonempty "$bb_pg"
    add_artifact brightbean-pg-secrets.tar.gz.gpg \
      docker exec "$bb_pg" tar -C /run/secrets -czf - .
  fi

  # --- LIOS (BD EXCLUSIVA tras migración; fail-closed si está habilitado y falta) ---
  if [ "${LIOS_ENABLED:-true}" = true ]; then
    local lios_pg lios_api
    lios_pg="$(resolve_container "$LIOS_PG_SERVICE")" || fail "servicio LIOS PG sin réplica única"
    lios_api="$(resolve_container "$LIOS_APP_SERVICE")" || fail "servicio LIOS API sin réplica única"

    add_artifact lios-db.dump.gpg \
      docker exec "$lios_pg" pg_dump -U "$LIOS_PG_USER" -Fc "$LIOS_DB"

    add_artifact lios-data.tar.gz.gpg \
      docker exec "$lios_api" tar -C "$LIOS_DATA_DIR" -czf - .

    # Secretos LIOS: runtime/API crt+key/CA desde la API; PG cert+key/password desde su PG.
    # UID por confirmar en el manifest de despliegue LIOS; ajustar LIOS_APP_UID/LIOS_PG_UID.
    require_secrets_nonempty "$lios_api" "$LIOS_APP_UID"
    add_artifact lios-api-secrets.tar.gz.gpg \
      docker exec -u "$LIOS_APP_UID" "$lios_api" tar -C /run/secrets -czf - .
    require_secrets_nonempty "$lios_pg" "$LIOS_PG_UID"
    add_artifact lios-pg-secrets.tar.gz.gpg \
      docker exec -u "$LIOS_PG_UID" "$lios_pg" tar -C /run/secrets -czf - .
  fi

  trap - ERR

  # Sin pipelines habilitados no hay conjunto válido: fail-closed (nunca COMPLETE vacío).
  [ "${#artifacts[@]}" -gt 0 ] || fail "ningún pipeline habilitado (BB/LIOS)"

  # Manifiesto SHA256 de todos los artefactos.
  local manifest="$out/manifest.json" first=1
  printf '{\n  "set": "%s",\n  "artifacts": [\n' "${BACKUP_SET_PREFIX}-${ts}" > "$manifest"
  local rel
  for rel in "${artifacts[@]}"; do
    [ $first = 1 ] || printf ',\n' >> "$manifest"
    first=0
    printf '    {"name": "%s", "sha256": "%s", "bytes": %s}' \
      "$rel" "$(sha256_of "$out/$rel")" "$(stat -c %s "$out/$rel")" >> "$manifest"
  done
  printf '\n  ]\n}\n' >> "$manifest"

  # Verificación del manifiesto con exit capturado: cuenta y hashes de TODOS los artefactos,
  # sin bucles vacíos que puedan pasar en silencio.
  if ! python3 - "$manifest" "$out" "${#artifacts[@]}" <<'PY'
import hashlib, json, sys
manifest, out, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = json.load(open(manifest))
arts = data["artifacts"]
assert len(arts) == expected, f"manifiesto con {len(arts)} entradas, esperadas {expected}"
for a in arts:
    h = hashlib.sha256(open(f"{out}/{a['name']}", "rb").read()).hexdigest()
    assert h == a["sha256"], f"hash no coincide: {a['name']}"
print(f"OK manifiesto: {len(arts)} artefactos verificados")
PY
  then
    fail "verificación de manifiesto falló"
  fi

  # Marca de completo SOLO tras verificar todos los pipelines y hashes.
  printf 'COMPLETE %s manifest_sha256=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(sha256_of "$manifest")" > "$out/COMPLETE"
  rm -f "$out/INCOMPLETE.txt"
  log "backup completo: $out (${#artifacts[@]} artefactos)"

  do_retention
}

do_retention() {
  python3 "$OPS_HOME/retention.py" prune --root "$BACKUP_ROOT" \
    --daily-days "$RETENTION_DAILY_DAYS" --monthly-months "$RETENTION_MONTHLY_MONTHS"
}

cert_days_left() { # stdin: PEM (uno o varios certificados) -> días del que caduca antes
  python3 -c '
import datetime as dt
import re
import subprocess
import sys

data = sys.stdin.read()
blocks = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", data, re.S)
if not blocks:
    sys.exit(1)
best = None
for b in blocks:
    p = subprocess.run(
        ["openssl", "x509", "-noout", "-enddate"],
        input=b, capture_output=True, text=True,
    )
    if p.returncode != 0 or "=" not in p.stdout:
        sys.exit(1)
    val = " ".join(p.stdout.split("=", 1)[1].split())
    when = dt.datetime.strptime(val, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
    d = int((when - dt.datetime.now(dt.timezone.utc)).total_seconds() // 86400)
    best = d if best is None or d < best else best
print(best)
'
}

# Salidas del check: 0 OK; 2 WARN (TTL<=TLS_WARN_DAYS); 1 ERROR (fallo lectura o TTL<=TLS_ERROR_DAYS).
# WARN también sale != 0 para que systemd dispare OnFailure y el hook notifique (sin acuse falso).
check_cert() { # etiqueta modo argumentos...
  local label="$1" mode="$2"; shift 2
  local pem days
  case "$mode" in
    web) # endpoint público: chain real servida
      pem="$(timeout 15 openssl s_client -connect "$1" -servername "${1%%:*}" </dev/null 2>/dev/null)" \
        || { log "ERROR $label: no se pudo conectar a $1"; return 1; }
      ;;
    secrets) # certs internos montados en /run/secrets del contenedor (UID opcional)
      local ctr="$1" uid="${2:-}"
      if [ -n "$uid" ]; then
        pem="$(docker exec -u "$uid" "$ctr" sh -c 'cat /run/secrets/*.crt 2>/dev/null')"
      else
        pem="$(docker exec "$ctr" sh -c 'cat /run/secrets/*.crt 2>/dev/null')"
      fi
      [ -n "$pem" ] || { log "ERROR $label: sin certificados legibles en /run/secrets de $ctr"; return 1; }
      ;;
    *)
      log "ERROR $label: modo desconocido $mode"; return 1 ;;
  esac
  days="$(printf '%s\n' "$pem" | cert_days_left)" || { log "ERROR $label: certificado ilegible"; return 1; }
  if [ "$days" -le "$TLS_ERROR_DAYS" ]; then
    log "ERROR $label: certificado caduca en ${days}d (umbral error ${TLS_ERROR_DAYS}d)"
    return 1
  elif [ "$days" -le "$TLS_WARN_DAYS" ]; then
    log "WARN $label: certificado caduca en ${days}d (umbral warn ${TLS_WARN_DAYS}d)"
    return 2
  fi
  log "OK $label: certificado caduca en ${days}d"
  return 0
}

check_result=0 # 0 ok, 1 error, 2 warn
record() { # rc de un check_cert
  [ "$1" = 0 ] && return 0
  [ "$1" = 1 ] && check_result=1
  [ "$check_result" = 1 ] || check_result="$1"
}

do_check() {
  local latest age_hours max_age ctr
  check_result=0

  latest="$(latest_complete_set || true)"
  if [ -z "$latest" ]; then
    log "ERROR frescura: ningún conjunto completo en $BACKUP_ROOT"
    check_result=1
  else
    age_hours=$(( ( $(date +%s) - $(stat -c %Y "$latest/COMPLETE") ) / 3600 ))
    max_age="${BACKUP_MAX_AGE_HOURS:-26}"
    if [ "$age_hours" -gt "$max_age" ]; then
      log "ERROR frescura: último backup completo hace ${age_hours}h (máximo ${max_age}h): ${latest##*/}"
      check_result=1
    else
      log "OK frescura: último backup completo hace ${age_hours}h: ${latest##*/}"
    fi
  fi

  if [ "${BB_ENABLED:-true}" = true ]; then
    # Web público (chain servida) + TLS interno web (certs en /run/secrets de la app) + PG.
    check_cert brightbean-web-public web "${BB_WEB_TLS_ENDPOINT:-}" || record $?
    if ctr="$(resolve_container "$BB_APP_SERVICE")"; then
      check_cert brightbean-web-interno secrets "$ctr" "$BB_APP_UID" || record $?
    else
      log "ERROR brightbean-web-interno: servicio sin réplica única"; record 1
    fi
    if ctr="$(resolve_container "$BB_PG_SERVICE")"; then
      check_cert brightbean-pg secrets "$ctr" || record $?
    else
      log "ERROR brightbean-pg: servicio sin réplica única"; record 1
    fi
  fi
  if [ "${LIOS_ENABLED:-true}" = true ]; then
    if ctr="$(resolve_container "$LIOS_APP_SERVICE")"; then
      check_cert lios-api secrets "$ctr" "$LIOS_APP_UID" || record $?
    else
      log "ERROR lios-api: servicio sin réplica única"; record 1
    fi
    if ctr="$(resolve_container "$LIOS_PG_SERVICE")"; then
      check_cert lios-pg secrets "$ctr" "$LIOS_PG_UID" || record $?
    else
      log "ERROR lios-pg: servicio sin réplica única"; record 1
    fi
  fi

  if [ "$check_result" = 0 ]; then
    log "OK check completo"
  elif [ "$check_result" = 1 ]; then
    log "ERROR check con fallos"
  else
    log "WARN check con avisos (TLS próximo a caducar)"
  fi
  return "$check_result"
}

case "$SUBCMD" in
  backup)    do_backup ;;
  check)     do_check ;;
  retention) do_retention ;;
esac
