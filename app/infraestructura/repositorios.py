"""Adaptadores de persistencia sobre SQLAlchemy.

Implementan los puertos que declara la capa de aplicacion. Es el unico sitio de
las funciones nuevas donde se menciona SQLAlchemy o el modelo Proceso.
"""

from sqlalchemy import func, select, text

from app.aplicacion.puertos import RegistroDeAuditoria, RepositorioProcesos
from app.auditoria import registrar
from app.dominio.procesos import FilaProceso
from app.extensions import db
from app.models import Proceso


class RepositorioProcesosSQLAlchemy(RepositorioProcesos):
    def __init__(self, sesion=None, creado_por_id: int | None = None) -> None:
        self._sesion = sesion or db.session
        self._creado_por_id = creado_por_id

    def claves_naturales_existentes(self) -> set[tuple]:
        # Solo las cuatro columnas de la clave natural: traer las filas completas
        # seria innecesario y costoso con muchos registros.
        filas = self._sesion.execute(
            select(Proceso.cedula, Proceso.cliente,
                   Proceso.fecha_inicio, Proceso.tipo_proceso)
        ).all()
        return {
            ((cedula or "").strip().upper(),
             (cliente or "").strip().upper(),
             fecha,
             (tipo or "").strip().upper())
            for cedula, cliente, fecha, tipo in filas
        }

    def agregar_muchos(self, filas: list[FilaProceso], conservar_id: bool) -> int:
        for fila in filas:
            proceso = Proceso(
                creado_por_id=self._creado_por_id, **fila.como_diccionario()
            )
            if conservar_id and fila.id_original:
                proceso.id = fila.id_original
            self._sesion.add(proceso)
        return len(filas)

    def sincronizar_secuencia_id(self) -> None:
        # Solo PostgreSQL usa secuencias; en SQLite el autoincremento se ajusta solo.
        if self._sesion.get_bind().dialect.name != "postgresql":
            return
        self._sesion.execute(text(
            "SELECT setval(pg_get_serial_sequence('procesos','id'),"
            " COALESCE((SELECT MAX(id) FROM procesos), 1))"
        ))

    def total(self) -> int:
        return self._sesion.scalar(select(func.count()).select_from(Proceso)) or 0

    def confirmar(self) -> None:
        self._sesion.commit()

    def descartar(self) -> None:
        self._sesion.rollback()


class AuditoriaSQLAlchemy(RegistroDeAuditoria):
    """Adaptador sobre el registro de auditoria que ya existia."""

    def registrar_importacion(self, cantidad: int, origen: str) -> None:
        registrar(
            "CREAR", "PROCESO", None,
            descripcion="Importacion masiva de %d registros desde %s"
                        % (cantidad, origen),
        )
