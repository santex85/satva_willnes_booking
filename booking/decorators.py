"""
Декораторы для проверки прав доступа пользователей
"""
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.contrib.auth.views import redirect_to_login


def group_required(*group_names):
    """
    Декоратор для проверки принадлежности пользователя к одной из указанных групп.
    
    Для AJAX-запросов возвращает JSON-ответ с ошибкой 403.
    Для обычных запросов вызывает PermissionDenied.
    
    Usage:
        @group_required('Admin', 'SuperAdmin')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # Проверяем авторизацию (request.user.is_authenticated проверяется автоматически Django)
            if not request.user.is_authenticated:
                # Для AJAX-запросов возвращаем JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': 'Требуется авторизация'}, status=401)
                # Для обычных запросов - редирект на логин
                return redirect_to_login(request.path)
            
            # Проверяем группы
            if request.user.groups.filter(name__in=group_names).exists() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                # Для AJAX-запросов возвращаем JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': 'Доступ запрещен'}, status=403)
                # Для обычных запросов вызываем PermissionDenied
                raise PermissionDenied
        return wrapper
    return decorator


# Готовые декораторы для удобства
admin_required = group_required('Admin', 'SuperAdmin')
specialist_required = group_required('Specialist')


