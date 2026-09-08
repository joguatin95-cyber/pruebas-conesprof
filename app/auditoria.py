"""Utilidades para alimentar el historico de cambios."""

import json

from flask_login import current_user

from app.extensions import db
from app.models import Auditoria

# Etiquetas legibles para mostrar los campos en el historico.
ETIQUETAS = {
    "fecha_inicio": "Fecha inicio",
    "cliente": "Cliente",
    "subcliente": "Subcliente",
    "tipo_proceso": "Tipo de proceso",
    "ciudad": "Ciudad",
    "cedula": "Cedula",
    "nombre": "Nombre",
    "cargo": "Cargo",
    "fecha_finalizacion": "Fecha finalizacion",
    "estado": "Estado",
    "factura": "Factura",
    "orden_compra": "Orden de compra",
    "username": "Usuario",
    "email": "Correo",
    "rol": "Rol",
    "activo": "Activo",
    "cliente_asignado": "Cliente asignado",
    "contrasena": "Contrasena",
}


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Si" if valor else "No"
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def instantanea(obj, campos):
    """Copia el estado actual de los campos indicados, ya convertido a texto."""
    return {campo: _texto(getattr(obj, campo, None)) for campo in campos}


def comparar(antes, despues):
    """Devuelve solo los campos cuyo valor cambio: {campo: [antes, despues]}."""
    return {
        campo: [antes.get(campo, ""), valor]
        for campo, valor in despues.items()
        if antes.get(campo, "") != valor
    }


def _autor():
    """Quien realiza el cambio. Fuera de una peticion web (scripts) es 'sistema'."""
    try:
        if current_user.is_authenticated:
            return current_user.id, current_user.username
    except Exception:  # noqa: BLE001 - sin contexto de peticion, p. ej. en importar.py
        pass
    return None, "sistema"


def registrar(accion, entidad, entidad_id, descripcion="", detalle=None):
    """Agrega un registro al historico. El commit lo hace quien llama."""
    usuario_id, username = _autor()
    db.session.add(
        Auditoria(
            usuario_id=usuario_id,
            usuario_username=username,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            descripcion=descripcion[:255],
            detalle=json.dumps(detalle, ensure_ascii=False) if detalle else None,
        )
    )
