from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_client_key(request):
    """
    Usa o IP real do cliente quando disponível em X-Forwarded-For.
    Sem isso, dentro da rede Docker todos os requests chegam com o IP do
    gateway e o rate limit seria compartilhado entre todos os usuários.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_client_key)
