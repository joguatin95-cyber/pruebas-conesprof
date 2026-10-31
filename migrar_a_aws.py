"""Copia la base de datos de un servidor PostgreSQL a otro.

Se escribio para pasar de Supabase a Amazon RDS, pero sirve entre cualquier par
de servidores PostgreSQL. No hace falta instalar pg_dump: usa el mismo psycopg2
que ya usa la aplicacion, y el esquema lo crea a partir de los modelos.

Las dos cadenas de conexion se leen del .env, nunca de la linea de comandos, para
que no queden en el historial de la consola:

    DATABASE_URL=postgresql://...        <- origen (el servidor actual)
    DATABASE_URL_AWS=postgresql://...    <- destino (el servidor nuevo)

Uso:
    python migrar_a_aws.py --probar    comprueba que se llega a los dos servidores
    python migrar_a_aws.py             crea el esquema y copia los datos
    python migrar_a_aws.py --forzar    vacia el destino antes de copiar
"""

import os
import sys

from sqlalchemy import create_engine, func, inspect, select, text

from app.config import normalizar_url
from app.extensions import db
from app import models  # noqa: F401  importarlo registra las tablas en el metadata

# Orden de copia: las tablas referenciadas van primero, porque procesos apunta a
# usuarios con una clave ajena.
ORDEN = ("usuarios", "procesos", "auditoria", "importaciones_pendientes")

# Filas por lote. Las tablas traen binarios (fotos, archivos de importacion), asi
# que se copian por partes en vez de cargarlas enteras en memoria.
LOTE = 500


def leer_url(variable):
    url = normalizar_url(os.getenv(variable, "").strip().strip('"').strip("'"))
    if "://" not in url:
        salir("Falta %s en el .env (o no es una cadena de conexion valida)."
              % variable)
    if not url.startswith("postgresql"):
        salir("%s no apunta a PostgreSQL. Este script solo copia entre servidores "
              "PostgreSQL." % variable)
    return url


def salir(mensaje):
    print("\n  " + mensaje + "\n")
    sys.exit(1)


def describir(url):
    """Servidor y base, sin usuario ni contrasena, para poder mostrarlo sin riesgo."""
    cola = url.rsplit("@", 1)[-1]
    return cola.split("?")[0]


def version(conexion):
    return conexion.execute(text("SELECT version()")).scalar().split(",")[0]


def conteos(conexion, tablas):
    presentes = set(inspect(conexion).get_table_names())
    return {t: (conexion.execute(select(func.count()).select_from(
        db.metadata.tables[t])).scalar() if t in presentes else None)
        for t in tablas}


def mostrar_conteos(titulo, datos):
    print("  " + titulo)
    for tabla, n in datos.items():
        print("    %-26s %s" % (tabla, "no existe" if n is None else "%6d" % n))


def probar(url_origen, url_destino):
    for etiqueta, url in (("ORIGEN ", url_origen), ("DESTINO", url_destino)):
        print("\n%s  %s" % (etiqueta, describir(url)))
        try:
            with create_engine(url, connect_args={"connect_timeout": 10}).connect() as c:
                print("  conectado: %s" % version(c))
                mostrar_conteos("filas:", conteos(c, ORDEN))
        except Exception as error:
            print("  NO SE PUDO CONECTAR")
            print("  %s" % str(error).strip().splitlines()[0])
            return False
    print()
    return True


def copiar_tabla(origen, destino, tabla):
    """Copia una tabla por lotes conservando los id."""
    columnas = [c.name for c in tabla.columns]
    total = 0
    resultado = origen.execution_options(stream_results=True).execute(
        select(tabla).order_by(tabla.c.id))

    while True:
        filas = resultado.fetchmany(LOTE)
        if not filas:
            break
        destino.execute(
            tabla.insert(),
            [{c: valor for c, valor in zip(columnas, fila)} for fila in filas])
        total += len(filas)
        print("    %s: %d filas" % (tabla.name, total))

    return total


def vaciar(conexion):
    """Borra el contenido del destino.

    Se hace en una sola sentencia porque CASCADE resuelve el orden de las
    claves ajenas, por si el destino se reutiliza.
    """
    conexion.execute(text("TRUNCATE %s CASCADE" % ", ".join(ORDEN)))


def reiniciar_secuencia(conexion, nombre):
    """Deja el contador de id por encima del ultimo copiado.

    Sin esto el primer registro que se cree en el destino intentaria usar el id 1,
    que ya esta ocupado, y la insercion fallaria.
    """
    conexion.execute(text(
        "SELECT setval(pg_get_serial_sequence('%s', 'id'), "
        "COALESCE((SELECT MAX(id) FROM %s), 1))" % (nombre, nombre)))


def main():
    forzar = "--forzar" in sys.argv

    url_origen = leer_url("DATABASE_URL")
    url_destino = leer_url("DATABASE_URL_AWS")

    if describir(url_origen) == describir(url_destino):
        salir("El origen y el destino son el mismo servidor. Revise el .env.")

    if "--probar" in sys.argv:
        sys.exit(0 if probar(url_origen, url_destino) else 1)

    motor_origen = create_engine(url_origen, connect_args={"connect_timeout": 10})
    motor_destino = create_engine(url_destino, connect_args={"connect_timeout": 10})

    print("\nORIGEN   %s" % describir(url_origen))
    print("DESTINO  %s\n" % describir(url_destino))

    # El esquema del destino se crea a partir de los modelos, asi queda con las
    # mismas columnas e indices que espera la aplicacion.
    db.metadata.create_all(motor_destino)
    print("  Esquema verificado en el destino.\n")

    with motor_origen.connect() as origen:
        pendientes = conteos(origen, ORDEN)
        mostrar_conteos("En el origen hay:", pendientes)

        with motor_destino.begin() as destino:
            ocupadas = {t: n for t, n in conteos(destino, ORDEN).items() if n}
            if ocupadas and not forzar:
                print()
                mostrar_conteos("El destino ya tiene datos:", ocupadas)
                salir("No se copio nada. Use --forzar para vaciar el destino "
                      "antes de copiar.")

            if ocupadas:
                vaciar(destino)
                print("\n  Destino vaciado.")

            print("\n  Copiando:")
            copiadas = {}
            for nombre in ORDEN:
                if not pendientes.get(nombre):
                    print("    %s: vacia, se omite" % nombre)
                    copiadas[nombre] = 0
                    continue
                copiadas[nombre] = copiar_tabla(
                    origen, destino, db.metadata.tables[nombre])

            for nombre in ORDEN:
                reiniciar_secuencia(destino, nombre)
            print("\n  Contadores de id reiniciados.")

    # La comprobacion se hace con una conexion nueva, ya cerrada la transaccion,
    # para leer lo que de verdad quedo guardado.
    with motor_destino.connect() as destino:
        finales = conteos(destino, ORDEN)

    print()
    mostrar_conteos("Resultado en el destino:", finales)

    diferencias = [t for t in ORDEN if (pendientes.get(t) or 0) != (finales.get(t) or 0)]
    if diferencias:
        salir("NO COINCIDEN: %s. Revise el error y vuelva a ejecutar con --forzar."
              % ", ".join(diferencias))

    print("\n  Migracion completada: el destino tiene las mismas filas que el origen.\n")


if __name__ == "__main__":
    main()
