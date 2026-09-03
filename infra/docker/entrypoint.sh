#!/bin/sh
set -e

echo "=== Verificando conexión a la Base de Datos ==="

python -c "
import sys, time
from sqlalchemy import create_engine
from restaurant_os.config import get_settings
from restaurant_os.database import normalize_database_url

settings = get_settings()
raw_url = settings.database_url
if not raw_url:
    print('WARNING: No se encontró DATABASE_URL configurada.')
    sys.exit(0)

url = normalize_database_url(raw_url)
print(f'Intentando conectar a la base de datos...')

for i in range(1, 31):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print('>>> ¡Conexión exitosa a la base de datos!')
            sys.exit(0)
    except Exception as e:
        print(f'Intento {i}/30: Esperando a la base de datos... ({e})')
        time.sleep(2)

print('ERROR: No se pudo resolver o conectar al host de la base de datos tras 60 segundos.')
print('Por favor verifica en Easypanel:')
print('1. Que el servicio PostgreSQL esté encendido (Running).')
print('2. Que el nombre del HOST en DATABASE_URL sea exactamente el nombre del servicio Postgres en Easypanel (ej. postgres, db, o database).')
print('3. Que ambos servicios estén dentro del mismo Proyecto en Easypanel.')
sys.exit(1)
"

echo "=== Ejecutando migraciones de base de datos (Alembic) ==="
alembic upgrade head

echo "=== Iniciando servidor RestaurantOS en 0.0.0.0:8000 ==="
exec uvicorn restaurant_os.main:app --host 0.0.0.0 --port 8000
