"""
Custom error page handlers, registered in config/urls.py (handler403/404/500).
Django only calls these when DEBUG=False -- locally you'll still see
Django's own debug tracebacks, which is what you want during development.
"""
from django.shortcuts import render


def error_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)


def error_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    # No context processors run for the 500 handler (the error may be a
    # context processor itself failing), so keep this template minimal.
    return render(request, 'errors/500.html', status=500)
