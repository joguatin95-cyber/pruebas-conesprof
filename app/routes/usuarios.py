from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import select, update

from app.auditoria import comparar, instantanea, registrar
from app.extensions import db
from app.forms import UsuarioEditarForm, UsuarioForm
from app.models import Proceso, Usuario
from app.security import solo_administrador

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

# Campos del usuario que quedan reflejados en el historico de cambios.
CAMPOS_AUDITADOS = ["username", "nombre", "email", "rol", "cliente_asignado", "activo"]


def _existe(campo, valor, excluir_id=None):
    consulta = select(Usuario).where(campo == valor)
    if excluir_id is not None:
        consulta = consulta.where(Usuario.id != excluir_id)
    return db.session.scalar(consulta) is not None


def _clientes_existentes():
    """Lista de clientes ya registrados, para sugerirlos al asignar un CLIENTE."""
    return db.session.scalars(
        select(Proceso.cliente).distinct().order_by(Proceso.cliente)
    ).all()


@bp.route("/")
@login_required
@solo_administrador
def listar():
    usuarios = db.session.scalars(select(Usuario).order_by(Usuario.id)).all()
    return render_template("usuarios/listar.html", usuarios=usuarios)


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@solo_administrador
def crear():
    form = UsuarioForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = (form.email.data or "").strip() or None
        if _existe(Usuario.username, username):
            flash("Ya existe un usuario con ese nombre de usuario.", "danger")
        elif email and _existe(Usuario.email, email):
            flash("Ya existe un usuario con ese correo.", "danger")
        else:
            usuario = Usuario(
                username=username,
                nombre=form.nombre.data.strip(),
                email=email,
                rol=form.rol.data,
                # El cliente asignado solo tiene sentido para el rol CLIENTE.
                cliente_asignado=(
                    (form.cliente_asignado.data or "").strip() or None
                    if form.rol.data == "CLIENTE"
                    else None
                ),
                activo=form.activo.data,
            )
            usuario.set_password(form.password.data)
            db.session.add(usuario)
            db.session.flush()
            registrar(
                "CREAR", "USUARIO", usuario.id, descripcion=f"{usuario.username} ({usuario.rol})",
                detalle={
                    c: ["", v] for c, v in instantanea(usuario, CAMPOS_AUDITADOS).items() if v
                },
            )
            db.session.commit()
            flash(f"Usuario '{usuario.username}' creado correctamente.", "success")
            if usuario.sin_cliente_asignado:
                flash(
                    "El usuario tiene rol CLIENTE sin cliente asignado: no vera ningun "
                    "registro hasta que le asigne uno.",
                    "warning",
                )
            return redirect(url_for("usuarios.listar"))
    return render_template(
        "usuarios/form.html", form=form, titulo="Nuevo usuario",
        clientes=_clientes_existentes(),
    )


@bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@solo_administrador
def editar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    form = UsuarioEditarForm(obj=usuario)
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = (form.email.data or "").strip() or None
        if _existe(Usuario.username, username, excluir_id=usuario.id):
            flash("Ya existe otro usuario con ese nombre de usuario.", "danger")
        elif email and _existe(Usuario.email, email, excluir_id=usuario.id):
            flash("Ya existe otro usuario con ese correo.", "danger")
        else:
            # Evita que el administrador conectado se quite a si mismo el acceso.
            if usuario.id == current_user.id and (
                form.rol.data != usuario.rol or not form.activo.data
            ):
                flash("No puede cambiar su propio rol ni desactivar su cuenta.", "warning")
                return render_template(
                    "usuarios/form.html", form=form, titulo=f"Editar usuario #{usuario.id}",
                    usuario=usuario, clientes=_clientes_existentes(),
                )

            antes = instantanea(usuario, CAMPOS_AUDITADOS)
            usuario.username = username
            usuario.nombre = form.nombre.data.strip()
            usuario.email = email
            usuario.rol = form.rol.data
            usuario.cliente_asignado = (
                (form.cliente_asignado.data or "").strip() or None
                if form.rol.data == "CLIENTE"
                else None
            )
            usuario.activo = form.activo.data

            cambios = comparar(antes, instantanea(usuario, CAMPOS_AUDITADOS))
            if form.password.data:
                usuario.set_password(form.password.data)
                # Nunca se guarda la contrasena en el historico, solo el hecho del cambio.
                cambios["contrasena"] = ["", "(actualizada)"]
            if cambios:
                registrar(
                    "EDITAR", "USUARIO", usuario.id,
                    descripcion=f"{usuario.username} ({usuario.rol})", detalle=cambios,
                )
            db.session.commit()
            flash(f"Usuario '{usuario.username}' actualizado correctamente.", "success")
            if usuario.sin_cliente_asignado:
                flash(
                    "El usuario tiene rol CLIENTE sin cliente asignado: no vera ningun "
                    "registro hasta que le asigne uno.",
                    "warning",
                )
            return redirect(url_for("usuarios.listar"))
    return render_template(
        "usuarios/form.html", form=form, titulo=f"Editar usuario #{usuario.id}",
        usuario=usuario, clientes=_clientes_existentes(),
    )


@bp.route("/<int:usuario_id>/eliminar", methods=["POST"])
@login_required
@solo_administrador
def eliminar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    if usuario.id == current_user.id:
        flash("No puede eliminar su propia cuenta.", "warning")
        return redirect(url_for("usuarios.listar"))

    if usuario.es_administrador:
        admins = db.session.scalars(
            select(Usuario).where(Usuario.rol == "ADMINISTRADOR", Usuario.activo.is_(True))
        ).all()
        if len(admins) <= 1:
            flash("Debe existir al menos un administrador activo.", "warning")
            return redirect(url_for("usuarios.listar"))

    registrar(
        "ELIMINAR", "USUARIO", usuario.id, descripcion=f"{usuario.username} ({usuario.rol})",
        detalle={c: [v, ""] for c, v in instantanea(usuario, CAMPOS_AUDITADOS).items() if v},
    )
    # Los procesos que creo se conservan; solo se suelta la referencia al autor.
    db.session.execute(
        update(Proceso).where(Proceso.creado_por_id == usuario.id).values(creado_por_id=None)
    )
    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuario '{usuario.username}' eliminado.", "info")
    return redirect(url_for("usuarios.listar"))
