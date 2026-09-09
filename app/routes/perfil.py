"""Panel personal: cualquier usuario puede cambiar su contrasena y su foto.

Es la unica parte de la aplicacion donde CONTADOR y CLIENTE pueden escribir, y
siempre limitada a su propia cuenta: nunca reciben el id del usuario por la URL,
se toma de la sesion.
"""

from datetime import datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.auditoria import registrar
from app.extensions import db
from app.forms import CambiarPasswordForm, FotoForm
from app.imagenes import procesar
from app.models import Usuario

bp = Blueprint("perfil", __name__, url_prefix="/perfil")


@bp.route("/", methods=["GET"])
@login_required
def ver():
    return render_template(
        "perfil.html", form_password=CambiarPasswordForm(), form_foto=FotoForm()
    )


@bp.route("/password", methods=["POST"])
@login_required
def cambiar_password():
    form = CambiarPasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.password_actual.data):
            flash("La contrasena actual no es correcta.", "danger")
        elif form.password_actual.data == form.password.data:
            flash("La nueva contrasena debe ser distinta de la actual.", "warning")
        else:
            current_user.set_password(form.password.data)
            registrar(
                "EDITAR", "USUARIO", current_user.id,
                descripcion="%s (%s)" % (current_user.username, current_user.rol),
                # Nunca se guarda el valor, solo el hecho de que cambio.
                detalle={"contrasena": ["", "(cambiada por el propio usuario)"]},
            )
            db.session.commit()
            flash("Contrasena actualizada correctamente.", "success")
            return redirect(url_for("perfil.ver"))
    else:
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")

    return render_template("perfil.html", form_password=form, form_foto=FotoForm())


@bp.route("/foto", methods=["POST"])
@login_required
def cambiar_foto():
    form = FotoForm()
    if form.validate_on_submit():
        archivo = form.foto.data
        if not archivo:
            flash("Seleccione una imagen antes de guardar.", "warning")
            return redirect(url_for("perfil.ver"))

        datos, mime, error = procesar(archivo)
        if error:
            flash(error, "danger")
            return redirect(url_for("perfil.ver"))

        tenia = current_user.tiene_foto
        current_user.foto = datos
        current_user.foto_mime = mime
        current_user.foto_actualizada_en = datetime.utcnow()
        registrar(
            "EDITAR", "USUARIO", current_user.id,
            descripcion="%s (%s)" % (current_user.username, current_user.rol),
            detalle={"foto": ["(anterior)" if tenia else "", "(actualizada)"]},
        )
        db.session.commit()
        flash("Foto actualizada correctamente.", "success")
    else:
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")
    return redirect(url_for("perfil.ver"))


@bp.route("/foto/eliminar", methods=["POST"])
@login_required
def eliminar_foto():
    if current_user.tiene_foto:
        current_user.foto = None
        current_user.foto_mime = None
        current_user.foto_actualizada_en = None
        registrar(
            "EDITAR", "USUARIO", current_user.id,
            descripcion="%s (%s)" % (current_user.username, current_user.rol),
            detalle={"foto": ["(anterior)", "(eliminada)"]},
        )
        db.session.commit()
        flash("Foto eliminada.", "info")
    return redirect(url_for("perfil.ver"))


@bp.route("/foto/<int:usuario_id>")
@login_required
def foto(usuario_id):
    """Entrega la imagen. Solo para usuarios autenticados."""
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or not usuario.tiene_foto:
        abort(404)

    respuesta = Response(usuario.foto, mimetype=usuario.foto_mime or "image/jpeg")
    # nosniff evita que el navegador interprete el archivo como otra cosa.
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Content-Disposition"] = "inline"
    respuesta.headers["Cache-Control"] = "private, max-age=300"
    return respuesta
