"""Punto de entrada WSGI para el servidor de produccion (gunicorn).

Expone un objeto 'app' a nivel de modulo, de modo que el comando de arranque sea
simplemente:

    gunicorn wsgi:app --bind 0.0.0.0:$PORT

Sin comillas ni parentesis, que dependen de como el proveedor interprete el comando.
"""

from app import create_app

app = create_app()
