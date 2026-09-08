-- Esquema equivalente al que genera SQLAlchemy. Solo como referencia/documentacion;
-- no es necesario ejecutarlo si usa "python seed.py".

CREATE TABLE usuarios (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    nombre        VARCHAR(120) NOT NULL,
    email         VARCHAR(120) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol           VARCHAR(20)  NOT NULL DEFAULT 'CLIENTE',
    activo        BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE procesos (
    id                 SERIAL PRIMARY KEY,
    fecha_inicio       DATE         NOT NULL,
    cliente            VARCHAR(120) NOT NULL,
    subcliente         VARCHAR(120),
    tipo_proceso       VARCHAR(120) NOT NULL,
    ciudad             VARCHAR(80),
    cedula             VARCHAR(30)  NOT NULL,
    nombre             VARCHAR(150) NOT NULL,
    cargo              VARCHAR(120),
    fecha_finalizacion DATE,
    estado             VARCHAR(30)  NOT NULL DEFAULT 'PENDIENTE',
    factura            VARCHAR(60),
    orden_compra       VARCHAR(60),
    creado_en          TIMESTAMP    NOT NULL DEFAULT NOW(),
    actualizado_en     TIMESTAMP    NOT NULL DEFAULT NOW(),
    creado_por_id      INTEGER REFERENCES usuarios(id)
);

CREATE INDEX ix_procesos_cliente      ON procesos (cliente);
CREATE INDEX ix_procesos_cedula       ON procesos (cedula);
CREATE INDEX ix_procesos_nombre       ON procesos (nombre);
CREATE INDEX ix_procesos_estado       ON procesos (estado);
CREATE INDEX ix_procesos_fecha_inicio ON procesos (fecha_inicio);

-- Historico de cambios (agregado posteriormente).
-- usuario_id se guarda sin llave foranea a proposito: el historico debe sobrevivir
-- a la eliminacion de la cuenta que hizo el cambio, por eso tambien se copia el username.
CREATE TABLE auditoria (
    id               SERIAL PRIMARY KEY,
    fecha            TIMESTAMP    NOT NULL DEFAULT NOW(),
    usuario_id       INTEGER,
    usuario_username VARCHAR(50)  NOT NULL DEFAULT 'sistema',
    accion           VARCHAR(20)  NOT NULL,   -- CREAR / EDITAR / ELIMINAR
    entidad          VARCHAR(20)  NOT NULL,   -- PROCESO / USUARIO
    entidad_id       INTEGER,
    descripcion      VARCHAR(255) NOT NULL DEFAULT '',
    detalle          TEXT                     -- JSON: {campo: [antes, despues]}
);

CREATE INDEX ix_auditoria_fecha      ON auditoria (fecha);
CREATE INDEX ix_auditoria_accion     ON auditoria (accion);
CREATE INDEX ix_auditoria_entidad    ON auditoria (entidad);
CREATE INDEX ix_auditoria_entidad_id ON auditoria (entidad_id);

-- Alcance por cliente del rol CLIENTE (agregado posteriormente).
ALTER TABLE usuarios ADD COLUMN cliente_asignado VARCHAR(120);
