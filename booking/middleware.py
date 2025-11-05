"""
Middleware для централизованного логирования и обработки ошибок
"""
import logging
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class ErrorLoggingMiddleware:
    """
    Middleware для логирования ошибок и HTTP ответов с кодами >= 400
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Логируем HTTP ответы с кодами >= 400
        if response.status_code >= 400:
            logger.warning(
                f"HTTP {response.status_code}: {request.method} {request.path}",
                extra={
                    'status_code': response.status_code,
                    'user': getattr(request.user, 'username', 'anonymous'),
                    'path': request.path,
                    'method': request.method,
                }
            )
        
        return response

    def process_exception(self, request, exception):
        """
        Обработка исключений с логированием
        """
        logger.error(
            f"Exception in {request.method} {request.path}: {exception}",
            exc_info=True,
            extra={
                'user': getattr(request.user, 'username', 'anonymous'),
                'path': request.path,
                'method': request.method,
            }
        )
        
        # Для API запросов возвращаем JSON
        if request.path.startswith('/api/'):
            if isinstance(exception, PermissionDenied):
                return JsonResponse(
                    {'error': 'Доступ запрещён'},
                    status=403
                )
            return JsonResponse(
                {'error': 'Внутренняя ошибка сервера'},
                status=500
            )
        
        # Для остальных - пропускаем дальше (Django покажет 500.html)
        return None


