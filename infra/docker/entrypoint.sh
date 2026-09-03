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
try:
    from sqlalchemy.engine.url import make_url
    parsed = make_url(url)
    print(f'Conectando a base de datos -> Host: \"{parsed.host}\", Puerto: {parsed.port}, Base: \"{parsed.database}\"')
except Exception:
    pass

for i in range(1, 31):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            print('>>> ¡Conexión exitosa a la base de datos!')
            sys.exit(0)
    except Exception as e:
        print(f'Intento {i}/30: Esperando a la base de datos... ({e})')
        time.sleep(2)

print('ERROR: No se pudo conectar a la base de datos tras 60 segundos.')
print('CÓMO SOLUCIONARLO EN EASYPANEL:')
print('1. Abre tu servicio PostgreSQL en Easypanel.')
print('2. Ve a la pestaña \"Credentials\".')
print('3. Copia el valor de \"Internal Connection URL\" (o el \"Internal Host\").')
print('4. Pégalo en tu servicio App como la variable DATABASE_URL.')
sys.exit(1)
"

echo "=== Ejecutando migraciones de base de datos (Alembic) ==="
alembic upgrade head

echo "=== Iniciando servidor RestaurantOS en 0.0.0.0:8000 ==="
exec uvicorn restaurant_os.main:app --host 0.0.0.0 --port 8000
