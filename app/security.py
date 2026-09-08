from functools import wraps

from flask import abort
from flask_login import current_user


def solo_administrador(view):
    """Restringe una vista al rol ADMINISTRADOR."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.es_administrador:
            abort(403)
        return view(*args, **kwargs)

    return wrapper
