import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

# Roles disponibles en la plataforma.
ROL_ADMINISTRADOR = "ADMINISTRADOR"
ROL_CONTADOR = "CONTADOR"
ROL_CLIENTE = "CLIENTE"
ROLES = (ROL_ADMINISTRADOR, ROL_CONTADOR, ROL_CLIENTE)

# Estados posibles de un proceso.
ESTADOS = (
    "PENDIENTE",
    "EN PROCESO",
    "FINALIZADO",
    "ANULADO",
)


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default=ROL_CLIENTE)
    # Solo aplica al rol CLIENTE: limita los registros visibles a ese cliente.
    cliente_asignado = db.Column(db.String(120), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # La foto se guarda en la base y no en disco: el almacenamiento de Render es
    # efimero y se borraria en cada despliegue.
    foto = db.Column(db.LargeBinary, nullable=True)
    foto_mime = db.Column(db.String(30), nullable=True)
    foto_actualizada_en = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def es_administrador(self) -> bool:
        return self.rol == ROL_ADMINISTRADOR

    @property
    def tiene_foto(self) -> bool:
        return bool(self.foto)

    @property
    def iniciales(self) -> str:
        """Iniciales para mostrar cuando el usuario no tiene foto."""
        partes = [p for p in (self.nombre or self.username).split() if p]
        if not partes:
            return "?"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[1][0]).upper()

    @property
    def limitado_por_cliente(self) -> bool:
        """El rol CLIENTE solo ve los registros del cliente que tenga asignado."""
        return self.rol == ROL_CLIENTE

    @property
    def sin_cliente_asignado(self) -> bool:
        return self.limitado_por_cliente and not (self.cliente_asignado or "").strip()

    # Flask-Login bloquea el acceso de las cuentas desactivadas.
    @property
    def is_active(self) -> bool:
        return self.activo

    def __repr__(self) -> str:
        return f"<Usuario {self.username} ({self.rol})>"


class Proceso(db.Model):
    __tablename__ = "procesos"

    id = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    cliente = db.Column(db.String(120), nullable=False, index=True)
    subcliente = db.Column(db.String(120), nullable=True)
    tipo_proceso = db.Column(db.String(120), nullable=False)
    ciudad = db.Column(db.String(80), nullable=True)
    cedula = db.Column(db.String(30), nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False, index=True)
    cargo = db.Column(db.String(120), nullable=True)
    fecha_finalizacion = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(30), nullable=False, default="PENDIENTE", index=True)
    factura = db.Column(db.String(60), nullable=True)
    orden_compra = db.Column(db.String(60), nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    creado_por = db.relationship("Usuario", lazy="joined")

    def __repr__(self) -> str:
        return f"<Proceso {self.id} {self.nombre}>"


class Auditoria(db.Model):
    """Historico de cambios. Cada creacion, edicion o eliminacion deja un registro."""

    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Se guarda el id y el nombre de usuario: el historico sobrevive si la cuenta se elimina.
    usuario_id = db.Column(db.Integer, nullable=True)
    usuario_username = db.Column(db.String(50), nullable=False, default="sistema")

    accion = db.Column(db.String(20), nullable=False, index=True)   # CREAR / EDITAR / ELIMINAR
    entidad = db.Column(db.String(20), nullable=False, index=True)  # PROCESO / USUARIO
    entidad_id = db.Column(db.Integer, nullable=True, index=True)
    descripcion = db.Column(db.String(255), nullable=False, default="")
    detalle = db.Column(db.Text, nullable=True)  # JSON: {campo: [antes, despues]}

    @property
    def cambios(self):
        """Devuelve el detalle como lista de (campo, antes, despues)."""
        if not self.detalle:
            return []
        try:
            datos = json.loads(self.detalle)
        except ValueError:
            return []
        return [(campo, valores[0], valores[1]) for campo, valores in datos.items()]

    def __repr__(self) -> str:
        return f"<Auditoria {self.accion} {self.entidad}#{self.entidad_id}>"
