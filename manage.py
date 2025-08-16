#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import socket # <--- Agregado



def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'evento.settings')

    # --- INICIO DEL CÓDIGO AGREGADO ---
    # Muestra la IP local al iniciar el servidor de desarrollo
    if 'runserver' in sys.argv:
        try:
            # Obtiene el nombre del host y la dirección IP local
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Intenta encontrar el puerto en los argumentos del comando
            # Si no lo encuentra, usa el puerto por defecto '8000'
            port = '8000'
            if len(sys.argv) > 2:
                # Si se especifica como 'manage.py runserver 0.0.0.0:8080'
                if ':' in sys.argv[2]:
                    port = sys.argv[2].split(':')[1]
                # Si se especifica como 'manage.py runserver 8080'
                elif sys.argv[2].isdigit():
                    port = sys.argv[2]

            print("\n✅ ¡Servidor de desarrollo listo!")
            print(f"   ✓ Accesible en tu red local en: http://{local_ip}:{port}/")
            print(f"   ✓ Accesible localmente en:     http://127.0.0.1:{port}/")
            print("   (Presiona CTRL+C para detener)\n")

            # Asegura que el servidor sea accesible desde la red local
            # si se ejecuta solo con 'python manage.py runserver'
            if len(sys.argv) == 2 and sys.argv[1] == 'runserver':
                 sys.argv.append('0.0.0.0:8000')

        except Exception as e:
            print(f"\n⚠️  No se pudo obtener la IP local: {e}")
            print("   Asegúrate de estar conectado a una red.\n")
    # --- FIN DEL CÓDIGO AGREGADO ---

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()