# Gestion de Procesos

Aplicacion web en **Python (Flask)** con autenticacion y control de acceso por roles,
sobre **PostgreSQL**.

## Roles

| Rol | Ver procesos | Crear / editar / eliminar procesos | Gestionar usuarios |
|---|---|---|---|
| **ADMINISTRADOR** | Si | Si | Si |
| **CONTADOR** | Si (todos los clientes) | No | No |
| **CLIENTE** | Solo su cliente asignado | No | No |

El control se aplica en dos capas: la interfaz oculta las acciones no permitidas y cada
ruta de escritura esta protegida por el decorador `@solo_administrador`, de modo que un
usuario sin permisos recibe **403** aunque escriba la URL directamente.

### Alcance del rol CLIENTE

Cada usuario con rol CLIENTE tiene un campo **Cliente asignado** y solo ve los registros
de ese cliente. El filtro se aplica en la consulta misma, no en la vista, asi que tambien
cubre el buscador, los filtros y la exportacion a CSV: el usuario no puede ver registros
de otro cliente por mas que cambie los parametros de la URL.

Si un usuario CLIENTE **no tiene cliente asignado no ve ningun registro** (comportamiento
restrictivo por seguridad). La aplicacion avisa de esa situacion al administrador cuando
crea o edita la cuenta, y la marca como *sin asignar* en el listado de usuarios.

Al cambiar el rol de un usuario a ADMINISTRADOR o CONTADOR, el cliente asignado se limpia
automaticamente.

### Historico de cambios

Toda creacion, edicion o eliminacion —de procesos y de usuarios— queda registrada en la
tabla `auditoria` con fecha, usuario responsable, accion y el detalle campo por campo
(**valor anterior → valor nuevo**). Se consulta en **Historico** (menu superior, solo
administrador), con filtros por texto, accion, entidad y rango de fechas. Cada registro
tiene ademas un enlace *Historial* que muestra solo sus movimientos, y la pantalla de
edicion de un proceso muestra sus ultimos 20 cambios al final.

Detalles de diseno:

- Las contrasenas **nunca** se guardan en el historico; solo queda constancia de que
  cambiaron.
- El historico conserva el nombre de usuario, de modo que sobrevive si esa cuenta se
  elimina despues.
- Una edicion que no modifica ningun campo no genera movimiento.

## Vista por meses

La pantalla de procesos agrupa los registros en **pestanas de mes**, como las hojas de un
libro de Excel: `Todos`, `Septiembre 2026`, `Agosto 2026`... Cada pestana muestra cuantos
registros contiene, y al cambiar de pestana se conservan los demas filtros activos.

La tabla imita una hoja de calculo: columna de numero de fila, cuadricula, encabezado que
queda fijo al desplazarse y filas alternadas.

Los meses se calculan con una consulta agregada en la base (`GROUP BY`), no trayendo los
procesos a memoria, y respetan el alcance del usuario: un CLIENTE solo ve los meses en
los que su propio cliente tiene registros.

## Pantalla principal

Tabla con las columnas solicitadas:

`ID` · `FECHA INICIO` · `CLIENTE` · `SUBCLIENTE` · `TIPO DE PROCESO` · `CIUDAD` ·
`CEDULA` · `NOMBRE` · `CARGO` · `FECHA FINALIZACION` · `ESTADO` · `FACTURA` ·
`ORDEN DE COMPRA`

Incluye buscador por texto, filtro por estado, filtro por rango de fecha de inicio,
paginacion y exportacion a CSV (respeta los filtros activos).

## Instalacion

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Configuracion

Copie `.env.example` a `.env` y ajuste los valores:

```
SECRET_KEY=una-clave-larga-y-aleatoria
DATABASE_URL=postgresql+psycopg2://usuario:password@localhost:5432/gestion_procesos
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin123*
```

> Si `DATABASE_URL` no esta definida (o conserva el texto de ejemplo), la aplicacion usa
> SQLite (`dev.db`) para pruebas locales en vez de fallar al arrancar. Para produccion
> siempre defina la cadena de PostgreSQL y confirmela con `python check_db.py`.

## Base de datos PostgreSQL en Render

1. En <https://dashboard.render.com> cree (o abra) su base **PostgreSQL**.
2. En la seccion **Connections** copie la **External Database URL**.
   No use la *Internal Database URL*: esa solo funciona entre servicios de Render.
3. Pegue esa cadena en el archivo `.env`, en la linea `DATABASE_URL=`.
4. Verifique la conexion:

```bash
python check_db.py
```

5. Cree las tablas y el administrador inicial:

```bash
python seed.py
```

6. Vuelva a verificar; debe reportar las tres tablas:

```bash
python check_db.py
```

La aplicacion adapta sola el formato de la cadena: acepta `postgres://`,
`postgresql://` o `postgresql+psycopg2://`, y agrega `sslmode=require` cuando el
servidor no es local, que es lo que exige Render para conexiones externas.

`check_db.py` nunca imprime la contrasena: la enmascara antes de mostrar la cadena.

**Importante sobre el plan gratuito de Render:** las bases gratuitas expiran a los 30 dias
y quedan inaccesibles. Si `check_db.py` deja de conectar, revise primero el estado de la
base en el panel de Render.

## Base de datos PostgreSQL local (alternativa)

1. Cree la base y el usuario:

```bash
psql -U postgres -f sql/init.sql
```

2. Cree las tablas y el administrador inicial:

```bash
python seed.py
```

Para cargar ademas cuatro registros de ejemplo:

```bash
python seed.py --demo
```

`sql/esquema_referencia.sql` documenta el DDL equivalente al que genera SQLAlchemy
(no es necesario ejecutarlo).

### Actualizar una base que ya existia

Si ya tenia la base creada antes de las funciones de alcance por cliente e historico:

```bash
python migrate.py
```

Agrega la columna `usuarios.cliente_asignado` y la tabla `auditoria` si faltan.
Es idempotente y funciona tanto en PostgreSQL como en SQLite.

## Arquitectura

El codigo nuevo sigue Arquitectura Limpia: las dependencias apuntan siempre hacia
adentro, y el dominio no conoce a nadie.

```
app/
  dominio/            Entidades y reglas. Sin Flask, sin SQLAlchemy, sin Excel.
    procesos.py       FilaProceso, estados, campos obligatorios, clave natural
    normalizacion.py  Como se interpretan fechas, estados y encabezados reales
  aplicacion/         Casos de uso y PUERTOS (abstracciones)
    puertos.py        LectorTabular, RepositorioProcesos, RegistroDeAuditoria
    importar_procesos.py   El caso de uso ImportarProcesos
  infraestructura/    ADAPTADORES: implementan los puertos
    lectores.py       LectorExcel, LectorCsv y la factory lector_para()
    repositorios.py   RepositorioProcesosSQLAlchemy, AuditoriaSQLAlchemy
  routes/             Presentacion (Flask). Capa delgada: no contiene reglas.
```

### Patrones aplicados y por que

| Patron | Donde | Que problema resuelve |
|---|---|---|
| **Puertos y adaptadores** | `aplicacion/puertos.py` | El caso de uso se prueba con dobles en memoria, sin Excel ni base de datos |
| **Strategy** | `LectorExcel` / `LectorCsv` | Agregar otro formato no obliga a tocar el caso de uso |
| **Factory Method** | `lector_para(nombre)` | Quien llama no necesita conocer las clases concretas |
| **Repository** | `RepositorioProcesos` | Aisla la persistencia; el dominio no sabe que existe SQLAlchemy |
| **Inyeccion por constructor** | `ImportarProcesos.__init__` | Invierte la dependencia (la D de SOLID) |
| **Objeto de resultado** | `ResultadoImportacion` | Una importacion reporta TODOS los errores, no se detiene en el primero |

La consecuencia practica: la pantalla web y el script de consola comparten exactamente
la misma logica de importacion. Antes esa logica vivia dentro de `importar.py` y la web
no podia reutilizarla.

**El codigo anterior a esta refactorizacion (rutas de usuarios, procesos y auditoria)
todavia mezcla reglas con acceso a datos.** Se ira moviendo a esta estructura a medida
que se toque, para no reescribir de golpe lo que ya funciona y esta probado.

## Mi perfil

Todos los usuarios —incluidos CONTADOR y CLIENTE— tienen un panel propio en
**Mi perfil** (menu superior) donde pueden:

- **Cambiar su contrasena.** Se exige la contrasena actual, minimo 8 caracteres, y no
  se admite repetir la que ya tenian.
- **Subir o quitar su foto.** Se recorta al centro, se reduce a 320x320 y se vuelve a
  codificar como JPEG con Pillow. Esa reconversion descarta los metadatos (incluida la
  ubicacion GPS que traen muchas fotos de celular) y garantiza que lo guardado sea
  realmente una imagen. Maximo 5 MB de archivo original.

Es la unica parte donde CONTADOR y CLIENTE pueden escribir, y siempre sobre su propia
cuenta: la ruta no recibe ningun identificador de usuario, se toma de la sesion. Sus
permisos sobre los procesos no cambian.

**Las fotos se guardan en la base de datos, no en disco.** El almacenamiento de Render es
efimero: cualquier archivo escrito en el disco desaparece en el siguiente despliegue.

## Contrasenas: por que no se pueden ver

En la base **no existe ninguna contrasena**. Solo se guarda un hash (scrypt), que es una
huella irreversible: sirve para comprobar si una clave es correcta, pero de ella no se
puede reconstruir el texto original. Ni el administrador, ni quien tenga acceso directo a
la base, pueden leer la contrasena de un usuario. Es intencional: si la base se filtrara,
las contrasenas seguirian protegidas.

Cuando un usuario pierde su contrasena, el administrador usa **Restablecer clave** en el
listado de usuarios. La aplicacion genera una contrasena temporal de 12 caracteres, la
muestra **una sola vez** en pantalla para que se la entregue al usuario, e invalida la
anterior. El alfabeto excluye los caracteres que se confunden al dictarla (O, 0, l, 1, I).

En el historico de cambios queda constancia de que la contrasena cambio y de quien lo
hizo, pero **nunca el valor**.

## Importar un Excel desde la aplicacion

**Procesos -> Importar Excel** (solo ADMINISTRADOR). El flujo tiene dos pasos y el
primero no escribe nada:

1. **Subir y revisar.** Se valida el archivo completo y se muestra cuantas filas se
   cargarian, cuantas estan repetidas y cuales tienen errores, con una vista previa de
   los primeros 20 registros. Las filas con error se pueden descargar en CSV para
   corregirlas.
2. **Confirmar.** Solo entonces se escribe en la base.

El archivo subido se guarda en la tabla `importaciones_pendientes` entre los dos pasos, y
se borra al confirmar o descartar. Los que queden sin confirmar se descartan solos a las
12 horas. Se guarda en la base y no en disco por dos razones: el almacenamiento de Render
es efimero, y con varios procesos de gunicorn no hay garantia de que la confirmacion
caiga en el mismo proceso que recibio la subida.

**Agregar un registro suelto sigue disponible** en *+ Nuevo registro*: la importacion no
lo reemplaza.

Las reglas de conversion, las columnas reconocidas y la deteccion de duplicados son las
mismas que usa el script de consola, porque comparten el caso de uso. Estan descritas en
la seccion siguiente.

## Importacion por consola (Excel o CSV)

```bash
python importar.py mis_datos.xlsx              # 1) SIMULA y muestra el informe
python importar.py mis_datos.xlsx --aplicar    # 2) importa de verdad
```

**Sin `--aplicar` no se escribe nada en la base.** El primer comando valida todo el
archivo y reporta cuantas filas quedarian cargadas, cuantas estan repetidas y cuales
tienen errores. Solo cuando el informe se ve bien se repite con `--aplicar`.

En `plantillas/` hay un modelo en ambos formatos, ya con los encabezados correctos.

### Encabezados

El orden de las columnas no importa, y las mayusculas, tildes y signos son indiferentes:
`Cédula`, `CEDULA` y `cedula` se reconocen igual. Tambien se aceptan nombres alternativos
frecuentes (`Documento`, `Fecha de Inicio`, `Tipo Proceso`, `Nombre Completo`, `Fecha Fin`,
`Estatus`, `No Factura`, `Orden Compra`...). Las columnas que no se reconozcan se ignoran
y se listan en el informe.

**Obligatorias:** FECHA INICIO, CLIENTE, TIPO DE PROCESO, CEDULA, NOMBRE.

### Conversiones automaticas

| Entrada | Resultado |
|---|---|
| `15/01/2026`, `2026-01-15`, `15-01-2026`, fecha de Excel | fecha valida |
| `terminado`, `cerrado`, `entregado` | `FINALIZADO` |
| `en trámite`, `en curso`, `proceso` | `EN PROCESO` |
| `cancelado`, `desistido` | `ANULADO` |
| estado vacio | `PENDIENTE` |
| espacios sobrantes | se recortan |
| filas totalmente vacias | se omiten en silencio |

### Que se rechaza

Una fila se rechaza (y **no** detiene la importacion) si le falta un campo obligatorio,
tiene una fecha ilegible, un estado no reconocido, una fecha de finalizacion anterior a la
de inicio, o un texto mas largo de lo que admite la columna. Todas las filas rechazadas se
guardan con su motivo en `<nombre_del_archivo>_rechazadas.csv`, listo para corregir y
volver a cargar.

### Duplicados

Se considera repetido un registro con la misma combinacion de **cedula + cliente +
fecha de inicio + tipo de proceso**. Por defecto se omiten, tanto los repetidos dentro del
archivo como los que ya estan en la base. Gracias a esto, **volver a correr la misma
importacion no duplica nada**, lo que permite cargar un archivo por partes o reintentar sin
riesgo. Use `--permitir-duplicados` si de verdad necesita cargarlos.

### Otras opciones

| Opcion | Para que sirve |
|---|---|
| `--hoja "Datos"` | elige la hoja del Excel (por defecto, la primera) |
| `--limite 20` | procesa solo las primeras 20 filas, util para una prueba rapida |
| `--conservar-id` | respeta la columna ID del archivo en vez de generar uno nuevo |
| `--permitir-duplicados` | carga tambien los registros repetidos |

Con `--conservar-id` la aplicacion ademas **adelanta la secuencia de PostgreSQL** al mayor
ID cargado. Sin ese ajuste, el siguiente registro creado desde la interfaz intentaria usar
un ID que ya existe y fallaria.

Cada importacion queda registrada en el historico de cambios como una entrada del usuario
`sistema`, indicando cuantos registros se cargaron y desde que archivo.

## Ejecucion

```bash
python run.py
```

Abra <http://127.0.0.1:5000> e ingrese con el usuario administrador creado por `seed.py`.
**Cambie la contrasena del administrador despues del primer ingreso**
(Usuarios → Editar → Nueva contrasena).

Para produccion, sirva con gunicorn (Linux) o waitress (Windows):

```bash
gunicorn wsgi:app -w 4 -b 0.0.0.0:8000
```

## Publicar la aplicacion en internet (Render)

La aplicacion corre en `127.0.0.1:5000` solo dentro de su computador. Para que sea
accesible desde internet hay que publicarla como **Web Service** en Render.

Render despliega desde un repositorio Git, asi que el codigo debe estar en GitHub.

### 1. Subir el codigo a GitHub

Cree un repositorio **privado** en <https://github.com/new> (no agregue README ni
.gitignore, el proyecto ya los tiene) y luego, desde la carpeta del proyecto:

```bash
git remote add origin https://github.com/SU_USUARIO/SU_REPOSITORIO.git
git push -u origin main
```

El archivo `.env` **no se sube**: esta excluido en `.gitignore`. Las credenciales se
configuran aparte, en el panel de Render.

### 2. Crear el Web Service en Render

En <https://dashboard.render.com>: **New +** -> **Web Service** -> conecte el repositorio.

Render lee `render.yaml` y toma la configuracion sola. Si prefiere hacerlo a mano:

| Campo | Valor |
|---|---|
| Region | **Oregon** (la misma de la base de datos) |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60` |

### 3. Configurar las variables de entorno

En la pestana **Environment** del servicio:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la **Internal** Database URL de `conesprof` |
| `SECRET_KEY` | una clave larga y aleatoria (Render puede generarla) |
| `PYTHON_VERSION` | `3.12.4` |

Aqui si conviene la **Internal** Database URL (no la External): el servicio web y la base
estan en la misma region, la conexion no sale a internet y es mas rapida.

No hace falta crear tablas: ya existen. Si algun dia despliega contra una base nueva,
ejecute `python seed.py` desde su computador con la External URL configurada.

### 4. Entrar

Render asigna una direccion tipo `https://gestion-procesos.onrender.com`. Ingrese con el
usuario `admin` y **cambie la contrasena de inmediato**.

### Que cambia en produccion

Cuando detecta que corre en Render, la aplicacion activa sola:

- La cookie de sesion viaja **solo por HTTPS** (`SESSION_COOKIE_SECURE`).
- `ProxyFix`, para reconocer el HTTPS original detras del proxy de Render.
- `gunicorn` como servidor, en lugar del servidor de desarrollo de Flask.

### Limitaciones del plan gratuito

- El servicio **se duerme tras 15 minutos sin uso**; la primera visita despues tarda
  cerca de un minuto en responder. Es normal, no es una falla.
- La base de datos gratuita **expira a los 30 dias**.

Ambas se resuelven pasando esos servicios a un plan pago en Render.

## Estructura

```
app/
  __init__.py       Fabrica de la aplicacion y manejadores de error
  config.py         Configuracion y lectura del .env
  extensions.py     Instancias de SQLAlchemy, Flask-Login y CSRF
  models.py         Modelos Usuario y Proceso, roles y estados
  forms.py          Formularios con validacion (WTForms)
  security.py       Decorador @solo_administrador
  auditoria.py      Utilidades del historico (instantaneas y comparacion de cambios)
  imagenes.py       Validacion y reduccion de las fotos de perfil
  routes/
    auth.py         Login y logout
    procesos.py     Listado, filtros, CSV y CRUD de procesos
    usuarios.py     CRUD de usuarios (solo administrador)
    auditoria.py    Consulta del historico de cambios
    perfil.py       Panel personal: foto y cambio de contrasena propia
  templates/        Plantillas Jinja2
  static/css/       Hoja de estilos
sql/                Scripts de PostgreSQL
run.py              Punto de entrada
seed.py             Crea tablas, administrador inicial y datos de ejemplo
migrate.py          Actualiza una base existente al modelo actual
check_db.py         Diagnostica la conexion a la base de datos
importar.py         Importacion por consola (adaptador del caso de uso)
plantillas/         Modelos de archivo para la importacion
render.yaml         Configuracion del despliegue en Render
```

## Seguridad implementada

- Contrasenas almacenadas con hash (`werkzeug.security`, PBKDF2). Nunca en texto plano.
- Proteccion CSRF en todos los formularios (Flask-WTF).
- Sesiones firmadas con `SECRET_KEY`; el parametro `next` del login solo acepta rutas internas.
- Cuentas desactivables sin necesidad de eliminarlas.
- No se permite que un administrador se elimine, se desactive o se cambie el rol a si mismo,
  ni que quede el sistema sin administradores activos.
- El alcance del rol CLIENTE se aplica en la consulta a la base, no en la plantilla.
- Al eliminar un usuario, los procesos que creo se conservan (solo se suelta la referencia
  al autor) y su rastro en el historico permanece.

## Estados de un proceso

`PENDIENTE`, `EN PROCESO`, `FINALIZADO`, `ANULADO`.
Se editan en la constante `ESTADOS` de `app/models.py`.
