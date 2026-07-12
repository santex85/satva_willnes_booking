"""
Аутентификация по персональному API-ключу пользователя.
"""
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import UserApiKey


class ApiKeyAuthentication(BaseAuthentication):
    """
    Поддерживаемые заголовки:
    - Authorization: Api-Key satva_...
    - X-Api-Key: satva_...
    - Authorization: Bearer satva_...  (если значение начинается с satva_)
    """

    keyword = b'api-key'

    def authenticate(self, request):
        raw_key = self._extract_key(request)
        if not raw_key:
            return None

        api_key = UserApiKey.authenticate(raw_key)
        if api_key is None:
            raise AuthenticationFailed('Недействительный или отозванный API-ключ')

        api_key.touch_last_used()
        return (api_key.user, api_key)

    def _extract_key(self, request):
        header_key = request.headers.get('X-Api-Key', '').strip()
        if header_key:
            return header_key

        auth = get_authorization_header(request).split()
        if len(auth) == 2:
            scheme = auth[0].lower()
            token = auth[1].decode('utf-8')
            if scheme == self.keyword.decode('utf-8'):
                return token.strip()
            if scheme == 'bearer' and token.startswith('satva_'):
                return token.strip()
        return None
