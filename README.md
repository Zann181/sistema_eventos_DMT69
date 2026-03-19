# sistema_eventos_DMT69

Sistema modular para operar sucursales, eventos, entrada, catalogo, barra, QR y correo desde un mismo panel.

## Arquitectura

- `branches`: sucursales y personal.
- `events`: configuracion del evento, QR y branding de correo.
- `identity`: membresias, permisos y contexto activo.
- `attendees`: registro, check-in, exportes y compartidos.
- `catalog`: productos base.
- `sales`: POS, caja y productos habilitados por evento.
- `inventory`: auditoria historica de movimientos.
- `media_assets`: normalizacion y recuperacion de archivos.
- `shared_ui`: login, dashboard y layout comun.
- `ticketing`: utilidades internas de QR, WhatsApp y correo. No se registra como app Django.

La capa `core` y la ruta `/legacy/` quedaron retiradas.

## Instalacion

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Base de datos

Configuracion local por defecto:

```text
DB_NAME=evento_db_clean_20260316
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
```

Recrear una base limpia:

```powershell
venv\Scripts\python -c "import pymysql; conn=pymysql.connect(host='127.0.0.1', user='tu_usuario_mysql', password='tu_password_mysql', port=3306, autocommit=True); cur=conn.cursor(); cur.execute('DROP DATABASE IF EXISTS evento_db_clean_20260316'); cur.execute('CREATE DATABASE evento_db_clean_20260316 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'); cur.close(); conn.close()"
venv\Scripts\python manage.py migrate
```

## Desarrollo

Servidor local:

```powershell
venv\Scripts\python manage.py runserver_plus --cert-file certs/localhost+3.pem --key-file certs/localhost+3-key.pem 0.0.0.0:8000
```

Validacion:

```powershell
venv\Scripts\python manage.py check
venv\Scripts\python manage.py test
```

## Rutas activas

- `/`
- `/login/`
- `/sucursales/`
- `/eventos/`
- `/entrada/`
- `/catalogo/`
- `/barra/`

## Artefactos locales

No deben versionarse:

- `media/`
- `staticfiles/`
- `certs/`
- `__pycache__/`
- `.vscode/`
- archivos SQLite locales
