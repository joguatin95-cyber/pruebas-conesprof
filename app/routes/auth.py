from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from app.extensions import db
from app.forms import LoginForm
from app.models import Usuario

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("procesos.listar"))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = db.session.scalar(
            select(Usuario).where(Usuario.username == form.username.data.strip())
        )
        if usuario is None or not usuario.check_password(form.password.data):
            flash("Usuario o contrasena incorrectos.", "danger")
            return render_template("login.html", form=form)
        if not usuario.activo:
            flash("La cuenta se encuentra desactivada. Contacte al administrador.", "warning")
            return render_template("login.html", form=form)

        login_user(usuario, remember=form.recordarme.data)
        # Solo se aceptan destinos internos para evitar redirecciones abiertas.
        destino = request.args.get("next", "")
        if not destino.startswith("/") or destino.startswith("//"):
            destino = url_for("procesos.listar")
        return redirect(destino)

    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesion cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
