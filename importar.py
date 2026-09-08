"""Importacion masiva de procesos desde un archivo Excel (.xlsx) o CSV.

Por seguridad, de forma predeterminada solo SIMULA la carga: valida todo el archivo
y muestra el resultado sin escribir nada en la base. Para escribir hay que agregar
--aplicar de forma explicita.

Uso:
    python importar.py datos.xlsx                 # simula y muestra el informe
    python importar.py datos.xlsx --aplicar       # importa de verdad
    python importar.py datos.csv --hoja "Hoja1"   # elige la hoja del Excel
    python importar.py datos.xlsx --conservar-id  # respeta la columna ID del archivo
    python importar.py datos.xlsx --permitir-duplicados

Columnas reconocidas (el orden no importa, mayusculas y tildes son indiferentes):
    ID, FECHA INICIO, CLIENTE, SUBCLIENTE, TIPO DE PROCESO, CIUDAD, CEDULA,
    NOMBRE, CARGO, FECHA FINALIZACION, ESTADO, FACTURA, ORDEN DE COMPRA

Obligatorias: FECHA INICIO, CLIENTE, TIPO DE PROCESO, CEDULA, NOMBRE
"""

import argparse
import csv
import os
import sys
import unicodedata
from datetime import date, datetime, timedelta

from sqlalchemy import select, text

from app import create_app
from app.auditoria import registrar
from app.extensions import db
from app.models import ESTADOS, Proceso

# --- Definicion de columnas -------------------------------------------------

# Nombre interno -> encabezados aceptados en el archivo.
ALIAS = {
    "id": ["ID", "NO", "NUMERO", "CONSECUTIVO"],
    "fecha_inicio": ["FECHA INICIO", "FECHA DE INICIO", "FECHAINICIO", "INICIO",
                     "FECHA RADICACION", "FECHA DE RADICACION"],
    "cliente": ["CLIENTE", "EMPRESA"],
    "subcliente": ["SUBCLIENTE", "SUB CLIENTE", "SUCURSAL", "SEDE"],
    "tipo_proceso": ["TIPO DE PROCESO", "TIPO PROCESO", "TIPO", "PROCESO", "SERVICIO"],
    "ciudad": ["CIUDAD", "MUNICIPIO"],
    "cedula": ["CEDULA", "DOCUMENTO", "NO DOCUMENTO", "NUMERO DE DOCUMENTO",
               "IDENTIFICACION", "NO IDENTIFICACION", "CC"],
    "nombre": ["NOMBRE", "NOMBRE COMPLETO", "NOMBRES", "CANDIDATO", "EVALUADO"],
    "cargo": ["CARGO", "PUESTO"],
    "fecha_finalizacion": ["FECHA FINALIZACION", "FECHA DE FINALIZACION", "FECHA FIN",
                           "FECHA FINAL", "FINALIZACION", "FECHA ENTREGA"],
    "estado": ["ESTADO", "ESTATUS", "STATUS"],
    "factura": ["FACTURA", "NO FACTURA", "NUMERO DE FACTURA", "FACTURA NO"],
    "orden_compra": ["ORDEN DE COMPRA", "ORDEN COMPRA", "OC", "ORDEN"],
}

OBLIGATORIAS = ["fecha_inicio", "cliente", "tipo_proceso", "cedula", "nombre"]

# Nombre interno -> como se llama la columna en los mensajes de error.
TITULO = {interno: variantes[0] for interno, variantes in ALIAS.items()}

# Longitud maxima de cada columna de texto, segun el modelo.
LARGOS = {
    "cliente": 120, "subcliente": 120, "tipo_proceso": 120, "ciudad": 80,
    "cedula": 30, "nombre": 150, "cargo": 120, "estado": 30,
    "factura": 60, "orden_compra": 60,
}

# Variantes de estado que se aceptan y a que valor oficial corresponden.
SINONIMOS_ESTADO = {
    "PENDIENTE": "PENDIENTE", "POR INICIAR": "PENDIENTE", "NUEVO": "PENDIENTE",
    "EN PROCESO": "EN PROCESO", "PROCESO": "EN PROCESO", "EN TRAMITE": "EN PROCESO",
    "EN CURSO": "EN PROCESO", "TRAMITE": "EN PROCESO", "EN EJECUCION": "EN PROCESO",
    "FINALIZADO": "FINALIZADO", "FINALIZADA": "FINALIZADO", "TERMINADO": "FINALIZADO",
    "COMPLETADO": "FINALIZADO", "CERRADO": "FINALIZADO", "ENTREGADO": "FINALIZADO",
    "ANULADO": "ANULADO", "ANULADA": "ANULADO", "CANCELADO": "ANULADO",
    "CANCELADA": "ANULADO", "DESISTIDO": "ANULADO",
}

FORMATOS_FECHA = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
    "%d.%m.%Y", "%Y.%m.%d",
]


# --- Utilidades -------------------------------------------------------------


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizar_encabezado(texto) -> str:
    """Deja el encabezado comparable: sin tildes, en mayusculas y sin signos."""
    if texto is None:
        return ""
    limpio = sin_tildes(str(texto)).upper()
    limpio = "".join(c if c.isalnum() else " " for c in limpio)
    return " ".join(limpio.split())


# Encabezado normalizado -> nombre interno.
MAPA = {}
for interno, variantes in ALIAS.items():
    for variante in variantes:
        MAPA[normalizar_encabezado(variante)] = interno


def a_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        # Excel entrega los numeros como float: 12345.0 debe quedar "12345".
        return str(int(valor))
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return str(valor).strip()


def a_fecha(valor):
    """Convierte a date. Devuelve (fecha, error)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, None
    if isinstance(valor, datetime):
        return valor.date(), None
    if isinstance(valor, date):
        return valor, None
    if isinstance(valor, (int, float)):
        # Numero de serie de Excel (1 = 1900-01-01, con el bug historico del 29/02/1900).
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(valor))).date(), None
        except (ValueError, OverflowError):
            return None, "fecha numerica invalida (%s)" % valor

    texto = str(valor).strip()
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date(), None
        except ValueError:
            continue
    return None, "no se reconoce la fecha '%s' (use dd/mm/aaaa o aaaa-mm-dd)" % texto


def a_estado(valor):
    """Normaliza el estado. Devuelve (estado, error)."""
    texto = normalizar_encabezado(a_texto(valor))
    if not texto:
        return "PENDIENTE", None
    if texto in SINONIMOS_ESTADO:
        return SINONIMOS_ESTADO[texto], None
    return None, "estado '%s' no reconocido (validos: %s)" % (
        a_texto(valor), ", ".join(ESTADOS))


# --- Lectura del archivo ----------------------------------------------------


def leer_excel(ruta, hoja=None):
    from openpyxl import load_workbook

    libro = load_workbook(ruta, data_only=True, read_only=True)
    if hoja:
        if hoja not in libro.sheetnames:
            raise SystemExit("La hoja '%s' no existe. Hojas disponibles: %s"
                             % (hoja, ", ".join(libro.sheetnames)))
        pagina = libro[hoja]
    else:
        pagina = libro[libro.sheetnames[0]]

    filas = list(pagina.iter_rows(values_only=True))
    libro.close()
    if not filas:
        raise SystemExit("El archivo no tiene contenido.")
    return filas[0], filas[1:], pagina.title


def leer_csv(ruta):
    contenido = None
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(ruta, "r", encoding=codificacion, newline="") as archivo:
                contenido = archivo.read()
            break
        except UnicodeDecodeError:
            continue
    if contenido is None:
        raise SystemExit("No se pudo leer el archivo: codificacion desconocida.")

    muestra = contenido[:8000]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t|")
        separador = dialecto.delimiter
    except csv.Error:
        # Si no se puede detectar, se elige el separador mas frecuente.
        separador = max(";,\t|", key=lambda s: muestra.count(s))

    filas = list(csv.reader(contenido.splitlines(), delimiter=separador))
    if not filas:
        raise SystemExit("El archivo no tiene contenido.")
    return filas[0], filas[1:], "CSV (separador '%s')" % separador


def mapear_columnas(encabezados):
    """Devuelve {nombre_interno: indice} y la lista de encabezados ignorados."""
    columnas, ignorados = {}, []
    for indice, bruto in enumerate(encabezados):
        clave = normalizar_encabezado(bruto)
        if not clave:
            continue
        interno = MAPA.get(clave)
        if interno and interno not in columnas:
            columnas[interno] = indice
        elif not interno:
            ignorados.append(a_texto(bruto))
    return columnas, ignorados


# --- Validacion de una fila -------------------------------------------------


def preparar_fila(fila, columnas):
    """Valida y convierte una fila. Devuelve (datos, errores)."""

    def bruto(campo):
        indice = columnas.get(campo)
        if indice is None or indice >= len(fila):
            return None
        return fila[indice]

    datos, errores = {}, []

    for campo in ("cliente", "subcliente", "tipo_proceso", "ciudad", "cedula",
                  "nombre", "cargo", "factura", "orden_compra"):
        valor = a_texto(bruto(campo))
        largo = LARGOS.get(campo)
        if largo and len(valor) > largo:
            errores.append("%s excede %d caracteres (tiene %d)"
                           % (TITULO[campo], largo, len(valor)))
        datos[campo] = valor or None

    ilegibles = set()
    for campo in ("fecha_inicio", "fecha_finalizacion"):
        valor, error = a_fecha(bruto(campo))
        if error:
            errores.append("%s: %s" % (TITULO[campo], error))
            ilegibles.add(campo)
        datos[campo] = valor

    estado, error = a_estado(bruto("estado"))
    if error:
        errores.append(error)
    datos["estado"] = estado

    for campo in OBLIGATORIAS:
        # Si la fecha ya se reporto como ilegible, no se repite como "faltante".
        if not datos.get(campo) and campo not in ilegibles:
            errores.append("falta %s (obligatorio)" % TITULO[campo])

    if (datos.get("fecha_inicio") and datos.get("fecha_finalizacion")
            and datos["fecha_finalizacion"] < datos["fecha_inicio"]):
        errores.append("FECHA FINALIZACION es anterior a FECHA INICIO")

    identificador = a_texto(bruto("id"))
    datos["_id"] = int(float(identificador)) if identificador.replace(".", "").isdigit() else None

    return datos, errores


def clave_duplicado(datos):
    """Identidad natural de un registro, para detectar repeticiones."""
    return (
        (datos.get("cedula") or "").upper(),
        (datos.get("cliente") or "").upper(),
        datos.get("fecha_inicio"),
        (datos.get("tipo_proceso") or "").upper(),
    )


# --- Programa principal -----------------------------------------------------


def main():
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
    args = parser.parse_args()

    if not os.path.exists(args.archivo):
        raise SystemExit("No se encontro el archivo: " + args.archivo)

    extension = os.path.splitext(args.archivo)[1].lower()
    if extension in (".xlsx", ".xlsm"):
        encabezados, filas, origen = leer_excel(args.archivo, args.hoja)
    elif extension in (".csv", ".txt"):
        encabezados, filas, origen = leer_csv(args.archivo)
    else:
        raise SystemExit("Formato no soportado: %s (use .xlsx, .xlsm o .csv)" % extension)

    columnas, ignorados = mapear_columnas(encabezados)

    print("Archivo   : %s" % args.archivo)
    print("Origen    : %s" % origen)
    print("Columnas  : %s" % ", ".join(sorted(columnas)))
    if ignorados:
        print("Ignoradas : %s" % ", ".join(ignorados))

    faltantes = [c for c in OBLIGATORIAS if c not in columnas]
    if faltantes:
        print("")
        print("ERROR: el archivo no tiene estas columnas obligatorias: %s"
              % ", ".join(c.upper() for c in faltantes))
        print("Encabezados encontrados: %s"
              % ", ".join(a_texto(e) for e in encabezados if a_texto(e)))
        return 1

    if args.limite:
        filas = filas[:args.limite]

    app = create_app()
    with app.app_context():
        motor = app.config["SQLALCHEMY_DATABASE_URI"].split("://")[0]
        print("Destino   : %s" % motor)
        print("Modo      : %s" % ("APLICAR (escribe en la base)" if args.aplicar
                                  else "SIMULACION (no escribe nada)"))
        print("")

        # Claves ya presentes en la base, para no duplicar en cargas repetidas.
        existentes = set()
        if not args.permitir_duplicados:
            for p in db.session.scalars(select(Proceso)):
                existentes.add(clave_duplicado({
                    "cedula": p.cedula, "cliente": p.cliente,
                    "fecha_inicio": p.fecha_inicio, "tipo_proceso": p.tipo_proceso}))

        validos, rechazados, duplicados = [], [], []
        vistos_en_archivo = set()

        for numero, fila in enumerate(filas, start=2):  # fila 1 = encabezados
            if not any(a_texto(v) for v in fila):
                continue  # fila completamente vacia

            datos, errores = preparar_fila(fila, columnas)
            if errores:
                rechazados.append((numero, datos, errores))
                continue

            clave = clave_duplicado(datos)
            if not args.permitir_duplicados and (clave in existentes or clave in vistos_en_archivo):
                donde = "ya esta en la base" if clave in existentes else "repetida en el archivo"
                duplicados.append((numero, datos, donde))
                continue

            vistos_en_archivo.add(clave)
            validos.append((numero, datos))

        print("Filas leidas       : %d" % len([f for f in filas if any(a_texto(v) for v in f)]))
        print("Listas para cargar : %d" % len(validos))
        print("Duplicadas         : %d" % len(duplicados))
        print("Con errores        : %d" % len(rechazados))

        if duplicados:
            print("")
            print("--- DUPLICADAS (no se cargan) ---")
            for numero, datos, donde in duplicados[:15]:
                print("  Fila %-5d %s / %s / %s  (%s)"
                      % (numero, datos.get("cedula"), datos.get("cliente"),
                         datos.get("fecha_inicio"), donde))
            if len(duplicados) > 15:
                print("  ... y %d mas" % (len(duplicados) - 15))

        if rechazados:
            print("")
            print("--- CON ERRORES (no se cargan) ---")
            for numero, datos, errores in rechazados[:20]:
                print("  Fila %-5d %s" % (numero, "; ".join(errores)))
            if len(rechazados) > 20:
                print("  ... y %d mas" % (len(rechazados) - 20))

            informe = os.path.splitext(args.archivo)[0] + "_rechazadas.csv"
            with open(informe, "w", encoding="utf-8-sig", newline="") as salida:
                escritor = csv.writer(salida, delimiter=";")
                escritor.writerow(["FILA", "MOTIVO"] + [c.upper() for c in ALIAS if c != "id"])
                for numero, datos, errores in rechazados:
                    escritor.writerow([numero, "; ".join(errores)]
                                      + [a_texto(datos.get(c)) for c in ALIAS if c != "id"])
            print("")
            print("Detalle completo de los rechazos: %s" % informe)

        if not args.aplicar:
            print("")
            print("Esto fue una SIMULACION: no se escribio nada en la base.")
            print("Si el informe se ve bien, repita el comando agregando --aplicar")
            return 0

        if not validos:
            print("")
            print("No hay filas validas para cargar.")
            return 1

        # --- Carga real ---
        for _, datos in validos:
            proceso = Proceso(
                fecha_inicio=datos["fecha_inicio"],
                cliente=datos["cliente"],
                subcliente=datos["subcliente"],
                tipo_proceso=datos["tipo_proceso"],
                ciudad=datos["ciudad"],
                cedula=datos["cedula"],
                nombre=datos["nombre"],
                cargo=datos["cargo"],
                fecha_finalizacion=datos["fecha_finalizacion"],
                estado=datos["estado"],
                factura=datos["factura"],
                orden_compra=datos["orden_compra"],
            )
            if args.conservar_id and datos["_id"]:
                proceso.id = datos["_id"]
            db.session.add(proceso)

        registrar("CREAR", "PROCESO", None,
                  descripcion="Importacion masiva de %d registros desde %s"
                              % (len(validos), os.path.basename(args.archivo)))
        db.session.commit()

        # En PostgreSQL, si se conservaron los ID hay que adelantar la secuencia,
        # o el proximo registro creado desde la aplicacion chocaria con uno existente.
        if args.conservar_id and motor.startswith("postgresql"):
            db.session.execute(text(
                "SELECT setval(pg_get_serial_sequence('procesos','id'),"
                " COALESCE((SELECT MAX(id) FROM procesos), 1))"))
            db.session.commit()
            print("Secuencia de ID de PostgreSQL sincronizada.")

        total = db.session.scalar(select(db.func.count()).select_from(Proceso))
        print("")
        print("IMPORTACION COMPLETADA: %d registros cargados." % len(validos))
        print("La tabla procesos tiene ahora %d registros." % total)

    return 0


if __name__ == "__main__":
    sys.exit(main())
