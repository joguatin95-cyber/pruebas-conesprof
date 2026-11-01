from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config, enmascarar
from app.extensions import csrf, db, login_manager


def anunciar_base(app):
    """Deja constancia en el registro de contra que base quedo apuntando.

    Sin DATABASE_URL la configuracion cae a SQLite para que se pueda probar en
    local sin preparar nada. En un servidor eso casi siempre significa que la
    variable falta o esta mal escrita, y el sintoma que llega al usuario es un
    error 500 por tablas inexistentes, que no apunta a la causa. Anunciarlo al
    arrancar convierte media hora de diagnostico en una linea del registro.
    """
    uri = app.config["SQLALCHEMY_DATABASE_URI"]

    if not uri.startswith("sqlite"):
        app.logger.info("Base de datos: %s", enmascarar(uri))
        return

    app.logger.warning(
        "DATABASE_URL no esta definida o no es una cadena de conexion valida "
        "(debe contener '://'). Se usara SQLite en %s, que en un servidor esta "
        "vacia y hara fallar toda consulta.", uri.split("///", 1)[-1])


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    anunciar_base(app)

    if app.config.get("EN_PRODUCCION"):
        # Detras del proxy de Render, para que Flask reconozca el HTTPS original
        # y no marque como insegura la cookie de sesion.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    from app.routes.auditoria import bp as auditoria_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.importacion import bp as importacion_bp
    from app.routes.perfil import bp as perfil_bp
    from app.routes.procesos import bp as procesos_bp
    from app.routes.usuarios import bp as usuarios_bp

    app.register_blueprint(auditoria_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(importacion_bp)
    app.register_blueprint(perfil_bp)
    app.register_blueprint(procesos_bp)
    app.register_blueprint(usuarios_bp)

    @app.errorhandler(413)
    def archivo_muy_grande(error):
        return render_template("error.html", codigo=413,
                               mensaje="El archivo es demasiado grande (maximo 5 MB)."), 413

    @app.errorhandler(403)
    def sin_permisos(error):
        return render_template("error.html", codigo=403,
                               mensaje="No tiene permisos para realizar esta accion."), 403

    @app.errorhandler(404)
    def no_encontrado(error):
        return render_template("error.html", codigo=404,
                               mensaje="La pagina solicitada no existe."), 404

    @app.context_processor
    def inyectar_etiquetas():
        from app.auditoria import ETIQUETAS

        return {"etiquetas": ETIQUETAS}

    @app.shell_context_processor
    def shell_context():
        from app.models import Auditoria, Proceso

        return {"db": db, "Usuario": Usuario, "Proceso": Proceso, "Auditoria": Auditoria}

    return app
