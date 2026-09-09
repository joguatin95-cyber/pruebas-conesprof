"""Procesamiento de las fotos de perfil.

La imagen que sube el usuario NO se guarda tal cual: se vuelve a codificar con
Pillow. Eso recorta el tamano, descarta los metadatos (incluida la ubicacion GPS
que traen muchas fotos de celular) y garantiza que lo almacenado sea realmente una
imagen y no un archivo disfrazado.
"""

import io

from PIL import Image, UnidentifiedImageError

LADO = 320                      # la foto se recorta a un cuadrado de 320x320
TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB de archivo original
FORMATOS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}


def procesar(archivo):
    """Devuelve (bytes_jpeg, mime, error). Si hay error, los dos primeros son None."""
    datos = archivo.read()
    if not datos:
        return None, None, "El archivo esta vacio."
    if len(datos) > TAMANO_MAXIMO:
        return None, None, "La imagen supera los 5 MB (pesa %.1f MB)." % (
            len(datos) / 1024 / 1024)

    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.verify()  # detecta archivos corruptos o que no son imagenes
        imagen = Image.open(io.BytesIO(datos))
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None, "El archivo no es una imagen valida."

    if imagen.format not in FORMATOS:
        return None, None, "Formato no admitido (use JPG, PNG, WEBP, GIF o BMP)."

    # Fondo blanco para imagenes con transparencia, ya que se guardan como JPEG.
    imagen = imagen.convert("RGB")
    imagen = _recortar_cuadrado(imagen)
    imagen = imagen.resize((LADO, LADO), Image.LANCZOS)

    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=85, optimize=True)
    return salida.getvalue(), "image/jpeg", None


def _recortar_cuadrado(imagen):
    """Recorta al centro para que la foto no salga deformada."""
    ancho, alto = imagen.size
    if ancho == alto:
        return imagen
    lado = min(ancho, alto)
    izquierda = (ancho - lado) // 2
    arriba = (alto - lado) // 2
    return imagen.crop((izquierda, arriba, izquierda + lado, arriba + lado))
