"""Crea las tablas y el usuario ADMINISTRADOR inicial.

Uso:  python seed.py            -> crea tablas + admin
      python seed.py --demo     -> ademas carga registros de ejemplo
"""

import os
import sys
from datetime import date, timedelta

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Proceso, Usuario


def crear_admin():
    username = os.getenv("ADMIN_USERNAME", "admin")
    if db.session.scalar(select(Usuario).where(Usuario.username == username)):
        print(f"El usuario '{username}' ya existe, no se modifica.")
        return

    admin = Usuario(
        username=username,
        nombre=os.getenv("ADMIN_NOMBRE", "Administrador General"),
        email=os.getenv("ADMIN_EMAIL", "admin@empresa.com"),
        rol="ADMINISTRADOR",
        activo=True,
    )
    password = os.getenv("ADMIN_PASSWORD", "Admin123*")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Administrador creado -> usuario: {username} / contrasena: {password}")
    print("Cambie esta contrasena despues del primer ingreso.")


def crear_demo():
    if db.session.scalar(select(Proceso)):
        print("Ya existen procesos, no se cargan datos de ejemplo.")
        return

    hoy = date.today()
    ejemplos = [
        ("ALMACENES EXITO", "BODEGA NORTE", "SELECCION", "MEDELLIN", "1017234567",
         "JUAN PEREZ", "AUXILIAR LOGISTICO", "FINALIZADO", "FA-1001", "OC-5510", 12),
        ("BANCOLOMBIA", "OFICINA CENTRO", "VISITA DOMICILIARIA", "BOGOTA", "52987654",
         "MARIA GOMEZ", "ASESOR COMERCIAL", "EN PROCESO", "FA-1002", "OC-5511", None),
        ("SURA", None, "POLIGRAFIA", "CALI", "1144556677",
         "CARLOS RUIZ", "ANALISTA", "PENDIENTE", None, "OC-5512", None),
        ("GRUPO NUTRESA", "PLANTA SUR", "ESTUDIO DE SEGURIDAD", "BARRANQUILLA", "1098765432",
         "LAURA DIAZ", "SUPERVISORA", "FINALIZADO", "FA-1003", "OC-5513", 5),
    ]

    for i, (cli, sub, tipo, ciudad, ced, nom, cargo, estado, fac, oc, dias) in enumerate(ejemplos):
        inicio = hoy - timedelta(days=30 - i * 5)
        db.session.add(
            Proceso(
                fecha_inicio=inicio, cliente=cli, subcliente=sub, tipo_proceso=tipo,
                ciudad=ciudad, cedula=ced, nombre=nom, cargo=cargo, estado=estado,
                factura=fac, orden_compra=oc,
                fecha_finalizacion=inicio + timedelta(days=dias) if dias else None,
            )
        )
    db.session.commit()
    print(f"{len(ejemplos)} procesos de ejemplo cargados.")


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        print(f"Tablas verificadas en: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        crear_admin()
        if "--demo" in sys.argv:
            crear_demo()


if __name__ == "__main__":
    main()
