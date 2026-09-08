"""Verifica la conexion a la base de datos configurada en .env

Muestra el motor, el servidor, la version de PostgreSQL y el estado de las tablas.
Nunca imprime la contrasena.

Uso:  python check_db.py
"""

import re
import sys

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

TABLAS_ESPERADAS = {"usuarios", "procesos", "auditoria"}


def enmascarar(url: str) -> str:
    """Oculta la contrasena de la cadena de conexion antes de mostrarla."""
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


def main():
    app = create_app()
    url = app.config["SQLALCHEMY_DATABASE_URI"]
    motor = url.split(":", 1)[0]

    print("Cadena de conexion : " + enmascarar(url))

    if motor.startswith("sqlite"):
        print("")
        print("AVISO: se esta usando SQLite, no PostgreSQL.")
        print("Defina DATABASE_URL en el archivo .env con la cadena de Render.")
        return 1

    with app.app_context():
        try:
            with db.engine.connect() as conexion:
                version = conexion.execute(text("SELECT version()")).scalar()
                base = conexion.execute(text("SELECT current_database()")).scalar()
                usuario = conexion.execute(text("SELECT current_user")).scalar()
                cifrado = conexion.execute(
                    text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
                ).scalar()
        except Exception as error:  # noqa: BLE001 - se muestra el diagnostico al usuario
            print("")
            print("NO SE PUDO CONECTAR.")
            print("Detalle: " + enmascarar(str(error).strip().splitlines()[0]))
            print("")
            print("Revise que:")
            print("  - La cadena sea la 'External Database URL' de Render, no la interna.")
            print("  - La base siga activa en Render (las gratuitas expiran a los 30 dias).")
            print("  - No haya un firewall o proxy bloqueando el puerto 5432.")
            return 1

        print("Conexion            : OK")
        print("Base de datos       : " + str(base))
        print("Usuario             : " + str(usuario))
        print("Cifrado TLS         : " + ("si" if cifrado else "no"))
        print("Version             : " + str(version).split(" on ")[0])

        tablas = set(inspect(db.engine).get_table_names())
        faltantes = TABLAS_ESPERADAS - tablas
        print("Tablas encontradas  : " + (", ".join(sorted(tablas)) or "(ninguna)"))

        if faltantes:
            print("")
            print("Faltan tablas: " + ", ".join(sorted(faltantes)))
            print("Ejecute 'python seed.py' para crearlas.")
            return 2

        for tabla in sorted(TABLAS_ESPERADAS):
            with db.engine.connect() as conexion:
                total = conexion.execute(text("SELECT count(*) FROM " + tabla)).scalar()
            print("  %-12s %s registro(s)" % (tabla, total))

    print("")
    print("La base de datos esta lista.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
