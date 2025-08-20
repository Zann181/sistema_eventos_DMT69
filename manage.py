#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import socket

def get_local_ip():
    """
    Obtiene la IP local de la máquina de una forma más fiable.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No es necesario que la IP sea alcanzable, solo se usa para encontrar la interfaz
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'evento.settings')

    # --- CÓDIGO ADAPTADO PARA MOSTRAR IP CON HTTPS ---
    is_runserver = 'runserver' in sys.argv
    is_runserver_plus = 'runserver_plus' in sys.argv

    if is_runserver or is_runserver_plus:
        try:
            local_ip = get_local_ip()
            # Intenta adivinar el puerto de los argumentos, si no, usa 8000 por defecto
            port = '8000'
            for arg in sys.argv:
                if ':' in arg and arg.split(':')[-1].isdigit():
                    port = arg.split(':')[-1]
                    break
                elif arg.isdigit(): # Si el puerto se pasa como un argumento separado
                    port = arg
                    break

            # Determina si se usa HTTPS para mostrar el enlace correcto
            protocol = "https" if is_runserver_plus else "http"
            
            print("\n✅ ¡Servidor de desarrollo listo!")
            print(f"   ✓ Para acceder desde otros dispositivos, usa: {protocol}://{local_ip}:{port}/")
            print(f"   ✓ O localmente en tu computador:             {protocol}://127.0.0.1:{port}/")
            print("   (Presiona CTRL+C para detener)\n")

            # Si no se especifica una dirección, hace que el servidor sea accesible en la red
            address_provided = any(':' in arg or arg.replace('.', '').isdigit() for arg in sys.argv[2:] if not arg.startswith('-'))
            if not address_provided:
                cmd_index = sys.argv.index('runserver_plus' if is_runserver_plus else 'runserver')
                sys.argv.insert(cmd_index + 1, '0.0.0.0:8000')

        except Exception as e:
            print(f"\n⚠️  No se pudo obtener la IP local: {e}\n")
    # --- FIN DEL CÓDIGO ADAPTADO ---

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