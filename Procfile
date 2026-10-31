# Comando de arranque en Elastic Beanstalk.
#
# El servidor nginx de la plataforma reenvia las peticiones al puerto 8000 del
# propio equipo, asi que gunicorn tiene que escuchar ahi. No se usa $PORT porque
# la plataforma de Python no define esa variable.
#
# Dos procesos atienden en paralelo, y 60 segundos de espera dan margen a la
# importacion de archivos grandes, que es lo mas lento que hace la aplicacion.
web: gunicorn wsgi:app --bind :8000 --workers 2 --timeout 60
