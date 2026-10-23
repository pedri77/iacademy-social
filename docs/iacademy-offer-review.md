# Reconciliación de oferta pública IAcademy — F0 (ADR-IAC-SOCIAL-001)

Fecha: 2026-10-22. Solo lectura de fuentes; no se han editado `iacedemy-web` ni `iacademy-soporte`, ni solicitado matrículas/compras.

## Fuentes consultadas

| Fuente | Ruta / URL | Estado |
|---|---|---|
| Config del sitio | `iacedemy-web/site-config.json` (updated 2026-09-20) | **Caducada**: describe fase Founding (deadline 2026-10-15, pro 99 €, itinerario 19 €, "después" pro 199 €) |
| Price Book Stripe | `iacedemy-web/scripts/stripe/price_book.json` (v1.0) | Mixto: planes de suscripción 2026-10 vigentes + entradas de evento con errores de importe |
| Web pública precios | https://iacedemy.com/pricing/ (leída 2026-10-22) | Catálogo observado; no equivale a importe efectivo o vigencia del checkout |
| Web pública Foundations | https://iacedemy.com/foundations/ (leída 2026-10-22) | Banner "Hasta el 16 de octubre" aún visible; oferta de 50 € de pago único |
| KB soporte | `iacademy-soporte/kb/suscripciones-y-planes.md` | Coherente con /pricing/ desde 16-10-2026 |
| KB soporte | `iacademy-soporte/kb/evento-16-octubre.md:54-64` | Define la oferta restringida por correo |

## Catálogo público observado (contrastado: /pricing/ + KB planes + price_book)

- **Pro**: 39 €/mes o 390 €/año (suscripción, sin permanencia, IVA incluido). Checkout: https://buy.stripe.com/9B6bJ1gEU0SJaR750XgEg1c. Coincide con `pro_monthly_2026_10` (3900) y `pro_annual_2026_10` (39000).
- **Premium**: 199 €/mes o 1.990 €/año. Checkout: https://buy.stripe.com/6oU4gzfAQbxnaR7eBxgEg1e. Coincide con `premium_monthly_2026_10` (19900) y `premium_annual_2026_10` (199000).
- **M00–M03 gratuitos** sin tarjeta (https://iacedemy.com/free/). Confirmed por /foundations/ y /pricing/.
- **Itinerario suelto**: 39 € desde la página de cada itinerario (KB); no verificado en página de itinerario concreta.
- **Mentored / Programa Profesional**: 3.000 € desde el 17-10 (KB y /foundations/ "Ver programa Mentored"); pago tras llamada de diagnóstico, sin checkout público directo. price_book tiene `programa_profesional` a 1.500,00 € (150000 céntimos) → **contradice el precio público actual** (posible resto de precio pre-17-10 de 1.500 €).
- **Empresas**: Team 240 €/seat/año (10-24), Business 180 € (25-99), Enterprise 120 € (100-250), IVA excluido. Coincide site-config ↔ price_book ↔ KB (https://iacedemy.com/enterprise/).
- **Garantía**: 14 días naturales. **PRIMER30**: −20 % primera compra, solo en Pro/Premium de /pricing/, no combinable con la oferta del correo.
- Telefónico público: 919 93 27 93.

Los enlaces de checkout citados son los publicados en las fuentes, no compras ni sesiones de pago verificadas. Ningún importe o condición de esta revisión interna se habilita automáticamente en el canal social.

## Oferta restringida — NO propagar al público (kb/evento-16-octubre.md:58-64)

- Existen condiciones comerciales restringidas a destinatarios de un correo. Se han consultado para excluirlas del conocimiento público; no se reproducen aquí importes, condiciones ni enlaces.
- El canal social no comprueba elegibilidad ni gestiona esa oferta automáticamente.
- Regla: una consulta sobre una promoción privada se deriva a humano **sin confirmar ni negar condiciones ni facilitar enlaces privados**.

## Contradicciones detectadas

1. **site-config.json caducado** (2026-09-20): sigue en escalera Founding (99/19, deadline 15-10) y "después" pro 199 € de pago único. La realidad desde 16-10 es suscripción 39/390. Es la "fuente única de cifras" del generador del sitio → riesgo de regenerar contenido con precios muertos. **Requiere decisión/actualización humana en `iacedemy-web`** (fuera del alcance de F0, es lectura).
2. **Entrada online del evento**: web (/foundations/, /evento/ según KB) y KB dicen **50 €**; price_book `evento_2026_10_streaming` = 500 céntimos (**5 €**) y su nota de archivo habla de "entrada online de 5 EUR". Importe contradictorio (5 € vs 50 €). `evento_2026_10_presencial` = 50,00 € (5000) vs 50 € web: coincide. Sin resolver, **no se declara ningún precio de entrada en el manifiesto**.
3. **Precio evento/50 € de pago único**: la página /foundations/ sigue mostrando "50 € … hasta el 16 de octubre" y "de por vida" pese a haber pasado la fecha; el KB mantiene la entrada de 50 € como vía vigente. No se ha podido verificar si el checkout sigue abierto → **prices_enabled=false para esa vía** hasta confirmación humana.
4. **programa_profesional** a 1.500 € en price_book vs 3.000 € público desde 17-10.
5. Página /foundations/ menciona "10 ponentes" en el banner; el KB del evento dice 8. Menor, sin impacto comercial, pero inconsistency a señalar.

## Gate (conclusión)

- **No habilitar respuestas automáticas de precios** mientras `prices_enabled=false`. Los importes contrastados quedan como evidencia de revisión, no como autorización para ofrecerlos desde el bot.
- Se pueden ensayar hechos públicos no comerciales, enlaces de consulta y derivación humana. La garantía, los descuentos y las condiciones de compra requieren validación comercial antes de su uso productivo.
- Toda consulta sobre una oferta recibida por correo se deriva a humano. El texto de las ofertas restringidas no forma parte del conocimiento público recuperable.

## Hechos que requieren decisión humana

1. Actualizar `iacedemy-web/site-config.json` a la era de suscripciones (o retirar su rol de fuente única).
2. Corregir `evento_2026_10_streaming` (5 € vs 50 €) y `programa_profesional` (1.500 vs 3.000 €) en `scripts/stripe/price_book.json` / Stripe.
3. Decidir si la entrada de 50 € con lifetime sigue vendiéndose tras el evento y limpiar el banner de /foundations/.
4. Confirmar precio público del itinerario suelto (39 €) en una página de itinerario real.
5. Validar el manifiesto `deploy/iacademy/public-knowledge.json` antes de cualquier uso productivo (dueño del contenido comercial: David).
