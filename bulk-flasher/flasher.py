#!/usr/bin/env python3
"""
Прошивка роутерів TP-Link TL-WR840N v4 через TFTP з використанням tftp-now.
Сервер запускається один раз на всіх інтерфейсах (0.0.0.0:69).
Прошивки: папка ../openwrt-generator/bin/<node>/*tftp-recovery*.bin
"""

import os
import sys
import time
import subprocess
import tempfile
import shutil
from pathlib import Path


def main():
    # Шлях до tftp-now (поруч зі скриптом)
    script_dir = Path(__file__).parent.resolve()
    tftp_now = script_dir / "tftp-now"
    if not tftp_now.exists():
        print(f"Помилка: tftp-now не знайдено за шляхом {tftp_now}")
        sys.exit(1)
    if not os.access(tftp_now, os.X_OK):
        print(f"Помилка: tftp-now не виконуваний. Виконайте chmod +x {tftp_now}")
        sys.exit(1)

    # Папка з прошивками
    if len(sys.argv) > 1:
        bin_dir = Path(sys.argv[1]).resolve()
    else:
        bin_dir = script_dir.parent / "openwrt-generator" / "bin"
    if not bin_dir.is_dir():
        print(f"Папку з прошивками не знайдено: {bin_dir}")
        print("Вкажіть шлях до папки bin першим аргументом.")
        sys.exit(1)

    # Тимчасова папка в /tmp
    tftp_root = Path(tempfile.mkdtemp(prefix="tftp_bulk_"))
    print(f"Тимчасова папка TFTP: {tftp_root}")

    # Збираємо вузли
    nodes = [p for p in bin_dir.iterdir() if p.is_dir() and p.name != "keys"]
    if not nodes:
        print("У папці bin немає підпапок з вузлами.")
        sys.exit(1)

    print("Роутер шукатиме сервер за адресою 192.168.0.66:69. "
          "Переконайтеся, що інтерфейс має цю IP-адресу.\n")
    print(f"Знайдено вузлів: {len(nodes)}")

    # Оновлюємо sudo, щоб пароль запитався один раз
    try:
        subprocess.run(["sudo", "-v"], check=True)
    except subprocess.CalledProcessError:
        print("Не вдалося отримати права sudo. Переконайтеся, що sudo доступний.")
        sys.exit(1)

    server_proc = None
    try:
        # Запускаємо сервер один раз на всіх адресах
        cmd = ["sudo", str(tftp_now), "serve", "-root", str(tftp_root), "-verbose"]
        server_proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
        print(f"TFTP-сервер запущено (PID {server_proc.pid}) на порту 69")
        time.sleep(2)

        for node_dir in nodes:
            node = node_dir.name
            # Шукаємо файл з tftp-recovery
            firmwares = list(node_dir.glob("*tftp-recovery*.bin"))
            if not firmwares:
                print(f"Немає файлу з tftp-recovery для вузла {node}, пропускаємо")
                continue
            firmware_file = firmwares[0]
            print(f"\n=== Прошивка вузла {node} ===")
            print(f"Файл: {firmware_file.name}")

            # Копіюємо як tp_recovery.bin
            recovery_path = tftp_root / "tp_recovery.bin"
            recovery_path.write_bytes(firmware_file.read_bytes())
            print(f"Скопійовано в {recovery_path}")

            input("Під'єднайте роутер через LAN, натисніть Reset, увімкніть, "
                  "дочекайтеся блимання, після перезавантаження натисніть Enter\n")
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    # Видаляємо тимчасову папку
    shutil.rmtree(tftp_root, ignore_errors=True)
    print("\nУсі прошивки завантажено.")


if __name__ == "__main__":
    main()
