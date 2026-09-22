"""Dominio de procesos: entidades, reglas y vocabulario del negocio.

Esta capa no conoce Flask, SQLAlchemy, Excel ni HTTP. Solo describe que es un
proceso, que valores admite y cuando una fila es valida. Es la capa mas interna:
todo depende de ella y ella no depende de nada.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# --- Vocabulario del negocio -----------------------------------------------

ESTADOS = ("PENDIENTE", "EN PROCESO", "FINALIZADO", "ANULADO")

ESTADO_POR_DEFECTO = "PENDIENTE"

# Campos del proceso en el orden en que se muestran y se exportan.
CAMPOS = (
    "fecha_inicio",
    "cliente",
    "subcliente",
    "tipo_proceso",
    "ciudad",
    "cedula",
    "nombre",
    "cargo",
    "fecha_finalizacion",
    "estado",
    "factura",
    "orden_compra",
)

# Sin estos datos un proceso no identifica a nadie ni se puede rastrear.
OBLIGATORIOS = ("fecha_inicio", "cliente", "tipo_proceso", "cedula", "nombre")

# Titulo legible de cada campo, usado en encabezados y mensajes de error.
TITULOS = {
    "id": "ID",
    "fecha_inicio": "FECHA INICIO",
    "cliente": "CLIENTE",
    "subcliente": "SUBCLIENTE",
    "tipo_proceso": "TIPO DE PROCESO",
    "ciudad": "CIUDAD",
    "cedula": "CEDULA",
    "nombre": "NOMBRE",
    "cargo": "CARGO",
    "fecha_finalizacion": "FECHA FINALIZACION",
    "estado": "ESTADO",
    "factura": "FACTURA",
    "orden_compra": "ORDEN DE COMPRA",
}

# Longitud maxima de cada campo de texto. Es una regla del dominio, aunque
# coincida con el ancho de la columna en la base de datos.
LARGOS = {
    "cliente": 120,
    "subcliente": 120,
    "tipo_proceso": 120,
    "ciudad": 80,
    "cedula": 30,
    "nombre": 150,
    "cargo": 120,
    "estado": 30,
    "factura": 60,
    "orden_compra": 60,
}

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def nombre_mes(numero: int) -> str:
    return MESES[numero - 1].capitalize()


# --- Entidades y objetos de valor ------------------------------------------


@dataclass(frozen=True)
class FilaProceso:
    """Un proceso ya normalizado, listo para persistirse.

    Es inmutable a proposito: una vez validada, la fila no se retoca.
    """

    fecha_inicio: date
    cliente: str
    tipo_proceso: str
    cedula: str
    nombre: str
    subcliente: str | None = None
    ciudad: str | None = None
    cargo: str | None = None
    fecha_finalizacion: date | None = None
    estado: str = ESTADO_POR_DEFECTO
    factura: str | None = None
    orden_compra: str | None = None
    id_original: int | None = None

    def clave_natural(self) -> tuple:
        """Identidad de negocio de un proceso, al margen del ID de la base.

        Dos filas con esta misma combinacion describen el mismo tramite, asi que
        sirve para detectar duplicados entre cargas repetidas.
        """
        return (
            (self.cedula or "").strip().upper(),
            (self.cliente or "").strip().upper(),
            self.fecha_inicio,
            (self.tipo_proceso or "").strip().upper(),
        )

    def como_diccionario(self) -> dict[str, Any]:
        return {campo: getattr(self, campo) for campo in CAMPOS}


@dataclass(frozen=True)
class FilaRechazada:
    """Fila que no se pudo cargar, con el motivo para que el usuario lo corrija."""

    numero: int
    motivos: tuple[str, ...]
    valores: dict[str, str] = field(default_factory=dict)

    @property
    def motivo(self) -> str:
        return "; ".join(self.motivos)


@dataclass(frozen=True)
class FilaDuplicada:
    numero: int
    fila: FilaProceso
    donde: str  # "ya esta en la base" | "repetida en el archivo"


@dataclass
class ResultadoImportacion:
    """Informe de una importacion, se haya aplicado o solo simulado."""

    validas: list[FilaProceso] = field(default_factory=list)
    duplicadas: list[FilaDuplicada] = field(default_factory=list)
    rechazadas: list[FilaRechazada] = field(default_factory=list)
    columnas_reconocidas: tuple[str, ...] = ()
    columnas_ignoradas: tuple[str, ...] = ()
    filas_leidas: int = 0
    origen: str = ""
    aplicado: bool = False

    @property
    def total_validas(self) -> int:
        return len(self.validas)

    @property
    def total_duplicadas(self) -> int:
        return len(self.duplicadas)

    @property
    def total_rechazadas(self) -> int:
        return len(self.rechazadas)

    @property
    def hay_algo_que_cargar(self) -> bool:
        return bool(self.validas)

    @property
    def limpio(self) -> bool:
        return not self.rechazadas and not self.duplicadas
