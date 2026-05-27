#!/usr/bin/env python3
"""
Script de autorización OAuth2 — ejecutar UNA sola vez.

Pasos previos:
  1. Crear proyecto en https://console.cloud.google.com
  2. Habilitar Gmail API
  3. Crear credenciales OAuth 2.0 (tipo "Desktop app")
  4. Descargar el JSON y guardarlo como credentials.json en esta carpeta
  5. Correr: python setup_auth.py
"""

import sys
from pathlib import Path

# Agrega el directorio padre al path para poder importar gmail_client
sys.path.insert(0, str(Path(__file__).parent))

from gmail_client import CREDENTIALS_FILE, TOKEN_FILE, _resolve_path, get_gmail_service


def main():
    creds_path = _resolve_path(CREDENTIALS_FILE)
    token_path = _resolve_path(TOKEN_FILE)

    print("=== Setup Gmail OAuth2 ===\n")

    if not creds_path.exists():
        print(f"ERROR: No encontré {creds_path}")
        print("\nPasos para obtenerlo:")
        print("  1. Ir a https://console.cloud.google.com/apis/credentials")
        print("  2. Crear proyecto (o usar uno existente)")
        print("  3. Habilitar 'Gmail API' en APIs & Services > Library")
        print("  4. En Credentials > Create Credentials > OAuth client ID")
        print("     - Application type: Desktop app")
        print("     - Descargar el JSON")
        print(f"  5. Guardarlo como: {creds_path.resolve()}")
        print("\nLuego volvé a correr este script.")
        sys.exit(1)

    if token_path.exists():
        print(f"Ya existe {token_path} — si querés re-autorizar, borralo primero.")
        resp = input("¿Re-autorizar de todas formas? [s/N]: ").strip().lower()
        if resp != "s":
            print("Saliendo sin cambios.")
            return
        token_path.unlink()

    print("Abriendo el navegador para autorizar acceso a Gmail...")
    print("(si no abre automáticamente, copiá la URL que aparece en la terminal)\n")

    service = get_gmail_service()

    # Verificación rápida: obtiene el perfil del usuario
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "desconocido")
    total = profile.get("messagesTotal", 0)

    print(f"\n✓ Autorización exitosa!")
    print(f"  Cuenta: {email}")
    print(f"  Total de mensajes: {total:,}")
    print(f"  Token guardado en: {token_path.resolve()}")
    print("\nYa podés correr el agente con: python main.py")


if __name__ == "__main__":
    main()
