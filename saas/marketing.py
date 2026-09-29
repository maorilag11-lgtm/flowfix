"""Serve the reviewed public website without exposing private source files."""
import base64
import hashlib
import mimetypes
import re
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect

PUBLIC_FILES = frozenset(['about.html', 'apple-touch-icon.png', 'contact.html', 'cookie-consent.js', 'cookie.png', 'coverage.html', 'diagnosis.html', 'docs.html', 'errors.html', 'favicon-32.png', 'favicon-48.png', 'hero-ferrofluid.js', 'hero-mask.jpg', 'hero-mask.mp4', 'hero-mask.webm', 'how-it-works.html', 'index.html', 'login.html', 'logo.webp', 'privacy.html', 'product-access.js', 'product-config.js', 'security.html', 'shot-history.webp', 'shot-inconclusive.webp', 'shot-newdiagnosis.webp', 'shot-verdict.webp', 'terms.html'])


def serve(request, name):
    if name not in PUBLIC_FILES:
        raise Http404
    if name == 'login.html':
        return redirect('/signup/' if request.GET.get('mode') == 'signup' else '/login/')
    file = settings.BASE_DIR / 'marketing' / name
    if not file.is_file():
        raise Http404
    if file.suffix != '.html':
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return FileResponse(file.open('rb'), content_type=content_type)
    content = file.read_text()
    # Authorize only the exact inline scripts shipped with the public website.
    hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(code.encode()).digest()).decode() + "'"
              for code in re.findall(r'<script\b[^>]*>(.*?)</script\s*>', content, re.I | re.S) if code.strip()]
    response = HttpResponse(content, content_type='text/html; charset=utf-8')
    response.marketing_csp = (
        "default-src 'self'; script-src 'self' " + ' '.join(hashes) + "; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "media-src 'self'; connect-src 'self'; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response
