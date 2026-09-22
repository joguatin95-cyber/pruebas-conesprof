"""Puertos: las abstracciones de las que dependen los casos de uso.

Inversion de dependencias (la D de SOLID): el caso de uso declara aqui QUE
necesita, y la capa de infraestructura decide COMO se hace. Asi el caso de uso se
puede probar con dobles en memoria, sin Excel ni base de datos, y cambiar de
formato de archivo o de motor de base no lo obliga a cambiar.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.dominio.procesos import FilaProceso


@dataclass(frozen=True)
class TablaLeida:
    """Contenido tabular crudo, independiente del formato de origen."""

    encabezados: list
    filas: list
    descripcion: str  # p. ej. "Hoja: Datos" o "CSV (separador ';')"


class ErrorDeLectura(Exception):
    """El archivo no se pudo interpretar. Lleva un mensaje para el usuario."""


class LectorTabular(ABC):
    """Puerto de entrada de datos tabulares (Excel, CSV, o lo que venga)."""

    @abstractmethod
    def leer(self, contenido: bytes, hoja: str | None = None) -> TablaLeida:
        ...


class RepositorioProcesos(ABC):
    """Puerto de persistencia de procesos."""

    @abstractmethod
    def claves_naturales_existentes(self) -> set[tuple]:
        """Claves de negocio ya guardadas, para detectar duplicados."""

    @abstractmethod
    def ids_existentes(self) -> set[int]:
        """Identificadores ya ocupados, para no chocar al conservar los del archivo."""

    @abstractmethod
    def agregar_muchos(self, filas: list[FilaProceso], conservar_id: bool) -> int:
        """Guarda las filas y devuelve cuantas quedaron."""

    @abstractmethod
    def sincronizar_secuencia_id(self) -> None:
        """Ajusta el contador de IDs tras insertar IDs explicitos."""

    @abstractmethod
    def confirmar(self) -> None:
        """Consolida los cambios (commit)."""

    @abstractmethod
    def descartar(self) -> None:
        """Deshace los cambios pendientes (rollback)."""


class RegistroDeAuditoria(ABC):
    """Puerto para dejar constancia de lo que ocurrio."""

    @abstractmethod
    def registrar_importacion(self, cantidad: int, origen: str) -> None:
        ...
