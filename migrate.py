"""Actualiza una base de datos existente a la version actual del modelo.

Agrega, si faltan:
  - la columna usuarios.cliente_asignado
  - la columna usuarios.proveedor_asignado y la columna procesos.proveedor
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

        # Tipo binario segun el motor: PostgreSQL usa BYTEA, SQLite BLOB.
        binario = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
        nuevas = {
            "usuarios": [
                ("cliente_asignado", "VARCHAR(120)"),
                ("proveedor_asignado", "VARCHAR(120)"),
                ("foto", binario),
                ("foto_mime", "VARCHAR(30)"),
                ("foto_actualizada_en", "TIMESTAMP"),
            ],
            "procesos": [
                ("proveedor", "VARCHAR(120)"),
            ],
        }
        for tabla, columnas_nuevas in nuevas.items():
            if tabla not in tablas:
                continue
            existentes = {c["name"] for c in inspector.get_columns(tabla)}
            for nombre, tipo in columnas_nuevas:
                if nombre in existentes:
                    print("%s.%s ya existe." % (tabla, nombre))
                    continue
                with db.engine.begin() as conexion:
                    conexion.execute(
                        text("ALTER TABLE %s ADD COLUMN %s %s" % (tabla, nombre, tipo)))
                print("Columna %s.%s agregada." % (tabla, nombre))

        # El indice del proveedor acelera el filtro de alcance del rol PROVEEDOR.
        if "procesos" in tablas:
            indices = {i["name"] for i in inspector.get_indexes("procesos")}
            if "ix_procesos_proveedor" not in indices:
                with db.engine.begin() as conexion:
                    conexion.execute(text(
                        "CREATE INDEX ix_procesos_proveedor ON procesos (proveedor)"))
                print("Indice ix_procesos_proveedor creado.")
            else:
                print("El indice ix_procesos_proveedor ya existe.")

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
