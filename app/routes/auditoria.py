from datetime import datetime

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.models import Auditoria
from app.security import solo_administrador

bp = Blueprint("auditoria", __name__, url_prefix="/auditoria")

ACCIONES = ("CREAR", "EDITAR", "ELIMINAR")
ENTIDADES = ("PROCESO", "USUARIO")


@bp.route("/")
@login_required
@solo_administrador
def listar():
    consulta = select(Auditoria)

    buscar = (request.args.get("q") or "").strip()
    if buscar:
        patron = f"%{buscar}%"
        consulta = consulta.where(
            or_(
                Auditoria.usuario_username.ilike(patron),
                Auditoria.descripcion.ilike(patron),
                Auditoria.detalle.ilike(patron),
            )
        )

    accion = (request.args.get("accion") or "").strip()
    if accion:
        consulta = consulta.where(Auditoria.accion == accion)

    entidad = (request.args.get("entidad") or "").strip()
    if entidad:
        consulta = consulta.where(Auditoria.entidad == entidad)

    registro = request.args.get("registro", type=int)
    if registro:
        consulta = consulta.where(Auditoria.entidad_id == registro)

    desde = _fecha(request.args.get("desde"))
    if desde:
        consulta = consulta.where(Auditoria.fecha >= datetime.combine(desde, datetime.min.time()))

    hasta = _fecha(request.args.get("hasta"))
    if hasta:
        consulta = consulta.where(Auditoria.fecha <= datetime.combine(hasta, datetime.max.time()))

    paginacion = db.paginate(
        consulta.order_by(Auditoria.fecha.desc(), Auditoria.id.desc()),
        page=request.args.get("pagina", 1, type=int),
        per_page=current_app.config["ITEMS_POR_PAGINA"],
        error_out=False,
    )
    filtros = {k: v for k, v in request.args.items() if k != "pagina" and v}
    return render_template(
        "auditoria/listar.html", paginacion=paginacion, acciones=ACCIONES,
        entidades=ENTIDADES, filtros=filtros,
    )


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None
