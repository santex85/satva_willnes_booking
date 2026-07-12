"""
Веб-страница управления API-ключами в профиле пользователя.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import UserApiKey


@login_required
def api_keys_profile_view(request):
    """Список и создание API-ключей текущего пользователя."""
    keys = UserApiKey.objects.filter(user=request.user).order_by('-created_at')
    new_key_plain = request.session.pop('new_api_key_plain', None)
    new_key_name = request.session.pop('new_api_key_name', None)

    return render(request, 'booking/api_keys_profile.html', {
        'keys': keys,
        'new_key_plain': new_key_plain,
        'new_key_name': new_key_name,
    })


@login_required
@require_POST
def api_key_create_view(request):
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, 'Укажите название ключа')
        return redirect('api_keys_profile')

    api_key = UserApiKey.create_for_user(user=request.user, name=name)
    request.session['new_api_key_plain'] = api_key._plain_key
    request.session['new_api_key_name'] = api_key.name
    messages.success(request, f'API-ключ «{api_key.name}» создан. Скопируйте его сейчас — больше он не будет показан.')
    return redirect('api_keys_profile')


@login_required
@require_POST
def api_key_revoke_view(request, pk):
    updated = UserApiKey.objects.filter(pk=pk, user=request.user, is_active=True).update(is_active=False)
    if updated:
        messages.success(request, 'API-ключ отозван')
    else:
        messages.error(request, 'Ключ не найден или уже отозван')
    return redirect('api_keys_profile')
