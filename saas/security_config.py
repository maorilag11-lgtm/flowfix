"""Fail closed before serving requests with unsafe production settings."""
from urllib.parse import urlsplit,unquote,parse_qs


def postgres_url_config(value):
    """Accept a server-owned Postgres URL without ever reflecting its secrets."""
    try:
        url=urlsplit(value)
        options=parse_qs(url.query,keep_blank_values=True)
        if (url.scheme not in ('postgres','postgresql') or not url.hostname
            or not url.username or not url.password or not url.path.lstrip('/')
            or url.fragment or set(options)-{'sslmode'}):raise ValueError()
        modes=options.get('sslmode',['require'])
        if len(modes)!=1 or modes[0] not in ('require','verify-ca','verify-full'):raise ValueError()
        port=url.port or 5432
        return {'ENGINE':'django.db.backends.postgresql','HOST':url.hostname,
                'PORT':str(port),'NAME':unquote(url.path[1:]),'USER':unquote(url.username),
                'PASSWORD':unquote(url.password),'CONN_MAX_AGE':60,
                'OPTIONS':{'sslmode':modes[0]}}
    except (ValueError,TypeError):
        raise RuntimeError('DATABASE_URL must be a complete PostgreSQL URL with TLS enabled') from None


def validate_production(secret_key, allowed_hosts, public_url):
    # Same structural minimum as Django's deployment check; not an entropy test.
    if len(secret_key)<50 or len(set(secret_key))<5 or secret_key.startswith('django-insecure-'):
        raise RuntimeError('Production requires a strong, independently generated DJANGO_SECRET_KEY')
    if not allowed_hosts or any(not h or '*' in h or h.startswith('.') for h in allowed_hosts):
        raise RuntimeError('Production requires explicit DJANGO_ALLOWED_HOSTS without wildcards')
    try:
        url=urlsplit(public_url)
        port=url.port  # Validate malformed ports too.
        valid=(url.scheme=='https' and url.hostname and not url.username and not url.password
               and not url.query and not url.fragment and url.path in ('','/')
               and not any(c.isspace() for c in public_url)
               and url.hostname.lower() in [h.lower() for h in allowed_hosts])
    except ValueError:
        valid=False
    if not valid:
        raise RuntimeError('PUBLIC_URL must be an HTTPS origin whose hostname is explicitly allowed')
