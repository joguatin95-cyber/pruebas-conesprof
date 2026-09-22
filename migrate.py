"""Actualiza una base de datos existente a la version actual del modelo.

Agrega, si faltan:
  - la columna usuarios.cliente_asignado
  - la tabla auditoria (historico de cambios)
  - las columnas de la foto de perfil (usuarios.foto, foto_mime, foto_actualizada_en)
  - la tabla importaciones_pendientes (cargas de Excel a la espera de confirmacion)

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

        # Tipo binario segun el motor: PostgreSQL usa BYTEA, SQLite BLOB.
        binario = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
        nuevas = [
            ("cliente_asignado", "VARCHAR(120)"),
            ("foto", binario),
            ("foto_mime", "VARCHAR(30)"),
            ("foto_actualizada_en", "TIMESTAMP"),
        ]
        for nombre, tipo in nuevas:
            if nombre in columnas:
                print("usuarios.%s ya existe." % nombre)
            else:
                with db.engine.begin() as conexion:
                    conexion.execute(
                        text("ALTER TABLE usuarios ADD COLUMN %s %s" % (nombre, tipo))
                    )
                print("Columna usuarios.%s agregada." % nombre)

        # create_all solo crea lo que falta, no toca las tablas existentes.
        faltantes = [t for t in ("auditoria", "importaciones_pendientes")
                     if t not in tablas]
        if faltantes:
            db.create_all()
            print("Tablas creadas: %s." % ", ".join(faltantes))
        else:
            print("Las tablas auditoria e importaciones_pendientes ya existen.")

        print("Migracion completada.")


if __name__ == "__main__":
    main()
