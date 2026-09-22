"""Caso de uso: importar procesos desde un archivo tabular.

Una sola clase concentra la regla completa —leer, mapear columnas, validar,
detectar duplicados y (si se pide) guardar— y la usan por igual la pantalla web y
el script de consola. Antes esta logica vivia dentro de importar.py y la web no
podia reutilizarla.

Puntos de diseno:

- **Inyeccion de dependencias por constructor.** Recibe un LectorTabular, un
  RepositorioProcesos y un RegistroDeAuditoria; no los construye. Eso permite
  probarlo con dobles en memoria.
- **Simular es el modo por omision.** `aplicar=False` recorre y valida todo sin
  escribir nada. La pantalla web lo usa para mostrar la vista previa y la consola
  para el informe previo.
- **Objeto de resultado en lugar de excepciones** para los errores de datos: una
  importacion debe reportar todos los problemas de todas las filas de una vez.
  Las excepciones quedan para lo que impide siquiera leer el archivo.
"""

from dataclasses import dataclass

from app.aplicacion.puertos import (
    ErrorDeLectura,
    LectorTabular,
    RegistroDeAuditoria,
    RepositorioProcesos,
)
from app.dominio import normalizacion
from app.dominio.procesos import (
    FilaDuplicada,
    FilaRechazada,
    ResultadoImportacion,
)

# La primera fila del archivo son los encabezados, asi que los datos empiezan en 2.
PRIMERA_FILA_DE_DATOS = 2


@dataclass(frozen=True)
class OpcionesImportacion:
    aplicar: bool = False
    conservar_id: bool = False
    permitir_duplicados: bool = False
    hoja: str | None = None
    limite: int | None = None


class ArchivoInvalido(ErrorDeLectura):
    """El archivo no sirve como fuente: sin columnas obligatorias, vacio, etc."""


class ImportarProcesos:
    def __init__(
        self,
        lector: LectorTabular,
        repositorio: RepositorioProcesos,
        auditoria: RegistroDeAuditoria,
    ) -> None:
        self._lector = lector
        self._repositorio = repositorio
        self._auditoria = auditoria

    def ejecutar(
        self,
        contenido: bytes,
        nombre_origen: str,
        opciones: OpcionesImportacion = OpcionesImportacion(),
    ) -> ResultadoImportacion:
        tabla = self._lector.leer(contenido, opciones.hoja)

        columnas, ignoradas = normalizacion.mapear_columnas(tabla.encabezados)
        ausentes = normalizacion.campos_obligatorios_ausentes(columnas)
        if ausentes:
            encontrados = [normalizacion.a_texto(e) for e in tabla.encabezados
                           if normalizacion.a_texto(e)]
            raise ArchivoInvalido(
                "El archivo no tiene estas columnas obligatorias: %s. "
                "Encabezados encontrados: %s."
                % (", ".join(ausentes), ", ".join(encontrados) or "(ninguno)")
            )

        filas = tabla.filas[: opciones.limite] if opciones.limite else tabla.filas

        existentes: set[tuple] = set()
        if not opciones.permitir_duplicados:
            existentes = self._repositorio.claves_naturales_existentes()

        # Al conservar los ID del archivo hay que comprobar que esten libres ANTES
        # de escribir; si no, la base los rechaza y se pierde toda la importacion.
        ids_ocupados: set[int] = set()
        if opciones.conservar_id:
            ids_ocupados = self._repositorio.ids_existentes()
        ids_vistos: set[int] = set()

        resultado = ResultadoImportacion(
            columnas_reconocidas=tuple(sorted(columnas)),
            columnas_ignoradas=ignoradas,
            origen="%s - %s" % (nombre_origen, tabla.descripcion),
        )
        vistas_en_archivo: set[tuple] = set()

        for numero, fila in enumerate(filas, start=PRIMERA_FILA_DE_DATOS):
            if normalizacion.fila_vacia(fila):
                continue
            resultado.filas_leidas += 1

            proceso, motivos, texto = normalizacion.normalizar_fila(fila, columnas)
            if motivos:
                resultado.rechazadas.append(FilaRechazada(numero, motivos, texto))
                continue

            if opciones.conservar_id and proceso.id_original is not None:
                motivo = self._id_no_usable(proceso.id_original, ids_ocupados, ids_vistos)
                if motivo:
                    resultado.rechazadas.append(FilaRechazada(numero, (motivo,), texto))
                    continue
                ids_vistos.add(proceso.id_original)

            clave = proceso.clave_natural()
            if not opciones.permitir_duplicados:
                if clave in existentes:
                    resultado.duplicadas.append(
                        FilaDuplicada(numero, proceso, "ya esta en la base"))
                    continue
                if clave in vistas_en_archivo:
                    resultado.duplicadas.append(
                        FilaDuplicada(numero, proceso, "repetida en el archivo"))
                    continue

            vistas_en_archivo.add(clave)
            resultado.validas.append(proceso)

        if opciones.aplicar and resultado.validas:
            self._guardar(resultado, opciones)

        return resultado

    @staticmethod
    def _id_no_usable(identificador, ocupados, vistos) -> str | None:
        """Motivo por el que no se puede reutilizar ese ID, o None si esta libre."""
        if identificador in ocupados:
            return ("el ID %d ya esta ocupado en la base; desmarque 'Respetar la "
                    "columna ID del archivo' para que se asigne uno nuevo"
                    % identificador)
        if identificador in vistos:
            return "el ID %d esta repetido dentro del archivo" % identificador
        return None

    def _guardar(self, resultado, opciones) -> None:
        try:
            self._repositorio.agregar_muchos(resultado.validas, opciones.conservar_id)
            self._auditoria.registrar_importacion(
                resultado.total_validas, resultado.origen)
            self._repositorio.confirmar()
            if opciones.conservar_id:
                # Sin esto, el siguiente proceso creado desde la interfaz
                # intentaria reutilizar un ID ya ocupado.
                self._repositorio.sincronizar_secuencia_id()
                self._repositorio.confirmar()
            resultado.aplicado = True
        except Exception:
            self._repositorio.descartar()
            raise
