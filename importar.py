"""Importacion de procesos desde consola.

Adaptador de linea de comandos sobre el caso de uso ImportarProcesos, el mismo que
usa la pantalla web (Procesos -> Importar Excel). Aqui no hay ninguna regla de
validacion: solo se leen argumentos y se imprime el resultado.

Por seguridad, de forma predeterminada solo SIMULA la carga. Para escribir hay que
agregar --aplicar de forma explicita.

Uso:
    python importar.py datos.xlsx                 # simula y muestra el informe
    python importar.py datos.xlsx --aplicar       # importa de verdad
    python importar.py datos.xlsx --hoja "Datos"  # elige la hoja del Excel
    python importar.py datos.xlsx --conservar-id  # respeta la columna ID del archivo
    python importar.py datos.xlsx --permitir-duplicados
    python importar.py datos.xlsx --limite 20     # solo las primeras 20 filas

Columnas reconocidas (el orden no importa, mayusculas y tildes son indiferentes):
    ID, FECHA INICIO, CLIENTE, SUBCLIENTE, TIPO DE PROCESO, CIUDAD, CEDULA,
    NOMBRE, CARGO, FECHA FINALIZACION, ESTADO, FACTURA, ORDEN DE COMPRA

Obligatorias: FECHA INICIO, CLIENTE, TIPO DE PROCESO, CEDULA, NOMBRE
"""

import argparse
import csv
import os
import sys

from app import create_app
from app.aplicacion.importar_procesos import ImportarProcesos, OpcionesImportacion
from app.aplicacion.puertos import ErrorDeLectura
from app.dominio.procesos import CAMPOS, TITULOS
from app.infraestructura.lectores import lector_para
from app.infraestructura.repositorios import (
    AuditoriaSQLAlchemy,
    RepositorioProcesosSQLAlchemy,
)

MAXIMO_A_LISTAR = 20


def argumentos():
    parser = argparse.ArgumentParser(
        description="Importa procesos desde un archivo Excel o CSV.")
    parser.add_argument("archivo", help="ruta del archivo .xlsx, .xlsm o .csv")
    parser.add_argument("--aplicar", action="store_true",
                        help="escribe en la base (sin este parametro solo simula)")
    parser.add_argument("--hoja", help="nombre de la hoja del Excel a leer")
    parser.add_argument("--conservar-id", action="store_true",
                        help="usa la columna ID del archivo en lugar de generar uno nuevo")
    parser.add_argument("--permitir-duplicados", action="store_true",
                        help="importa tambien los registros que ya existen")
    parser.add_argument("--limite", type=int,
                        help="procesa solo las primeras N filas (para probar)")
    return parser.parse_args()


def informar(resultado, ruta):
    print("Origen             : %s" % resultado.origen)
    print("Columnas           : %s" % ", ".join(resultado.columnas_reconocidas))
    if resultado.columnas_ignoradas:
        print("Ignoradas          : %s" % ", ".join(resultado.columnas_ignoradas))
    print("")
    print("Filas leidas       : %d" % resultado.filas_leidas)
    print("Listas para cargar : %d" % resultado.total_validas)
    print("Duplicadas         : %d" % resultado.total_duplicadas)
    print("Con errores        : %d" % resultado.total_rechazadas)

    if resultado.duplicadas:
        print("")
        print("--- DUPLICADAS (no se cargan) ---")
        for d in resultado.duplicadas[:15]:
            print("  Fila %-5d %s / %s / %s  (%s)"
                  % (d.numero, d.fila.cedula, d.fila.cliente,
                     d.fila.fecha_inicio, d.donde))
        if resultado.total_duplicadas > 15:
            print("  ... y %d mas" % (resultado.total_duplicadas - 15))

    if resultado.rechazadas:
        print("")
        print("--- CON ERRORES (no se cargan) ---")
        for f in resultado.rechazadas[:MAXIMO_A_LISTAR]:
            print("  Fila %-5d %s" % (f.numero, f.motivo))
        if resultado.total_rechazadas > MAXIMO_A_LISTAR:
            print("  ... y %d mas" % (resultado.total_rechazadas - MAXIMO_A_LISTAR))
        print("")
        print("Detalle completo de los rechazos: %s" % guardar_rechazadas(resultado, ruta))


def guardar_rechazadas(resultado, ruta):
    informe = os.path.splitext(ruta)[0] + "_rechazadas.csv"
    with open(informe, "w", encoding="utf-8-sig", newline="") as salida:
        escritor = csv.writer(salida, delimiter=";")
        escritor.writerow(["FILA", "MOTIVO"] + [TITULOS[c] for c in CAMPOS])
        for fila in resultado.rechazadas:
            escritor.writerow([fila.numero, fila.motivo]
                              + [fila.valores.get(c, "") for c in CAMPOS])
    return informe


def main():
    args = argumentos()
    if not os.path.exists(args.archivo):
        raise SystemExit("No se encontro el archivo: " + args.archivo)

    with open(args.archivo, "rb") as archivo:
        contenido = archivo.read()

    app = create_app()
    with app.app_context():
        repositorio = RepositorioProcesosSQLAlchemy()
        try:
            caso_de_uso = ImportarProcesos(
                lector=lector_para(args.archivo),
                repositorio=repositorio,
                auditoria=AuditoriaSQLAlchemy(),
            )
        except ErrorDeLectura as error:
            raise SystemExit(str(error))

        print("Archivo            : %s" % args.archivo)
        print("Destino            : %s"
              % app.config["SQLALCHEMY_DATABASE_URI"].split("://")[0])
        print("Modo               : %s"
              % ("APLICAR (escribe en la base)" if args.aplicar
                 else "SIMULACION (no escribe nada)"))

        opciones = OpcionesImportacion(
            aplicar=args.aplicar,
            hoja=args.hoja,
            conservar_id=args.conservar_id,
            permitir_duplicados=args.permitir_duplicados,
            limite=args.limite,
        )
        try:
            resultado = caso_de_uso.ejecutar(
                contenido, os.path.basename(args.archivo), opciones)
        except ErrorDeLectura as error:
            raise SystemExit("\n" + str(error))

        informar(resultado, args.archivo)

        if not args.aplicar:
            print("")
            print("Esto fue una SIMULACION: no se escribio nada en la base.")
            print("Si el informe se ve bien, repita el comando agregando --aplicar")
            return 0

        if not resultado.aplicado:
            print("")
            print("No hay filas validas para cargar.")
            return 1

        print("")
        print("IMPORTACION COMPLETADA: %d registros cargados."
              % resultado.total_validas)
        print("La tabla procesos tiene ahora %d registros." % repositorio.total())
    return 0


if __name__ == "__main__":
    sys.exit(main())
