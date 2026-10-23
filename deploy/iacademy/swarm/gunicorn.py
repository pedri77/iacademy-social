"""TLS interno: Caddy valida la CA y Gunicorn solo admite TLS 1.3."""

import ssl


def ssl_context(_config, default_ssl_context_factory):
    context = default_ssl_context_factory()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context
