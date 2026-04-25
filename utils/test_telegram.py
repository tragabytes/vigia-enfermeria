#!/usr/bin/env python3
"""
Envía un mensaje de prueba a Telegram para validar credenciales.

Uso:
    TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python utils/test_telegram.py

Si el mensaje llega, las credenciales son correctas y puedes continuar.
"""
import sys
import os
import io

# Permite ejecutar desde la raíz del repo sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Forzar UTF-8 en stdout/stderr para que los emojis no rompan en Windows cp1252
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from vigia.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from vigia.notifier import send_test


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: variable de entorno TELEGRAM_BOT_TOKEN no definida")
        sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        print("ERROR: variable de entorno TELEGRAM_CHAT_ID no definida")
        sys.exit(1)

    print(f"Token: ...{TELEGRAM_BOT_TOKEN[-6:]}")
    print(f"Chat ID: {TELEGRAM_CHAT_ID}")
    print("Enviando mensaje de prueba...")

    try:
        send_test("✅ *vigia-enfermeria* — conexión Telegram OK\nSi ves este mensaje, las credenciales funcionan correctamente.")
        print("✅ Mensaje enviado. Comprueba tu Telegram.")
    except Exception as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
