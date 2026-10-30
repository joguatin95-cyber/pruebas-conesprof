import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.dominio.procesos import ESTADOS as _ESTADOS
from app.extensions import db

# Roles disponibles en la plataforma.
ROL_ADMINISTRADOR = "ADMINISTRADOR"
ROL_CONTADOR = "CONTADOR"
ROL_CLIENTE = "CLIENTE"
ROL_PROVEEDOR = "PROVEEDOR"
ROLES = (ROL_ADMINISTRADOR, ROL_CONTADOR, ROL_CLIENTE, ROL_PROVEEDOR)

# Roles de solo lectura que ven una porcion de los procesos. Para cada uno:
#   campo    -> columna de usuarios donde se guarda a quien representa
#   columna  -> columna de procesos contra la que se compara
#   ocultas  -> columnas del tablero que ese rol no debe ver
# CLIENTE y PROVEEDOR son dimensiones independientes: un proceso pertenece a un
# cliente y puede haberlo ejecutado un proveedor distinto, sin relacion entre si.
#
# Al CLIENTE se le ocultan las dos columnas: la suya porque ya sabe que todo lo
# que ve es suyo, y la del proveedor porque no le corresponde saber quien ejecuta
# cada proceso. Al PROVEEDOR solo se le oculta la suya: necesita ver de que
# cliente es cada registro para poder trabajarlo.
#
# Este diccionario es el unico lugar donde se decide el alcance. El formulario de
# usuarios, la consulta de procesos y las columnas visibles del tablero lo
# consultan en vez de comparar contra un rol concreto.
ALCANCES = {
    ROL_CLIENTE: {
        "campo": "cliente_asignado",
        "columna": "cliente",
        "ocultas": ("cliente", "proveedor"),
    },
    ROL_PROVEEDOR: {
        "campo": "proveedor_asignado",
        "columna": "proveedor",
        "ocultas": ("proveedor",),
    },
}

# Campos de asignacion, para limpiar los que no corresponden al rol elegido.
CAMPOS_DE_ASIGNACION = tuple(a["campo"] for a in ALCANCES.values())

# Los estados los define el dominio; aqui solo se reexportan para no romper
# los import existentes (from app.models import ESTADOS).
ESTADOS = _ESTADOS


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
    # Solo aplica al rol PROVEEDOR: limita los registros visibles a ese proveedor.
    proveedor_asignado = db.Column(db.String(120), nullable=True)
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
    def alcance(self):
        """Definicion del alcance del rol, o None si el usuario ve todos los registros."""
        return ALCANCES.get(self.rol)

    @property
    def limitado_por_alcance(self) -> bool:
        """El usuario solo ve una porcion de los procesos."""
        return self.rol in ALCANCES

    @property
    def valor_asignado(self) -> str:
        """A quien representa el usuario: su cliente o su proveedor, segun el rol."""
        alcance = self.alcance
        if not alcance:
            return ""
        return (getattr(self, alcance["campo"]) or "").strip()

    @property
    def columna_de_alcance(self):
        """Columna de procesos contra la que se filtra, o None si no hay limite."""
        alcance = self.alcance
        return alcance["columna"] if alcance else None

    @property
    def columnas_ocultas(self) -> tuple:
        """Columnas del tablero que este rol no debe ver.

        No es solo cosmetico: lo que no se muestra tampoco se puede buscar, para
        que no se deduzca por el buscador lo que la columna no revela.
        """
        alcance = self.alcance
        return alcance["ocultas"] if alcance else ()

    @property
    def sin_asignacion(self) -> bool:
        """Rol con alcance pero sin valor asignado: no debe ver ningun registro."""
        return self.limitado_por_alcance and not self.valor_asignado

    @property
    def etiqueta_de_asignacion(self) -> str:
        """Como se llama lo que el usuario tiene asignado, para los mensajes."""
        alcance = self.alcance
        return alcance["columna"] if alcance else ""

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
    # Quien ejecuta el proceso. Es independiente del cliente que lo encarga.
    proveedor = db.Column(db.String(120), nullable=True, index=True)
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


class ImportacionPendiente(db.Model):
    """Archivo subido que espera confirmacion del administrador.

    Se guarda en la base y no en disco por dos razones: el almacenamiento de
    Render es efimero, y con varios procesos de gunicorn atendiendo peticiones no
    hay garantia de que la confirmacion caiga en el mismo proceso que recibio la
    subida.
    """

    __tablename__ = "importaciones_pendientes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=False, index=True)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    hoja = db.Column(db.String(120), nullable=True)
    contenido = db.Column(db.LargeBinary, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                          index=True)

    def __repr__(self) -> str:
        return f"<ImportacionPendiente {self.id} {self.nombre_archivo}>"
