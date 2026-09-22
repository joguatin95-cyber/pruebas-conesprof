"""Reglas de interpretacion de los datos que llegan de un archivo.

Un Excel real trae fechas en cinco formatos, encabezados con tildes, estados
escritos a mano y numeros que Excel entrega como decimales. Traducir todo eso al
vocabulario del dominio es una regla de negocio, no un detalle tecnico: por eso
vive aqui y no en el lector de Excel ni en la ruta web.

Patron aplicado: Especificacion/Validador. Cada funcion devuelve
(valor_normalizado, error) en lugar de lanzar excepciones, porque una importacion
debe poder informar TODOS los problemas de una fila, no detenerse en el primero.
"""

import unicodedata
from datetime import date, datetime, timedelta

from app.dominio.procesos import (
    CAMPOS,
    ESTADO_POR_DEFECTO,
    ESTADOS,
    LARGOS,
    OBLIGATORIOS,
    TITULOS,
    FilaProceso,
)

# Encabezados que se aceptan para cada campo. El primero es el canonico.
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

# Como se escribe en la practica cada estado y a que valor oficial corresponde.
SINONIMOS_ESTADO = {
    "PENDIENTE": "PENDIENTE", "POR INICIAR": "PENDIENTE", "NUEVO": "PENDIENTE",
    "EN PROCESO": "EN PROCESO", "PROCESO": "EN PROCESO", "EN TRAMITE": "EN PROCESO",
    "EN CURSO": "EN PROCESO", "TRAMITE": "EN PROCESO", "EN EJECUCION": "EN PROCESO",
    "FINALIZADO": "FINALIZADO", "FINALIZADA": "FINALIZADO", "TERMINADO": "FINALIZADO",
    "COMPLETADO": "FINALIZADO", "CERRADO": "FINALIZADO", "ENTREGADO": "FINALIZADO",
    "ANULADO": "ANULADO", "ANULADA": "ANULADO", "CANCELADO": "ANULADO",
    "CANCELADA": "ANULADO", "DESISTIDO": "ANULADO",
}

FORMATOS_FECHA = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
    "%d.%m.%Y", "%Y.%m.%d",
)

CAMPOS_TEXTO = tuple(c for c in CAMPOS if c in LARGOS and c != "estado")


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def clave_encabezado(texto) -> str:
    """Deja un encabezado comparable: sin tildes, en mayusculas y sin signos."""
    if texto is None:
        return ""
    limpio = sin_tildes(str(texto)).upper()
    limpio = "".join(c if c.isalnum() else " " for c in limpio)
    return " ".join(limpio.split())


# Encabezado normalizado -> campo del dominio.
_MAPA_ENCABEZADOS = {
    clave_encabezado(variante): campo
    for campo, variantes in ALIAS.items()
    for variante in variantes
}


def mapear_columnas(encabezados) -> tuple[dict[str, int], tuple[str, ...]]:
    """Relaciona las columnas del archivo con los campos del dominio.

    Devuelve ({campo: indice}, encabezados_que_no_se_reconocieron).
    """
    columnas: dict[str, int] = {}
    ignorados: list[str] = []
    for indice, bruto in enumerate(encabezados):
        clave = clave_encabezado(bruto)
        if not clave:
            continue
        campo = _MAPA_ENCABEZADOS.get(clave)
        if campo and campo not in columnas:
            columnas[campo] = indice
        elif not campo:
            ignorados.append(a_texto(bruto))
    return columnas, tuple(ignorados)


def campos_obligatorios_ausentes(columnas) -> tuple[str, ...]:
    return tuple(TITULOS[c] for c in OBLIGATORIOS if c not in columnas)


def a_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Si" if valor else "No"
    if isinstance(valor, float) and valor.is_integer():
        # Excel entrega los numeros como decimales: 12345.0 debe quedar "12345".
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
        # Numero de serie de Excel, con el desfase historico del 29/02/1900.
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
    clave = clave_encabezado(a_texto(valor))
    if not clave:
        return ESTADO_POR_DEFECTO, None
    if clave in SINONIMOS_ESTADO:
        return SINONIMOS_ESTADO[clave], None
    return None, "estado '%s' no reconocido (validos: %s)" % (
        a_texto(valor), ", ".join(ESTADOS))


def a_entero(valor):
    texto = a_texto(valor)
    try:
        return int(float(texto)) if texto else None
    except ValueError:
        return None


def normalizar_fila(fila, columnas) -> tuple[FilaProceso | None, tuple[str, ...], dict]:
    """Valida y convierte una fila cruda.

    Devuelve (FilaProceso o None, motivos_de_rechazo, valores_en_texto).
    Los valores en texto se devuelven siempre, para poder mostrarle al usuario la
    fila tal como venia aunque no se haya podido cargar.
    """

    def bruto(campo):
        indice = columnas.get(campo)
        if indice is None or indice >= len(fila):
            return None
        return fila[indice]

    motivos: list[str] = []
    datos: dict = {}
    texto_original = {campo: a_texto(bruto(campo)) for campo in CAMPOS}

    for campo in CAMPOS_TEXTO:
        valor = a_texto(bruto(campo))
        limite = LARGOS[campo]
        if len(valor) > limite:
            motivos.append("%s excede %d caracteres (tiene %d)"
                           % (TITULOS[campo], limite, len(valor)))
        datos[campo] = valor or None

    fechas_ilegibles = set()
    for campo in ("fecha_inicio", "fecha_finalizacion"):
        valor, error = a_fecha(bruto(campo))
        if error:
            motivos.append("%s: %s" % (TITULOS[campo], error))
            fechas_ilegibles.add(campo)
        datos[campo] = valor

    estado, error = a_estado(bruto("estado"))
    if error:
        motivos.append(error)
    datos["estado"] = estado or ESTADO_POR_DEFECTO

    for campo in OBLIGATORIOS:
        # Si la fecha ya se reporto como ilegible, no se repite como "faltante".
        if not datos.get(campo) and campo not in fechas_ilegibles:
            motivos.append("falta %s (obligatorio)" % TITULOS[campo])

    if (datos.get("fecha_inicio") and datos.get("fecha_finalizacion")
            and datos["fecha_finalizacion"] < datos["fecha_inicio"]):
        motivos.append("%s es anterior a %s"
                       % (TITULOS["fecha_finalizacion"], TITULOS["fecha_inicio"]))

    if motivos:
        return None, tuple(motivos), texto_original

    return (
        FilaProceso(id_original=a_entero(bruto("id")), **datos),
        (),
        texto_original,
    )


def fila_vacia(fila) -> bool:
    return not any(a_texto(v) for v in fila)
