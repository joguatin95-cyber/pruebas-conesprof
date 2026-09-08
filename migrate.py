"""Actualiza una base de datos existente a la version actual del modelo.

Agrega, si faltan:
  - la columna usuarios.cliente_asignado
  - la tabla auditoria (historico de cambios)

Es idempotente: puede ejecutarse varias veces sin efecto adicional.
Funciona con PostgreSQL y con SQLite.

Uso:  python migrate.py
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def main():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        tablas = inspector.get_table_names()

        if "usuarios" not in tablas:
            print("La base esta vacia. Ejecute 'python seed.py' en lugar de este script.")
            return

        columnas = {c["name"] for c in inspector.get_columns("usuarios")}
        if "cliente_asignado" in columnas:
            print("usuarios.cliente_asignado ya existe.")
        else:
            with db.engine.begin() as conexion:
                conexion.execute(
                    text("ALTER TABLE usuarios ADD COLUMN cliente_asignado VARCHAR(120)")
                )
            print("Columna usuarios.cliente_asignado agregada.")

        if "auditoria" in tablas:
            print("La tabla auditoria ya existe.")
        else:
            # create_all solo crea lo que falta, no toca las tablas existentes.
            db.create_all()
            print("Tabla auditoria creada.")

        print("Migracion completada.")


if __name__ == "__main__":
    main()
