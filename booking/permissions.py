"""
Права доступа для REST API.
Соответствуют логике booking/decorators.py (группы Admin/SuperAdmin/Specialist и is_staff).
"""
from rest_framework import permissions

from .models import SpecialistProfile


def user_in_groups(user, *group_names):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=group_names).exists()


def is_admin_user(user):
    return user_in_groups(user, 'Admin', 'SuperAdmin')


def is_staff_user(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser or is_admin_user(user)


def is_specialist_user(user):
    if not user or not user.is_authenticated:
        return False
    if not user_in_groups(user, 'Specialist') and not user.is_superuser:
        # Специалист может быть без группы, но с профилем
        pass
    return SpecialistProfile.objects.filter(user=user).exists()


class IsAdminRole(permissions.BasePermission):
    """Полный доступ: группы Admin/SuperAdmin или superuser."""

    def has_permission(self, request, view):
        return is_admin_user(request.user)


class IsStaffRole(permissions.BasePermission):
    """Сотрудник: is_staff / Admin / SuperAdmin."""

    def has_permission(self, request, view):
        return is_staff_user(request.user)


class IsSpecialistRole(permissions.BasePermission):
    """Специалист с профилем SpecialistProfile."""

    def has_permission(self, request, view):
        return is_specialist_user(request.user)


class IsAdminOrReadOnly(permissions.BasePermission):
    """Чтение — любому авторизованному; запись — только Admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_admin_user(request.user)


class IsAdminOrStaffWrite(permissions.BasePermission):
    """Чтение — авторизованным; запись — staff/admin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_staff_user(request.user)


class IsAdminOrOwnSpecialistRead(permissions.BasePermission):
    """
    Admin — полный доступ.
    Specialist — только чтение своих бронирований (фильтруется в queryset).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if is_admin_user(request.user) or is_staff_user(request.user):
            return True
        if request.method in permissions.SAFE_METHODS and is_specialist_user(request.user):
            return True
        return False
