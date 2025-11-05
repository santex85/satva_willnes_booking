"""
Декораторы для проверки прав доступа пользователей
"""
from django.core.exceptions import PermissionDenied


def group_required(*group_names):
    """
    Декоратор для проверки принадлежности пользователя к одной из указанных групп.
    
    Usage:
        @group_required('Admin', 'SuperAdmin')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.user.groups.filter(name__in=group_names).exists() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                raise PermissionDenied
        return wrapper
    return decorator


# Готовые декораторы для удобства
admin_required = group_required('Admin', 'SuperAdmin')
specialist_required = group_required('Specialist')


