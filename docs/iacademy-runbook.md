# IAcademy Social — runbook F0/F1

Fecha: 2026-10-22. Distribución local en `iacademy-social`, rama `iacademy/f0-f1`, upstream `7bf959b30cc7f345f84d2be59e68a0a05c327e4f`. Decisión: ADR-IAC-SOCIAL-001, conservado en el worktree de documentación de `iacademy-soporte`.

**Estado: piloto local operativo; no conectado a Meta; G0 comercial y G1 pendientes.** No es un despliegue productivo ni un canal de atención activo. No hay cambios en soporte, web, precios, DNS o cuentas sociales. Sin commit, push ni fork remoto.

## 1. Arranque aislado comprobado

Desde la raíz de `iacademy-social`, con Docker Desktop activo:

```bash
docker compose --env-file /dev/null -f docker-compose.yml -f deploy/iacademy/compose.yaml config --quiet
docker compose --env-file /dev/null -f docker-compose.yml -f deploy/iacademy/compose.yaml up -d --build
curl --fail http://127.0.0.1:18730/healthz
```

- Proyecto `iacademy-social-f0`; imagen `iacademy-social:7bf959b-f0`.
- Único puerto publicado: **127.0.0.1:18730**. PostgreSQL no publica puerto. Worker y web comparten medios.
- Los dos `-f` son obligatorios: excluyen `docker-compose.override.yml`, sus montajes y watchers de desarrollo.
- `--env-file /dev/null` excluye interpolación desde `.env`; el overlay elimina `env_file` de los servicios. No se introdujeron credenciales Meta.
- Settings de desarrollo y claves inseguras de desarrollo que ya incorpora upstream: **solo datos sintéticos, sin túnel, sin acceso público**. No reutilizar esta configuración ni estos valores en producción.
- El overlay usa `!reset` y `!override`, comprobados con Compose 5.1.1; no es YAML genérico para PyYAML.
- Alta de prueba: `pilot-f0@example.invalid`. Contraseña aleatoria de la sesión, no versionada ni registrada. Para otra sesión, crear otro usuario sintético desde la interfaz; no enviar contraseñas por chat.

Para detener sin borrar los datos:

```bash
docker compose --env-file /dev/null -f docker-compose.yml -f deploy/iacademy/compose.yaml stop app worker postgres
```

No ejecutar `down -v` para operar el piloto: borraría su BD y medios.

## 2. Smoke funcional observado

1. Alta desde el navegador → organización y workspace creados; workspace renombrado `IAcademy F0 sintético`.
2. Contacto `lead-f0@example.invalid`, sin persona real.
3. Creación de flujo en UI; grafo determinista guardado mediante el servicio `save_draft`; publicación mediante **Set live** en el editor React construido en Docker.
4. Flujo `IAcademy F0 — worker sin envíos`: una acción `add_tag(f0-worker-complete)`. No contiene envío, petición externa ni IA. Sin trigger automático.
5. Encolado `start_flow` por `apps.queueing.registry.schedule`, clave `iacademy-f0-worker-smoke`. El proceso **worker ya arrancado** reclamó la fila: `done`, un intento; ejecución `completed`; etiqueta visible en contacto/bandeja. Reencolar la misma clave devolvió la misma fila; una sola ejecución.
6. Bandeja abierta con conversación sintética sobre canal `F0 sintético SIN Meta`, explícitamente **disabled**, sin credenciales ni dirección de destinatario. Nota interna añadida desde UI y persistida; pausa de automatización visible. Cero filas salientes externas. **No es una prueba de DM real.**
7. `/healthz`: HTTP 200, `status=ok`, `database=ok`.

La pausa upstream es temporal; no sustituye el ownership persistente de F2. No conectar IA al envío existente antes de implementar ese gate.

## 3. Backup y restauración ensayados

Artefactos sintéticos locales, ignorados por Git, permisos 0600, directorio 0700:

- `.local/f0-backup/database.dump`: 321.832 bytes, formato custom de PostgreSQL.
- `.local/f0-backup/media.tar.gz`: 214 bytes.
- Medio: `iacademy-f0/evidence.txt`, SHA-256 `70e0afea9b5dc1b458b7d00374b1a6e49a51661d35d84f249847131c9d87c335`.

Procedimiento ejecutado: parar web/worker, `pg_dump -U postgres -Fc --no-owner brightbean_chat` desde el contenedor PostgreSQL y `tar -C /app/media -czf - .` desde un contenedor app de un solo uso; conservar las salidas binarias y reanudar web/worker en `finally`. No se volcó ninguna BD productiva.

Restauración comprobada en una BD **nueva**, `iacademy_restore`, del PostgreSQL desechable `iacademy-social-f0-tests-pg`, no sobre la BD del piloto:

```bash
docker exec iacademy-social-f0-tests-pg createdb -U postgres iacademy_restore
docker exec -i iacademy-social-f0-tests-pg pg_restore -U postgres --exit-on-error --no-owner -d iacademy_restore < .local/f0-backup/database.dump
```

El primer comando solo es válido si esa BD no existe; no borrarla ni sobrescribirla para repetir la prueba. Elegir otra BD vacía. El contenedor de pruebas usó PostgreSQL 16, publicado solo en `127.0.0.1:18731`, y se conectó a la red aislada del piloto para validar la copia con Django.

Medios extraídos en volumen independiente `iacademy-social-f0-restore-media`; aplicación de comprobación en `127.0.0.1:18732`, con BD y volumen restaurados. Se verificaron:

- Credenciales del usuario original con una sesión de navegador limpia: login correcto.
- Flujo conservado como **Live**, contacto, etiqueta, ejecución completada y nota interna.
- Ninguna fila saliente externa; SHA-256 del medio restaurado idéntico.
- Piloto original reanudado y `/healthz` correcto.

Al extraer como usuario no root en tmpfs, crear primero un subdirectorio propio; extraer sobre la raíz de un tmpfs ajeno falla al aplicar metadatos del directorio. No resolverlo dando privilegios al servicio permanente.

La restauración sintética **no acredita** backup productivo cifrado, custodia de claves ni RPO/RTO. Las claves de cifrado futuras deben custodiarse aparte de la BD; no incluirlas en estos artefactos.

Tras verificar la copia, se retiraron el contenedor app de restauración, el PostgreSQL de pruebas y el volumen restaurado creados en esta sesión. Los puertos 18731/18732 ya no quedan activos. Se conservan el piloto en 18730, los backups y la captura local `.local/f0-backup/restored-flow.png`.

## 4. Inventario Hetzner en solo lectura

| Evidencia | Observado |
|---|---|
| `saas-01` | Caddy 2.11.3 existente en 80/443; PostgreSQL 16; servicios de IAcademy y soporte ya en ejecución |
| Capacidad puntual `saas-01` | 7,6 GiB RAM total, 3,4 GiB disponible; sin swap; 34 GiB disco libre. No equivale a presupuesto de capacidad bajo carga |
| Modelo en `saas-01` | Ollama interno `http://ollama:11434`, HTTP 200 desde `soporte-api`; `qwen2.5:1.5b` y `qwen2.5:3b` |
| vLLM/modelo previsto | No acreditado en ese servidor. No se ha inferido calidad, latencia ni capacidad para F3 |
| `trigr-01` | Proxy Caddy existente en 80/443 y múltiples aplicaciones; no se ha instalado nada |

El modelo de soporte existente no se ha cambiado. Para la futura instalación remota, reutilizar `docker-compose.prod.yml` + `deploy/docker-compose.external-tls.yml` y el proxy existente; no arrancar un segundo Caddy que dispute 80/443. Confirmar hostname, secretos seguros, red de proxy, copias cifradas y capacidad **antes** de desplegar. El compose local de esta entrega no satisface ese gate.

## 5. Oferta: fail closed

Ver [revisión comercial](iacademy-offer-review.md) y [manifiesto público](../deploy/iacademy/public-knowledge.json).

El manifiesto no incluye importes, checkouts, condiciones de compra ni condiciones de ofertas privadas. `automated_replies_enabled=false`, `prices_enabled=false`, `commercial_terms_enabled=false`. No hay consumidor IA conectado: estos campos son un artefacto de revisión, **no** una salvaguarda ejecutable del BrightBean upstream.

G0 comercial pendiente de resolver contradicciones del generador del sitio, Price Book, web y KB, verificar importes/vigencia de los checkouts y aprobar una única versión. No corregir Stripe ni publicar ofertas por inferencia. No usar la revisión interna como fuente recuperable para el bot.

## 6. Preparación Meta — acta F0/F1 y actualización 2026-10-23

Referencia fijada: [Instagram](channels/instagram.md), [Messenger](channels/messenger.md).

Documentación histórica, **no panel verificado hoy**: app `IAcademy Ops`, id público `956080144220791`; Instagram `@iacad.emy`. Acredita configuración de publicación previa, no permisos de mensajería. No acredita página Facebook ni su titularidad. La conexión al navegador autenticado falló al arrancar el broker del relay; no se ha usado una sesión autenticada alternativa ni cambiado la configuración global de omp.

**Actualización 2026-10-23:** se restableció el acceso autenticado y se inspeccionaron Meta y LIOS en lectura. Messenger sigue apuntando a `https://ventas.iacedemy.com/webhooks/meta`, con LIOS habilitado. Instagram aún sin callback/redirect acreditados; app sin publicar/revisión no enviada y URLs legales todavía apuntando a Facebook. El párrafo anterior conserva la incidencia histórica de F0, no el estado del acceso actual. Detalle y corte controlado en el ADR/plan de transición de `iacademy-soporte`, rama `docs/brightbean-social-20261022`. No se modificó producción.

No existen credenciales Meta configuradas en esta distribución. No se han solicitado ni pegado tokens en chat. El titular debe conceder OAuth desde la cuenta correcta cuando exista un despliegue HTTPS seguro.

| Canal | Redirect relativo al origen HTTPS que se apruebe | Webhook | Scopes solicitados por la revisión fijada |
|---|---|---|---|
| Instagram Login | `/channels/instagram/callback/` | `/webhooks/instagram/` | `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_manage_comments` |
| Facebook Login for Business | `/channels/messenger/callback/` | `/webhooks/messenger/` | `pages_messaging`, `pages_show_list`, `pages_manage_metadata`, `pages_read_engagement`, `pages_manage_engagement` |

No registrar localhost ni inventar un hostname productivo. Resolver primero origen HTTPS y certificado. `APP_URL` determina los callbacks; Meta exige coincidencia exacta. No habilitar un túnel sobre este servidor DEBUG.

Configuración necesaria en secretos de contenedor: nombres `PLATFORM_INSTAGRAM_CLIENT_ID`, `PLATFORM_INSTAGRAM_CLIENT_SECRET`, `PLATFORM_INSTAGRAM_VERIFY_TOKEN` y sus equivalentes `PLATFORM_MESSENGER_*`. Para Instagram, usar el ID/secret de la **app Instagram**, no intercambiarlos con los de Facebook. Los verify tokens son de despliegue, no de workspace. No se han creado estos secretos reales.

Campos webhook: Instagram `messages`, `messaging_postbacks`, `comments`, `mentions`, `message_deletions`; Messenger `messages`, `messaging_postbacks`, `messaging_referrals`, `message_deliveries`, `message_reads`, `feed`.

### Seguridad y privacidad comprobadas / pendientes

- HTTP real local, ambos canales sin configurar: GET de verificación → **404**; POST con firma inválida → **403**. Ninguna conexión se activa con esos eventos.
- Suite upstream ejecutada: firmas válidas/inválidas, OAuth, comentarios, deduplicación, bajas, ventanas, refresco/reconexión y borrado con proveedores simulados. **No demuestra entrega de Meta, permisos concedidos ni recepción en un teléfono.**
- URLs públicas accesibles: https://iacedemy.com/legal/privacy y https://iacedemy.com/legal/data-deletion. La segunda es de **instrucciones de supresión**, no un callback programático. Su existencia no demuestra que estén registradas en la app ni aprobadas por Meta.
- No se localizó un callback Meta `signed_request` en las rutas/configuración de canales de upstream. No confundir `message_deletions` con una solicitud de supresión completa de datos de usuario.
- La privacidad pública describe Meta para medición de campañas, pero no explica este nuevo tratamiento de conversaciones con IA, su retención y derivación. Revisión y publicación legal pendientes antes de clientes reales. Ningún documento legal se ha modificado.
- El dato histórico `instagram_business_content_publish` corresponde a **publicación**, no acredita ni sustituye `manage_messages`/`manage_comments`. No se exige publicar contenido desde BrightBean para responder DMs.
- Registrar modo dev/live, rol de tester, scopes realmente concedidos, titularidad de página/cuenta, Business Verification y App Review. La inspección del 2026-10-23 no acredita permisos públicos ni entrega de mensajes. No inferir necesidad o concesión de acceso público a partir de una app propia: comprobar la combinación concreta en Meta.

### Pruebas reales que faltan para G1

Con HTTPS y permisos autorizados, todavía sin IA:

1. DM de cuenta de prueba → hilo → respuesta humana → recepción en el remitente, en Instagram y Messenger.
2. Reel controlado: keyword, comentario repetido, no seguidor, una sola respuesta privada y continuación solo tras respuesta válida. No activar secuencias sobre un comentario sin más.
3. Comentario Facebook: respuesta pública aprobada y derivación privada; nunca datos de cuenta/pago en público.
4. Baja, ventana cerrada y reconexión con el proveedor real, sin alterar timestamps ni credenciales productivas para fabricar evidencia.
5. Conservar IDs de eventos y capturas sin PII de terceros, scopes y modo de app. No declarar G1 superado solo porque la suite local pase.

## 7. Validación ejecutada

- `make lint`: Ruff y formato correctos, 822 archivos.
- `make typecheck`: mypy sin errores, 851 archivos; notas informativas sobre cuerpos sin anotaciones.
- `npm run typecheck:js`, `npm run build`: correctos.
- `npm run test:js`: **434 pruebas**, 32 archivos, aprobadas.
- `pytest -n 4` con PostgreSQL de pruebas independiente: **8.791 aprobadas, 12 omitidas**, 154,14 s. Es la suite completa, no un subconjunto Meta.
- Smoke de navegador, worker, HTTP y restauración descritos arriba. No se ha certificado accesibilidad completa ni QA móvil del producto upstream.

Se añadió `.local/` a `.gitignore` y `.dockerignore`. Tras crear los backups se reconstruyó la imagen y se comprobó ejecutándola que no contiene `/app/.local`, `/app/.env` ni `/app/.venv`; después se recreó el piloto sin borrar volúmenes. La build conserva avisos upstream de Vite/React Flow sobre opciones de bundling, sin error de compilación.

No se ha implementado F2/F3 ni conectado un LLM. No instalar Chatwoot/HushReply en paralelo ni conectar más de un emisor a las mismas conversaciones.

## 8. Centralización comercial con LIOS — 2026-10-23

Se añadió `GET /api/v1/conversations/{conversation_id}/context?message_id={message_id}`, autenticado y limitado al workspace/permiso de bandeja. Contrato en [API v1](api/v1.md): metadatos de entrada Instagram/Messenger y path del hilo, sin texto, historial ni identidad de canal. Cero o varias identidades no obligan a adivinar un remitente. **No** es el contexto futuro de IA con `owner`/`generation`, ni implementa decisiones/envío.

LIOS conserva persona, etapa, responsable, tareas y pagos. Su rama `feat/brightbean-centralizacion` implementa:

- `POST /webhooks/brightbean`: HMAC, recibo+job durables, dedupe workspace/delivery y workspace/mensaje; worker comercial `default`.
- `GET /api/integrations/brightbean/contacts/{contact_id}/context`: bearer independiente, sin nombres/contacto/pagos; etapa/tarea solo tras vínculo de identidad verificado.
- Ficha comercial con referencia al hilo y vinculación humana explícita, sin fusión por apodo/email ni cambio de una venta existente.

Suscribir únicamente `contact.created`, `message.received`, `contact.tag_added`, `execution.completed` del workspace aprobado a la URL HTTPS autorizada de LIOS. Mantener la entrega deshabilitada hasta pre-vincular los contactos conocidos verificados; habilitar y probar después. El `id` del envelope es el delivery ID: no añadir un event_id ficticio. Configuración, migración y operación en `LIOS/docs/brightbean.md`; no compartir acceso de escritura a las bases ni copiar secretos a estos documentos.

Validación final: Ruff/formato correctos (825 archivos), mypy sin errores (853 archivos) y suite completa **8.812 aprobadas, 12 omitidas upstream**. LIOS: suite final **555 aprobadas**, incluidas las 49 pruebas específicas; la cascada CSS se verificó en navegador. El smoke real incluyó alta, vínculo a venta existente, duplicados, apertura autenticada del hilo y recuperación automática tras caída, con datos sintéticos. La revisión final corrigió y comprobó la cronología de redeliveries y la liberación de peticiones tras rechazos 404; evidencia detallada en el runbook de LIOS.

El transporte local fue un harness de loopback: **no prueba** la entrega HTTPS saliente del emisor ni Meta. Se mantuvieron las defensas SSRF, las conexiones sintéticas sin credenciales y el webhook de prueba deshabilitado para no entregar fuera del entorno. **G-CENTRALIZACION productivo es obligatorio antes de cambiar el receptor Meta** y sigue pendiente de HTTPS/secretos/despliegue autorizados y prueba controlada. Ninguna IA, callback real, publicación o envío a clientes activado.

## 9. Despliegue Swarm aislado — 2026-10-23

**Alcance aprobado:** BrightBean aislado; LIOS productivo se conserva. El usuario autorizó Swarm y publicación de versiones, pero aplazó sustituir LIOS al comprobar que su PostgreSQL compartido tiene TLS desactivado. No se conectan Meta, IA, campañas ni el webhook comercial. G-CENTRALIZACION y G-CORTE siguen pendientes.

### Preparación acreditada

- Swarm inicializado en `saas-01`, control y datos por Tailscale; listener de gestión `100.109.129.32:2377`. Los 28 contenedores presentes conservaron ID, fecha de arranque y estado durante la inicialización.
- Registro A DNS-only `social.iacedemy.com → 167.233.58.69`, TTL 300. Se reutiliza `saas-caddy`, propietario de 80/443; Caddyfile real `/opt/saas/caddy/Caddyfile`.
- Redes externas overlay cifradas y attachable: `iacademy_social_front` (`10.99.0.0/24`) y `iacademy_brightbean_backend` (`10.99.3.0/24`). Solo Caddy y app en la frontal; solo app/worker/PostgreSQL en la backend. Ningún puerto de app/BD publicado.
- También se prepararon las redes LIOS `10.99.1.0/24` y `10.99.2.0/24`, **sin conectar sus servicios**. No autorizan migrar la BD compartida.
- Backup previo GPG en `/opt/saas/backups/iacademy-social/predeploy-20261023T125801Z`: dump LIOS, configuración/medios y metadatos runtime cifrados. Dump restaurado sin errores en PostgreSQL independiente, sin red y sobre tmpfs: 40 tablas y 49 FK. La instancia de restauración propia quedó detenida; no se restauró producción.
- Custodia privada exclusivamente en `~/.config/iacademy-social/` del Mac, directorios 700 y ficheros sensibles 600. Clave privada GPG y CA privada **no subidas al servidor**. No mostrar esos ficheros ni copiarlos a git.

### Manifiesto y secretos

`deploy/iacademy/swarm/brightbean-stack.yml` contiene app Gunicorn, worker `process_tasks` y PostgreSQL. Imagen app inmutable `BB_IMAGE`; fijar también `PG_IMAGE` al digest inspeccionado. Configuración secreta de Django en `/run/secrets/brightbean_runtime.env`, leída mediante `DJANGO_ENV_FILE`; contraseña PostgreSQL mediante `POSTGRES_PASSWORD_FILE`. No usar `.env` en el servidor ni credenciales en el entorno del servicio.

Variables públicas de despliegue:

- `BB_IMAGE`, `PG_IMAGE`, `BB_TRUSTED_PROXIES=10.99.0.0/24`.
- `BB_RUNTIME_SECRET`, `BB_POSTGRES_SECRET`.
- `BB_TLS_CA_SECRET`, `BB_WEB_CERT_SECRET`, `BB_WEB_KEY_SECRET`, `BB_PG_CERT_SECRET`, `BB_PG_KEY_SECRET`: nombres de secrets nativos, no valores.
- `BB_GUNICORN_CONFIG`, `BB_PG_HBA_CONFIG`: configs Swarm creadas desde `gunicorn.py` y `pg_hba.conf` de la misma versión publicada.
- `BB_APP_REPLICAS`, `BB_WORKER_REPLICAS`: ambos **0 por defecto** para arrancar únicamente PostgreSQL antes de migrar; establecer ambos a 1 tras la migración.

API y worker leen la misma configuración. No configurar claves Meta, SMTP externo, IA ni suscripciones comerciales en esta fase. Registro público y recuperación por email se cierran en el proxy mientras no haya correo operativo; el acceso inicial se provisiona administrativamente, con credenciales en custodia local y cambio de contraseña autenticado.

### TLS interno y rotación

Gunicorn exige TLS 1.3 mediante `gunicorn.py`; Caddy valida su certificado y hostname `brightbean-web` con la CA pública persistida en `/opt/saas/caddy/config/iacademy-social-ca.pem` (dentro de Caddy: `/config/iacademy-social-ca.pem`). **Nunca** `tls_insecure_skip_verify`.
El proxy preserva explícitamente `Host` público con `header_up Host {http.request.host}`: Caddy 2.11 usa por defecto el host del upstream HTTPS, que Django rechaza. La red adicional se conserva para recreaciones mediante `compose.proxy-network.yml`, combinado con `/opt/saas/docker-compose.yml`; la conexión inicial no recrea Caddy. No ejecutar una recreación de ese proxy compartido fuera de una ventana aprobada.


PostgreSQL exige TLS 1.3; `pg_hba.conf` permite socket local y únicamente `hostssl` por TCP. Django/migrador usan `sslmode=verify-full`, `sslrootcert=/run/secrets/brightbean_ca.crt` y `ssl_min_protocol_version=TLSv1.3`; hostname `brightbean-postgres`. Los certificados/keys web y PostgreSQL son distintos. Key PostgreSQL montada 400 para uid/gid 70; runtime/key web 400 para uid 1001.

Certificados internos emitidos el 23-10-2026, caducan el **23-10-2027 13:53:25 UTC**. Rotarlos antes de esa fecha: firmar nuevos leaf con la CA custodiada, crear **nuevos nombres** de secrets, actualizar el manifiesto público y verificar cadena/hostname/TLS antes de retirar los anteriores. No sustituir secretos inmutables en silencio. El certificado público usa la renovación ACME de Caddy. La CA privada no debe copiarse al host para automatizar esa rotación.

### Orden de despliegue

1. Publicar fuente modificada y fijar commit, hash del archivo, imagen e ID/digest. Construir desde el archivo Git de ese commit, no desde una carpeta local con cambios.
2. Crear secrets nativos desde stdin; configs desde los ficheros publicados. Guardar solo nombres/IDs públicos en el acta.
3. Exportar las variables públicas anteriores; `docker stack config -c deploy/iacademy/swarm/brightbean-stack.yml` debe resolver exactamente las imágenes aprobadas.
4. Desplegar con `BB_APP_REPLICAS=0 BB_WORKER_REPLICAS=0`; esperar PostgreSQL saludable.
5. `sh deploy/iacademy/swarm/migrate.sh "$BB_IMAGE" "$BB_TRUSTED_PROXIES"`: usa la misma imagen, runtime, CA y backend; espera hasta 600 s y exige estado `complete` con `ContainerStatus.ExitCode=0`. Un fallo aborta la activación. Servicio terminado retenido como evidencia; no existe `service create --rm` ni se confía en el exit del comando de creación.
6. Desplegar con ambas réplicas a 1. Esperar salud HTTPS interna, migraciones aplicadas y worker operativo.
7. Conectar Caddy **solo** a la frontal. Validar el snippet `Caddyfile.social.snippet` con la CA persistida antes de recargar. Preservar el resto del Caddyfile. Su bind es de un fichero: actualizar conservando inode, no mediante rename que deje al contenedor leyendo el antiguo.
8. Verificar HTTPS público, acceso real, registro cerrado, enlace visible al código fuente, colas y aislamiento. Repetir backup GPG y restauración independiente de la nueva BD y medios antes de declarar G-INFRA.

### Retorno y límites

- App/worker: actualizar imagen aprobada con stop-first y rollback automático ante fallo; PostgreSQL singleton con pausa, no rollback automático del estado.
- Si falla esta primera instalación, no publicar/conectar canales. Retirar su ruta del proxy únicamente mediante cambio validado y detener solo servicios nuevos aprobados. No usar `stack rm`, borrar volúmenes ni restaurar una BD antigua sobre datos posteriores.
- LIOS conserva imagen `lios:202610101928-6d74cfa2a3`, API, worker comercial, conversación, scheduler, DSN y callback. No ejecutar su `scripts/deploy.sh`, que recrearía los cuatro servicios.
- Oferta AGPL visible en acceso y aplicación, enlazada a [la fuente modificada](https://github.com/pedri77/iacademy-social/tree/iacademy/f0-f1). Registrar el commit exacto de cada imagen.

### Acta de ejecución y acceso

- Fuente de imagen: [`db0b7cb1f88467264a9cf2223c284b13242f22b5`](https://github.com/pedri77/iacademy-social/tree/db0b7cb1f88467264a9cf2223c284b13242f22b5); imagen `iacademy-social:20261023-db0b7cb1f8`, ID y RepoDigest `sha256:f32498fd01261a93578f09c2cf4e5b34d3e9dab5be1302408cff59e4bb76eab9`. Archivo Git de construcción SHA-256 `eba18b6fb00e4581c73a7c7ed20e696a3b6a5a6574143dadaddc11abaa06c78d`.
- Configuración de proxy: commit `64d905b05f753b28ca77701624e5a3430461d18e`, conservado en `/opt/iacademy-social/config-releases/64d905b05f753b28ca77701624e5a3430461d18e/`. La imagen no se reconstruyó por el cambio exclusivo de Caddy. Caddyfile activo SHA-256 `80ff3ce2aace21d382992ef782d8d36037cfdd5bcb64c561d0f4a9616037fe81`.
- PostgreSQL fijado a `postgres@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685`. Migrador inicial terminó `complete`/exit 0; `manage.py migrate --check` devolvió 0. App saludable y worker real ejecutándose, una réplica cada uno.
- `/healthz` público y login real correctos. Registro y recuperación por correo devuelven 403 deliberadamente; no hay SMTP externo. Operador provisionado con la identidad administrativa existente y propiedad de organización/workspace IAcademy, **sin superusuario global**. Acceso en `~/.config/iacademy-social/operator-access.json`, modo 600, solo en custodia local; cambiar la contraseña desde sesión autenticada. No publicar el fichero ni sus valores.
- Navegador real: login y aplicación a 1440 px y 390 px, sin desbordes horizontales; oferta AGPL visible, sin errores de navegador; logout realizado y pestaña cerrada.
- App→PostgreSQL negoció TLSv1.3; conexión TCP sin cifrar y certificado con hostname erróneo rechazados. Gunicorn rechazó TLS 1.2. No se relajaron CA, hostname ni permisos de secretos.
- Worker `process_tasks`: flujo real de espera→etiqueta completado; `start_flow` y `resume_execution` terminaron `done`, un intento cada uno, sin invocar handlers inline. Cero canales y mensajes; los registros sintéticos propios se retiraron tras comprobarlo.
- Los cuatro contenedores LIOS conservaron sus IDs y fechas de arranque; su login siguió en HTTP 200. Integración preparada y publicada en `pedri77/lead-intelligence-os`, rama `feat/brightbean-centralizacion`, commit `c59e7b3ba0ae53abd70ae94243cb40ba0a6932af`, **no desplegada**. Ruff y smoke de configuración correctos; suite repetida en PostgreSQL exclusivo: 555 aprobadas, un aviso upstream, 1156,95 s. No se repitió en esta fase la suite BrightBean de §8; sí Ruff/formato (826 archivos), build amd64 y los smokes runtime descritos.

### Backup y restauración del despliegue aislado

Conjunto completo verificado: `/opt/saas/backups/iacademy-social/brightbean-20261023T161821Z/`, con copia **cifrada** en `~/.config/iacademy-social/brightbean-20261023T161821Z/`. `manifest.json` SHA-256 `6bc68e143f4a97abaa7dac6dcd140cafe1867624f49c7dce18c97fbd3f38a269`; sus cuatro checksums coinciden con la copia local. `restore-proof.json` registra el resultado, sin filas de clientes ni secretos.

1. PostgreSQL: transacción `REPEATABLE READ READ ONLY`, `pg_export_snapshot()` y `pg_dump -Fc --snapshot=…` del mismo snapshot. El dump pasa directamente a GPG; no se escribe un dump claro. También se cifran medios y dos archivos de secretos nativos (web y PostgreSQL). El servidor solo tiene la clave pública GPG.
2. Web: archivar `/run/secrets` como el usuario normal **UID 1001**, no mediante `docker exec -u 0`: `cap_drop=ALL` hace que root no pueda leer los secretos 400 de otro UID. No cambiar permisos para hacer el backup. PostgreSQL conserva las capacidades necesarias de su entrypoint y su archivo se obtuvo como root. Un intento incompleto anterior está marcado `INCOMPLETE.txt`; no pertenece al conjunto verificado.
3. Recuperación: descifrar localmente con la clave privada custodiada y transmitir el stdout directamente por SSH a `docker exec -i … pg_restore --exit-on-error --single-transaction --no-owner --no-privileges -U brightbean -d brightbean`. GPG y restore devolvieron 0. La clave privada nunca se subió al servidor.
4. Destino independiente, `--network none`, sin puertos, PostgreSQL y medios sobre tmpfs. Coincidieron **79 tablas, 461 filas, 150 FK y las huellas agregadas de todas las tablas** con el snapshot original. Medios vacíos: restaurados 0 archivos; no acredita todavía una recuperación de adjuntos reales. Los dos archivos de secretos se descifraron y su estructura tar se comprobó sin imprimir valores.
5. Instancia de restauración propia detenida al terminar; no se restauró ni sustituyó la BD productiva. El PostgreSQL local exclusivo de la suite LIOS también se detuvo, sin intervenir bases de otras sesiones.

Es un snapshot puntual comprobado, **no** una programación automática de backups/rotación ni una alarma de caducidad de certificados. Esos controles operativos siguen pendientes antes de clientes reales, junto con G-LEGAL, permisos/prueba de Meta y G-CENTRALIZACION. G0 comercial permanece abierto por reconciliación de oferta; este despliegue no aprueba G-CORTE ni activa respuestas.

## 10. Backup automático y checks operativos — scripts entregados 2026-10-24

Software público en [`deploy/iacademy/ops/`](../deploy/iacademy/ops/): **listo para instalación, aún no instalado ni programado** (sin cron/timer activo, sin dry-run ni smoke ejecutados; el integrador lo opera). Sin credenciales en config, argv ni logs; los secretos solo se leen dentro de los contenedores.

### Componentes

- `backup.sh` — subcomandos `backup`, `check`, `retention`. Los targets se declaran como **servicios Swarm** (`*_SERVICE`); el script resuelve la réplica Running **única** por label `com.docker.swarm.service.name` y falla con 0 o >1 réplicas (nunca IDs volátiles). Dump PostgreSQL custom (`pg_dump -Fc`) por **pipe directo a GPG** (sin plaintext persistente); medios y **todos los secretos nativos montados** (`/run/secrets` completo de cada contenedor: web runtime/CA/crt+key, PG cert+key+password, LIOS runtime/API crt+key/CA y PG cert+key/password) cifrados igual, sin nombres hardcodeados. Secretos web como **UID de la app** (`docker exec -u`, nunca `-u 0`: `cap_drop=ALL`); PG con exec normal. GPG valida al inicio que el recipient esté en el homedir público del contrato. Fail-closed: servicio/replique, artefacto ausente/vacío, hash discordante, manifiesto con recuento erróneo o pipeline roto ⇒ conjunto queda `INCOMPLETE.txt` y salida ≠ 0; `mkdir` exclusivo sin reutilizar/reescribir conjuntos. `COMPLETE` (con SHA-256 del manifiesto) se escribe **solo** tras verificar todos los pipelines y hashes; nunca con 0 artefactos. Bloqueo single-flight con `flock`.
- `retention.py` — retención **solo** sobre conjuntos completos de `/opt/saas/backups/iacademy-social/ops/`: diarios 30 días + primer completo de cada mes 12 meses; nunca borra el más reciente, ni conjuntos `INCOMPLETE`, ni manuales/pre-deploy/ajenos del directorio padre, ni sigue symlinks.
- `alert-command.sh` — hook público de notificación: mensajes fijos sin PII por stdin o nombre de unidad. `/etc/iacademy-social/alert.conf` selecciona `notify-telegram.py`; este crea una tarea Swarm efímera que recibe las credenciales exclusivamente como secret nativo, comprueba la aceptación de Telegram y conserva el servicio si falla. `notify-refs.json` solo contiene imagen, red y nombre del secret. Sin notificador válido, el hook sale ≠ 0; no hay acuse falso.
- `ops.conf` — config pública de targets, rutas, UIDs, recipient GPG y umbrales. LIOS está habilitado después de su migración a BD exclusiva; API y exec de PG como UID 0, web BB como UID 1001. Si falta algún servicio, falla el conjunto completo, sin fallback.
- `systemd/` — `iacademy-social-backup.{service,timer}` (diario 02:30 UTC, `Persistent=true`) y `iacademy-social-check.{service,timer}` (diario 07:30): check de frescura de backup (`BACKUP_MAX_AGE_HOURS`, defecto 26) y caducidad TLS del endpoint público web, certs internos web BB (en `/run/secrets` de la app) y certs de PG BB/LIOS. Umbrales warn 30 d / error 7 d con salidas 2/1: **ambas ≠ 0 disparan `OnFailure` y el hook**. Ambas unidades con `OnFailure=iacademy-social-ops-alert@%n.service`.

### Instalación (servidor, por el integrador)

```bash
install -d -m 0755 /opt/saas/ops/iacademy-social /etc/iacademy-social
install -m 0755 deploy/iacademy/ops/backup.sh deploy/iacademy/ops/retention.py deploy/iacademy/ops/alert-command.sh deploy/iacademy/ops/notify-telegram.py /opt/saas/ops/iacademy-social/
install -m 0644 deploy/iacademy/ops/ops.conf deploy/iacademy/ops/alert.conf deploy/iacademy/ops/notify-refs.json /etc/iacademy-social/
install -m 0644 deploy/iacademy/ops/systemd/*.{service,timer} /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now iacademy-social-backup.timer iacademy-social-check.timer
```

Dependencias mínimas: `bash`, `/usr/bin/docker`, `gpg`, `python3` (stdlib), `openssl`, `flock`/`systemd` (Linux). `IACADEMY_OPS_CONF` apunta por defecto a `/etc/iacademy-social/ops.conf`; `IACADEMY_ALERT_ENV`, a `/etc/iacademy-social/alert.conf`. Son referencias públicas, no credenciales. Aprovisionar primero el secret nativo de notificación referido en `notify-refs.json`; nunca poner el token en esos archivos.

### Restauración (GPG privada local, no en el servidor ni keyserver)

Procedimiento ya acreditado en §9, reutilizable con los artefactos de `ops/`: descifrar en la Mac custodio (`gpg -d brightbean-db.dump.gpg`) y transmitir el stdout por SSH a `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges` de una BD **nueva** en destino aislado (`--network none`, tmpfs), verificando tablas/FK/huellas y medios; después los secretos descifrados solo estructura tar. No existe un `restore --clean` ni se restaurará sobre producción.

Pruebas permanentes: `tests/test_ops_retention.py` cubre solo los invariantes de retención (lógica pura, sin producción).
