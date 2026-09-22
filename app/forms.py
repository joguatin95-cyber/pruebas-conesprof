from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

from app.models import ESTADOS, ROLES


class LoginForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired(), Length(max=50)])
    password = PasswordField("Contrasena", validators=[DataRequired()])
    recordarme = BooleanField("Recordarme")
    submit = SubmitField("Ingresar")


class ProcesoForm(FlaskForm):
    fecha_inicio = DateField("Fecha inicio", validators=[DataRequired()])
    cliente = StringField("Cliente", validators=[DataRequired(), Length(max=120)])
    subcliente = StringField("Subcliente", validators=[Optional(), Length(max=120)])
    tipo_proceso = StringField("Tipo de proceso", validators=[DataRequired(), Length(max=120)])
    ciudad = StringField("Ciudad", validators=[Optional(), Length(max=80)])
    cedula = StringField("Cedula", validators=[DataRequired(), Length(max=30)])
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=150)])
    cargo = StringField("Cargo", validators=[Optional(), Length(max=120)])
    fecha_finalizacion = DateField("Fecha finalizacion", validators=[Optional()])
    estado = SelectField("Estado", choices=[(e, e) for e in ESTADOS], validators=[DataRequired()])
    factura = StringField("Factura", validators=[Optional(), Length(max=60)])
    orden_compra = StringField("Orden de compra", validators=[Optional(), Length(max=60)])
    submit = SubmitField("Guardar")


class UsuarioForm(FlaskForm):
    """Alta de usuario: la contrasena es obligatoria."""

    username = StringField("Usuario", validators=[DataRequired(), Length(max=50)])
    nombre = StringField("Nombre completo", validators=[DataRequired(), Length(max=120)])
    email = StringField("Correo", validators=[Optional(), Email(), Length(max=120)])
    rol = SelectField("Rol", choices=[(r, r) for r in ROLES], validators=[DataRequired()])
    cliente_asignado = StringField(
        "Cliente asignado (solo rol CLIENTE)", validators=[Optional(), Length(max=120)]
    )
    activo = BooleanField("Activo", default=True)
    password = PasswordField("Contrasena", validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField(
        "Confirmar contrasena",
        validators=[DataRequired(), EqualTo("password", message="Las contrasenas no coinciden.")],
    )
    submit = SubmitField("Guardar")


class UsuarioEditarForm(FlaskForm):
    """Edicion de usuario: la contrasena solo cambia si se diligencia."""

    username = StringField("Usuario", validators=[DataRequired(), Length(max=50)])
    nombre = StringField("Nombre completo", validators=[DataRequired(), Length(max=120)])
    email = StringField("Correo", validators=[Optional(), Email(), Length(max=120)])
    rol = SelectField("Rol", choices=[(r, r) for r in ROLES], validators=[DataRequired()])
    cliente_asignado = StringField(
        "Cliente asignado (solo rol CLIENTE)", validators=[Optional(), Length(max=120)]
    )
    activo = BooleanField("Activo")
    password = PasswordField(
        "Nueva contrasena (opcional)", validators=[Optional(), Length(min=8)]
    )
    password2 = PasswordField(
        "Confirmar contrasena",
        validators=[EqualTo("password", message="Las contrasenas no coinciden.")],
    )
    submit = SubmitField("Guardar cambios")


class CambiarPasswordForm(FlaskForm):
    """Cambio de la propia contrasena. Exige la actual para evitar que alguien
    con la sesion abierta ajena se apodere de la cuenta."""

    password_actual = PasswordField("Contrasena actual", validators=[DataRequired()])
    password = PasswordField(
        "Nueva contrasena",
        validators=[DataRequired(), Length(min=8, message="Minimo 8 caracteres.")],
    )
    password2 = PasswordField(
        "Confirmar nueva contrasena",
        validators=[DataRequired(), EqualTo("password", message="Las contrasenas no coinciden.")],
    )
    submit = SubmitField("Cambiar contrasena")


class FotoForm(FlaskForm):
    foto = FileField(
        "Imagen",
        validators=[
            FileAllowed(["jpg", "jpeg", "png", "webp", "gif", "bmp"],
                        "Solo se admiten imagenes JPG, PNG, WEBP, GIF o BMP.")
        ],
    )
    submit = SubmitField("Guardar foto")


class SubirArchivoForm(FlaskForm):
    """Paso 1 de la importacion: elegir el archivo y las opciones."""

    archivo = FileField(
        "Archivo de Excel o CSV",
        validators=[
            DataRequired(message="Seleccione un archivo."),
            FileAllowed(["xlsx", "xlsm", "csv", "txt"],
                        "Solo se admiten archivos .xlsx, .xlsm o .csv."),
        ],
    )
    hoja = StringField("Hoja del Excel (opcional)", validators=[Optional(), Length(max=120)])
    conservar_id = BooleanField("Respetar la columna ID del archivo")
    permitir_duplicados = BooleanField("Cargar tambien los registros repetidos")
    submit = SubmitField("Revisar archivo")


class ConfirmarImportacionForm(FlaskForm):
    """Paso 2: confirmar que se escriba en la base."""

    conservar_id = BooleanField("Respetar la columna ID del archivo")
    permitir_duplicados = BooleanField("Cargar tambien los registros repetidos")
    submit = SubmitField("Confirmar e importar")
