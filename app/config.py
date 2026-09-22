import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

LOCALES = ("localhost", "127.0.0.1", "::1")


def url_configurada() -> str:
    """DATABASE_URL del entorno, o cadena vacia si aun no se ha configurado.

    Mientras el .env conserve el texto de ejemplo, se ignora para que la aplicacion
    siga arrancando contra SQLite en lugar de fallar al iniciar.
    """
    url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
    return url if "://" in url else ""


def normalizar_url(url: str) -> str:
    """Adapta la cadena de conexion tal como la entregan proveedores como Render.

    - Render la publica como 'postgres://...'; SQLAlchemy 2.x exige indicar el driver.
    - Las conexiones externas a Render requieren TLS, asi que se agrega sslmode=require
      cuando el servidor no es local y la cadena no trae ya un sslmode.
    """
    if not url:
        return url

    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            url = "postgresql+psycopg2://" + url[len(prefijo):]
            break

    if url.startswith("postgresql+psycopg2://") and "sslmode=" not in url:
        servidor = url.rsplit("@", 1)[-1].split("/")[0].split(":")[0]
        # Solo se exige TLS con servidores externos. El nombre interno de Render
        # ("dpg-xxxx-a", sin puntos) viaja por su red privada y no lo necesita.
        if not servidor.startswith(LOCALES) and "." in servidor:
            url += ("&" if "?" in url else "?") + "sslmode=require"

    return url


def en_produccion() -> bool:
    """Render define RENDER=true en sus servicios; tambien se puede forzar a mano."""
    return (os.getenv("RENDER", "").lower() == "true"
            or os.getenv("EN_PRODUCCION", "").lower() in ("1", "true", "si"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-de-desarrollo-no-usar-en-produccion")

    EN_PRODUCCION = en_produccion()

    # En produccion la cookie de sesion solo viaja por HTTPS.
    SESSION_COOKIE_SECURE = EN_PRODUCCION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Si no hay DATABASE_URL configurada se usa SQLite para poder probar en local.
    SQLALCHEMY_DATABASE_URI = normalizar_url(url_configurada()) or (
        "sqlite:///" + os.path.join(BASE_DIR, "dev.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Detecta conexiones caidas antes de usarlas.
        "pool_pre_ping": True,
        # Render cierra las conexiones ociosas: se reciclan antes de que eso ocurra.
        "pool_recycle": 300,
        # connect_timeout solo lo entiende psycopg2; SQLite lo rechaza.
        "connect_args": (
            {"connect_timeout": 10}
            if SQLALCHEMY_DATABASE_URI.startswith("postgresql")
            else {}
        ),
    }

    # Tamano maximo de una subida: fotos de perfil y archivos de importacion.
    # Flask responde 413 si se excede.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # Cantidad de registros por pagina en la pantalla principal.
    ITEMS_POR_PAGINA = int(os.getenv("ITEMS_POR_PAGINA", "25"))

    @staticmethod
    def motor() -> str:
        """Nombre del motor en uso, para mensajes por consola."""
        return Config.SQLALCHEMY_DATABASE_URI.split(":", 1)[0]
