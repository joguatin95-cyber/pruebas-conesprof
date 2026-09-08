-- Creacion de la base de datos y el usuario en PostgreSQL.
-- Ejecutar conectado como superusuario:  psql -U postgres -f sql/init.sql

CREATE DATABASE gestion_procesos
    WITH ENCODING 'UTF8'
    TEMPLATE template0;

-- Usuario de la aplicacion (cambie la contrasena).
CREATE USER app_procesos WITH PASSWORD 'CambiarEstaClave123*';

GRANT ALL PRIVILEGES ON DATABASE gestion_procesos TO app_procesos;

\connect gestion_procesos
GRANT ALL ON SCHEMA public TO app_procesos;

-- Las tablas (usuarios, procesos) las crea SQLAlchemy al ejecutar:  python seed.py
