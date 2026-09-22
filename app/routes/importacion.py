"""Pantalla de importacion desde Excel o CSV. Solo ADMINISTRADOR.

Esta capa es deliberadamente delgada: recibe el archivo, arma el caso de uso con
sus adaptadores y muestra el resultado. Ninguna regla de validacion vive aqui.

El flujo tiene dos pasos a proposito:

  1. Subir  -> se valida TODO el archivo y se muestra la vista previa. No escribe.
  2. Confirmar -> se vuelve a procesar el archivo guardado y se aplica.

Se procesa dos veces en lugar de arrastrar las filas validadas entre peticiones
porque el archivo es la unica fuente de verdad, y porque entre los dos pasos la
base pudo cambiar (otro administrador pudo cargar los mismos registros).
"""

from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.aplicacion.importar_procesos import (
    ImportarProcesos,
    OpcionesImportacion,
)
from app.aplicacion.puertos import ErrorDeLectura
from app.extensions import db
from app.forms import ConfirmarImportacionForm, SubirArchivoForm
from app.infraestructura.lectores import EXTENSIONES_ADMITIDAS, hojas_de, lector_para
from app.infraestructura.repositorios import (
    AuditoriaSQLAlchemy,
    RepositorioProcesosSQLAlchemy,
)
from app.models import ImportacionPendiente
from app.security import solo_administrador

bp = Blueprint("importacion", __name__, url_prefix="/procesos/importar")

# Un archivo subido y no confirmado se descarta pasado este tiempo.
VIDA_DE_PENDIENTE = timedelta(hours=12)


def _caso_de_uso(nombre_archivo: str) -> ImportarProcesos:
    """Composicion de dependencias (el 'inyector' de la aplicacion)."""
    return ImportarProcesos(
        lector=lector_para(nombre_archivo),
        repositorio=RepositorioProcesosSQLAlchemy(creado_por_id=current_user.id),
        auditoria=AuditoriaSQLAlchemy(),
    )


def _purgar_pendientes() -> None:
    limite = datetime.utcnow() - VIDA_DE_PENDIENTE
    db.session.execute(
        delete(ImportacionPendiente).where(ImportacionPendiente.creado_en < limite)
    )
    db.session.commit()


@bp.route("/", methods=["GET"])
@login_required
@solo_administrador
def formulario():
    _purgar_pendientes()
    return render_template(
        "procesos/importar.html",
        form=SubirArchivoForm(),
        extensiones=", ".join(EXTENSIONES_ADMITIDAS),
    )


@bp.route("/", methods=["POST"])
@login_required
@solo_administrador
def previsualizar():
    form = SubirArchivoForm()
    if not form.validate_on_submit():
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")
        return redirect(url_for("importacion.formulario"))

    archivo = form.archivo.data
    contenido = archivo.read()
    if not contenido:
        flash("El archivo esta vacio.", "danger")
        return redirect(url_for("importacion.formulario"))

    nombre = archivo.filename or "archivo"
    hoja = (form.hoja.data or "").strip() or None
    opciones = OpcionesImportacion(
        aplicar=False,
        hoja=hoja,
        conservar_id=form.conservar_id.data,
        permitir_duplicados=form.permitir_duplicados.data,
    )

    try:
        resultado = _caso_de_uso(nombre).ejecutar(contenido, nombre, opciones)
    except ErrorDeLectura as error:
        flash(str(error), "danger")
        return redirect(url_for("importacion.formulario"))

    # Se guarda para que el paso de confirmacion pueda reprocesarlo.
    pendiente = ImportacionPendiente(
        usuario_id=current_user.id, nombre_archivo=nombre,
        hoja=hoja, contenido=contenido,
    )
    db.session.add(pendiente)
    db.session.commit()

    return render_template(
        "procesos/importar_previa.html",
        resultado=resultado,
        pendiente=pendiente,
        hojas=hojas_de(contenido),
        form=ConfirmarImportacionForm(
            conservar_id=form.conservar_id.data,
            permitir_duplicados=form.permitir_duplicados.data,
        ),
    )


@bp.route("/<int:pendiente_id>/confirmar", methods=["POST"])
@login_required
@solo_administrador
def confirmar(pendiente_id):
    form = ConfirmarImportacionForm()
    if not form.validate_on_submit():
        flash("La confirmacion no era valida. Vuelva a intentarlo.", "danger")
        return redirect(url_for("importacion.formulario"))

    pendiente = db.session.get(ImportacionPendiente, pendiente_id)
    if pendiente is None:
        flash("La carga ya no esta disponible; vuelva a subir el archivo.", "warning")
        return redirect(url_for("importacion.formulario"))

    nombre_archivo = pendiente.nombre_archivo
    opciones = OpcionesImportacion(
        aplicar=True,
        hoja=pendiente.hoja,
        conservar_id=form.conservar_id.data,
        permitir_duplicados=form.permitir_duplicados.data,
    )

    try:
        resultado = _caso_de_uso(nombre_archivo).ejecutar(
            pendiente.contenido, nombre_archivo, opciones)
    except ErrorDeLectura as error:
        flash(str(error), "danger")
        return redirect(url_for("importacion.formulario"))
    except IntegrityError:
        current_app.logger.exception(
            "Conflicto de integridad al importar %s", pendiente_id)
        flash(
            "La base rechazo los registros por un conflicto de identificadores y no "
            "se guardo nada. Suele ocurrir al marcar 'Respetar la columna ID del "
            "archivo' cuando esos ID ya existen: desmarquela y vuelva a intentarlo.",
            "danger")
        return redirect(url_for("importacion.formulario"))
    except Exception:
        current_app.logger.exception("Fallo la importacion %s", pendiente_id)
        flash("No se pudo completar la importacion; no se guardo nada. "
              "Revise el archivo y vuelva a intentarlo.", "danger")
        return redirect(url_for("importacion.formulario"))

    # El archivo ya cumplio su proposito.
    db.session.delete(pendiente)
    db.session.commit()

    if resultado.aplicado:
        flash("Se cargaron %d registro(s) desde %s."
              % (resultado.total_validas, nombre_archivo), "success")
    else:
        flash("No habia ninguna fila valida para cargar.", "warning")

    if resultado.total_rechazadas or resultado.total_duplicadas:
        flash("Se omitieron %d fila(s) con errores y %d duplicada(s)."
              % (resultado.total_rechazadas, resultado.total_duplicadas), "info")

    return redirect(url_for("procesos.listar"))


@bp.route("/<int:pendiente_id>/descartar", methods=["POST"])
@login_required
@solo_administrador
def descartar(pendiente_id):
    pendiente = db.session.get(ImportacionPendiente, pendiente_id)
    if pendiente is not None:
        db.session.delete(pendiente)
        db.session.commit()
    flash("Carga descartada. No se guardo nada.", "info")
    return redirect(url_for("importacion.formulario"))


@bp.route("/plantilla")
@login_required
@solo_administrador
def plantilla():
    """Archivo de ejemplo con los encabezados correctos."""
    import csv
    import io as _io

    from flask import Response

    from app.dominio.procesos import CAMPOS, TITULOS

    salida = _io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow([TITULOS[c] for c in CAMPOS])
    escritor.writerow(["15/01/2026", "ALMACENES EXITO", "BODEGA NORTE",
                       "SELECCION", "MEDELLIN", "1017234567", "JUAN PEREZ",
                       "AUXILIAR LOGISTICO", "28/01/2026", "FINALIZADO",
                       "FA-1001", "OC-5510"])
    return Response(
        "﻿" + salida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=plantilla_procesos.csv"},
    )


@bp.route("/rechazadas/<int:pendiente_id>")
@login_required
@solo_administrador
def rechazadas(pendiente_id):
    """Descarga las filas que no pasaron la validacion, para corregirlas."""
    import csv
    import io as _io

    from flask import Response, abort

    from app.dominio.procesos import CAMPOS, TITULOS

    pendiente = db.session.get(ImportacionPendiente, pendiente_id)
    if pendiente is None:
        abort(404)

    opciones = OpcionesImportacion(aplicar=False, hoja=pendiente.hoja)
    try:
        resultado = _caso_de_uso(pendiente.nombre_archivo).ejecutar(
            pendiente.contenido, pendiente.nombre_archivo, opciones)
    except ErrorDeLectura as error:
        flash(str(error), "danger")
        return redirect(url_for("importacion.formulario"))

    salida = _io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(["FILA", "MOTIVO"] + [TITULOS[c] for c in CAMPOS])
    for fila in resultado.rechazadas:
        escritor.writerow([fila.numero, fila.motivo]
                          + [fila.valores.get(c, "") for c in CAMPOS])

    return Response(
        "﻿" + salida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=filas_rechazadas.csv"},
    )


@bp.route("/pendientes")
@login_required
@solo_administrador
def pendientes():
    filas = db.session.scalars(
        select(ImportacionPendiente)
        .where(ImportacionPendiente.usuario_id == current_user.id)
        .order_by(ImportacionPendiente.creado_en.desc())
    ).all()
    return render_template("procesos/importaciones_pendientes.html", pendientes=filas)
