import csv
import io
from datetime import date, datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import false, func, or_, select, text

from app.auditoria import comparar, instantanea, registrar
from app.extensions import db
from app.forms import ProcesoForm
from app.dominio.procesos import nombre_mes
from app.models import ESTADOS, Auditoria, Proceso
from app.security import solo_administrador

bp = Blueprint("procesos", __name__)

COLUMNAS = [
    ("id", "ID"),
    ("fecha_inicio", "FECHA INICIO"),
    ("cliente", "CLIENTE"),
    ("subcliente", "SUBCLIENTE"),
    ("tipo_proceso", "TIPO DE PROCESO"),
    ("ciudad", "CIUDAD"),
    ("cedula", "CEDULA"),
    ("nombre", "NOMBRE"),
    ("cargo", "CARGO"),
    ("fecha_finalizacion", "FECHA FINALIZACION"),
    ("estado", "ESTADO"),
    ("factura", "FACTURA"),
    ("orden_compra", "ORDEN DE COMPRA"),
]

CAMPOS_EDITABLES = [campo for campo, _ in COLUMNAS if campo != "id"]


def _volcar_form(form, proceso):
    """Copia solo los campos del formulario que existen en el modelo."""
    for campo in CAMPOS_EDITABLES:
        setattr(proceso, campo, getattr(form, campo).data)


def _construir_consulta(aplicar_filtros=True):
    """Arma la consulta de procesos aplicando el alcance del usuario y los filtros.

    Con aplicar_filtros=False se obtiene solo el alcance (lo que el usuario tiene
    derecho a ver), que es la base para calcular las pestanas de mes.
    """
    consulta = select(Proceso)

    # El rol CLIENTE solo puede ver los registros del cliente que tenga asignado.
    if current_user.limitado_por_cliente:
        asignado = (current_user.cliente_asignado or "").strip()
        if not asignado:
            # Sin cliente asignado no se muestra ningun registro.
            return consulta.where(false())
        consulta = consulta.where(Proceso.cliente.ilike(asignado))

    if not aplicar_filtros:
        return consulta

    buscar = (request.args.get("q") or "").strip()
    if buscar:
        patron = f"%{buscar}%"
        consulta = consulta.where(
            or_(
                Proceso.cliente.ilike(patron),
                Proceso.subcliente.ilike(patron),
                Proceso.tipo_proceso.ilike(patron),
                Proceso.ciudad.ilike(patron),
                Proceso.cedula.ilike(patron),
                Proceso.nombre.ilike(patron),
                Proceso.cargo.ilike(patron),
                Proceso.factura.ilike(patron),
                Proceso.orden_compra.ilike(patron),
            )
        )

    estado = (request.args.get("estado") or "").strip()
    if estado:
        consulta = consulta.where(Proceso.estado == estado)

    # Pestana de mes (formato aaaa-mm), al estilo de las hojas de un Excel.
    mes = (request.args.get("mes") or "").strip()
    if mes:
        anio_mes = _anio_mes(mes)
        if anio_mes:
            anio, numero = anio_mes
            inicio = date(anio, numero, 1)
            fin = date(anio + (numero == 12), (numero % 12) + 1, 1)
            consulta = consulta.where(
                Proceso.fecha_inicio >= inicio, Proceso.fecha_inicio < fin)

    desde = _fecha(request.args.get("desde"))
    if desde:
        consulta = consulta.where(Proceso.fecha_inicio >= desde)

    hasta = _fecha(request.args.get("hasta"))
    if hasta:
        consulta = consulta.where(Proceso.fecha_inicio <= hasta)

    return consulta.order_by(Proceso.id.desc())


def _anio_mes(valor):
    """Interpreta 'aaaa-mm'. Devuelve (anio, mes) o None."""
    try:
        anio, numero = valor.split("-")
        anio, numero = int(anio), int(numero)
    except (ValueError, AttributeError):
        return None
    return (anio, numero) if 1 <= numero <= 12 else None


def _meses_disponibles():
    """Meses que tienen registros dentro del alcance del usuario.

    Se calcula en la base con una consulta agregada, no trayendo los procesos a
    memoria, para que siga funcionando con muchos registros.
    """
    base = _construir_consulta(aplicar_filtros=False).subquery()
    # Cada motor tiene su propia funcion para dar formato a una fecha.
    es_postgres = db.session.get_bind().dialect.name == "postgresql"
    columna = (func.to_char(base.c.fecha_inicio, "YYYY-MM") if es_postgres
               else func.strftime("%Y-%m", base.c.fecha_inicio))

    filas = db.session.execute(
        select(columna.label("mes"), func.count().label("total"))
        .group_by("mes").order_by(text("mes DESC"))
    ).all()

    return [
        {"valor": m, "etiqueta": "%s %s" % (nombre_mes(int(m[5:7])), m[:4]), "total": t}
        for m, t in filas if m
    ]


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/")
@login_required
def listar():
    pagina = request.args.get("pagina", 1, type=int)
    paginacion = db.paginate(
        _construir_consulta(),
        page=pagina,
        per_page=current_app.config["ITEMS_POR_PAGINA"],
        error_out=False,
    )
    # Filtros activos, sin la pagina, para reusarlos en los enlaces y en la exportacion.
    filtros = {k: v for k, v in request.args.items() if k != "pagina" and v}
    return render_template(
        "procesos/listar.html",
        paginacion=paginacion,
        columnas=COLUMNAS,
        estados=ESTADOS,
        filtros=filtros,
        meses=_meses_disponibles(),
        mes_activo=(request.args.get("mes") or "").strip(),
        # Los enlaces de las pestanas conservan los demas filtros, no el mes.
        filtros_sin_mes={k: v for k, v in filtros.items() if k != "mes"},
        primer_numero=(paginacion.page - 1) * paginacion.per_page + 1,
    )


@bp.route("/procesos/exportar")
@login_required
def exportar():
    """Descarga en CSV el resultado de los filtros activos."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow([titulo for _, titulo in COLUMNAS])
    for proceso in db.session.scalars(_construir_consulta()):
        escritor.writerow([getattr(proceso, campo) or "" for campo, _ in COLUMNAS])

    nombre = f"procesos_{datetime.now():%Y%m%d_%H%M}.csv"
    return Response(
        # BOM para que Excel reconozca los acentos.
        "\ufeff" + salida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


@bp.route("/procesos/nuevo", methods=["GET", "POST"])
@login_required
@solo_administrador
def crear():
    form = ProcesoForm()
    if form.validate_on_submit():
        proceso = Proceso(creado_por_id=current_user.id)
        _volcar_form(form, proceso)
        db.session.add(proceso)
        db.session.flush()  # asigna el id antes de registrar el historico
        registrar(
            "CREAR", "PROCESO", proceso.id,
            descripcion=f"{proceso.cliente} - {proceso.nombre}",
            detalle={c: ["", v] for c, v in instantanea(proceso, CAMPOS_EDITABLES).items() if v},
        )
        db.session.commit()
        flash(f"Registro #{proceso.id} creado correctamente.", "success")
        return redirect(url_for("procesos.listar"))
    return render_template("procesos/form.html", form=form, titulo="Nuevo registro")


@bp.route("/procesos/<int:proceso_id>/editar", methods=["GET", "POST"])
@login_required
@solo_administrador
def editar(proceso_id):
    proceso = db.get_or_404(Proceso, proceso_id)
    form = ProcesoForm(obj=proceso)
    if form.validate_on_submit():
        antes = instantanea(proceso, CAMPOS_EDITABLES)
        _volcar_form(form, proceso)
        cambios = comparar(antes, instantanea(proceso, CAMPOS_EDITABLES))
        if cambios:
            registrar(
                "EDITAR", "PROCESO", proceso.id,
                descripcion=f"{proceso.cliente} - {proceso.nombre}",
                detalle=cambios,
            )
        db.session.commit()
        flash(
            f"Registro #{proceso.id} actualizado correctamente."
            if cambios else "No se detectaron cambios en el registro.",
            "success" if cambios else "info",
        )
        return redirect(url_for("procesos.listar"))
    historial = db.session.scalars(
        select(Auditoria)
        .where(Auditoria.entidad == "PROCESO", Auditoria.entidad_id == proceso.id)
        .order_by(Auditoria.fecha.desc())
        .limit(20)
    ).all()
    return render_template(
        "procesos/form.html", form=form, titulo=f"Editar registro #{proceso.id}",
        proceso=proceso, historial=historial,
    )


@bp.route("/procesos/<int:proceso_id>/eliminar", methods=["POST"])
@login_required
@solo_administrador
def eliminar(proceso_id):
    proceso = db.get_or_404(Proceso, proceso_id)
    registrar(
        "ELIMINAR", "PROCESO", proceso.id,
        descripcion=f"{proceso.cliente} - {proceso.nombre}",
        detalle={c: [v, ""] for c, v in instantanea(proceso, CAMPOS_EDITABLES).items() if v},
    )
    db.session.delete(proceso)
    db.session.commit()
    flash(f"Registro #{proceso_id} eliminado.", "info")
    return redirect(url_for("procesos.listar"))
