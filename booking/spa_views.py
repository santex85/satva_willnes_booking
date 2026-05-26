from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def index(request):
    """Отдаёт собранный React SPA."""
    index_path = Path(settings.FRONTEND_DIST) / 'index.html'
    if not index_path.exists():
        return HttpResponse(
            'Frontend не собран. Выполните: npm --prefix frontend run build',
            status=503,
            content_type='text/plain; charset=utf-8',
        )
    return FileResponse(index_path.open('rb'), content_type='text/html; charset=utf-8')
