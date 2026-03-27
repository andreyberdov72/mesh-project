#!/usr/bin/env python3
"""
OTA-оновлення (sysupgrade) вузлів меш-мережі через SSH.

Скрипт підключається до кожної ноди по SSH (з ключами з configs/keys/),
завантажує відповідний sysupgrade.bin образ через SCP і запускає
`sysupgrade` на роутері. Ноди прошиваються паралельно.

Очікувана структура файлів:
    bin/<NODE>/*sysupgrade*.bin  – образи для прошивки
    configs/keys/<NODE>_id_rsa   – SSH приватні ключі

IP-адреси отримуються з topology.json через той самий алгоритм,
що й у generate_configs.py (детермінований, 10.0.0.X).

Залежності:
    pip install paramiko scp

Використання:
    python3 ota_upgrade.py [--topology topology.json] [--bin-dir ../openwrt-generator/bin]
                           [--keys-dir ../openwrt-generator/configs/keys]
                           [--subnet 10.0.0.] [--user root]
                           [--parallel] [--dry-run]
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("Помилка: встановіть залежності: pip install paramiko scp")
    sys.exit(1)

# --- Константи (збігаються з generate_configs.py) ---
IP_SUBNET = "10.0.0."
SSH_USER = "root"
SSH_PORT = 22
SSH_TIMEOUT = 30          # секунд на підключення
SYSUPGRADE_TIMEOUT = 180  # секунд на виконання sysupgrade


def assign_ips(nodes: list, subnet: str = IP_SUBNET) -> dict:
    """
    Детерміноване призначення IP-адрес — копія алгоритму з generate_configs.py.

    Args:
        nodes: Список словників із ключем ``id``.
        subnet: Префікс підмережі (наприклад, ``"10.0.0."``).

    Returns:
        Словник {node_id: ip_address}.
    """
    sorted_nodes = sorted(nodes, key=lambda n: n["id"])
    return {node["id"]: f"{subnet}{i + 1}" for i, node in enumerate(sorted_nodes)}


def find_sysupgrade(bin_dir: Path, node_id: str) -> Path | None:
    """
    Шукає *sysupgrade*.bin файл для вузла у папці bin/<node_id>/.

    Args:
        bin_dir: Шлях до кореневої папки bin/.
        node_id: Ідентифікатор вузла.

    Returns:
        Path до файлу або None, якщо не знайдено.
    """
    node_bin = bin_dir / node_id
    if not node_bin.is_dir():
        return None
    matches = list(node_bin.glob("*sysupgrade*.bin"))
    return matches[0] if matches else None


def upgrade_node(
    node_id: str,
    ip: str,
    firmware: Path,
    key_path: Path,
    user: str,
    dry_run: bool,
    results: dict,
) -> None:
    """
    Підключається до вузла по SSH, завантажує sysupgrade.bin та запускає оновлення.

    Кроки:
        1. SSH-підключення до ``user@ip`` з ключем ``key_path``.
        2. SCP копіювання образу до ``/tmp/sysupgrade.bin`` на роутері.
        3. Виконання ``sysupgrade -n /tmp/sysupgrade.bin`` (без збереження конфігу).

    Args:
        node_id: Ідентифікатор вузла (для логів).
        ip: IP-адреса вузла.
        firmware: Локальний шлях до sysupgrade.bin.
        key_path: Шлях до приватного SSH-ключа.
        user: Ім'я користувача SSH (зазвичай ``root``).
        dry_run: Якщо True — друкує команди, але не виконує.
        results: Спільний словник для запису результату потоку.
    """
    tag = f"[{node_id} / {ip}]"
    fw_size_mb = firmware.stat().st_size / 1024 / 1024

    if dry_run:
        print(f"{tag} [DRY-RUN] scp {firmware} -> /tmp/sysupgrade.bin")
        print(f"{tag} [DRY-RUN] sysupgrade -n /tmp/sysupgrade.bin")
        results[node_id] = "dry-run"
        return

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"{tag} Підключення...")
        client.connect(
            hostname=ip,
            port=SSH_PORT,
            username=user,
            key_filename=str(key_path),
            timeout=SSH_TIMEOUT,
            look_for_keys=False,
            allow_agent=False,
        )
        print(f"{tag} Підключено. Завантаження образу ({fw_size_mb:.1f} MB)...")

        # SCP upload
        with SCPClient(client.get_transport(), progress=_scp_progress(tag)) as scp:
            scp.put(str(firmware), remote_path="/tmp/sysupgrade.bin")

        print(f"\n{tag} Образ завантажено. Запуск sysupgrade...")

        # sysupgrade -n = без збереження конфіг
        # Виклик не чекає відповіді (роутер одразу ребутається)
        stdin, stdout, stderr = client.exec_command(
            "sysupgrade -n /tmp/sysupgrade.bin",
            timeout=SYSUPGRADE_TIMEOUT,
            get_pty=False,
        )

        # Чекаємо трохи — після старту sysupgrade ssh-з'єднання впаде
        try:
            out = stdout.read(1024).decode(errors="replace")
            err = stderr.read(1024).decode(errors="replace")
            if out:
                print(f"{tag} stdout: {out.strip()}")
            if err:
                print(f"{tag} stderr: {err.strip()}")
        except Exception:
            pass  # очікувано: з'єднання обривається під час прошивки

        print(f"{tag} ✓ sysupgrade запущено — роутер перезавантажується")
        results[node_id] = "ok"

    except paramiko.AuthenticationException:
        msg = f"Помилка автентифікації. Перевірте ключ: {key_path}"
        print(f"{tag} ✗ {msg}")
        results[node_id] = f"error: {msg}"
    except (paramiko.SSHException, OSError, TimeoutError) as exc:
        msg = str(exc)
        print(f"{tag} ✗ Помилка підключення: {msg}")
        results[node_id] = f"error: {msg}"
    finally:
        client.close()


def _scp_progress(tag: str):
    """Повертає callback для відображення прогресу SCP."""
    last = [0]

    def progress(filename, size, sent):
        pct = int(sent / size * 100) if size else 0
        if pct != last[0] and pct % 10 == 0:
            print(f"\r{tag} Завантаження: {pct}%", end="", flush=True)
            last[0] = pct

    return progress


def parse_args():
    """Парсить аргументи командного рядка."""
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent

    parser = argparse.ArgumentParser(
        description="OTA sysupgrade для вузлів меш-мережі через SSH"
    )
    parser.add_argument(
        "--topology",
        default=str(project_root / "openwrt-generator" / "topology.json"),
        help="Шлях до topology.json (за замовч.: ../openwrt-generator/topology.json)",
    )
    parser.add_argument(
        "--bin-dir",
        default=str(project_root / "openwrt-generator" / "bin"),
        help="Папка з bin/<NODE>/*sysupgrade*.bin (за замовч.: ../openwrt-generator/bin)",
    )
    parser.add_argument(
        "--keys-dir",
        default=str(project_root / "openwrt-generator" / "configs" / "keys"),
        help="Папка з SSH-ключами <NODE>_id_rsa (за замовч.: ../openwrt-generator/configs/keys)",
    )
    parser.add_argument(
        "--subnet",
        default=IP_SUBNET,
        help=f"Префікс IP-підмережі (за замовч.: {IP_SUBNET})",
    )
    parser.add_argument(
        "--user",
        default=SSH_USER,
        help=f"Користувач SSH (за замовч.: {SSH_USER})",
    )
    parser.add_argument(
        "--nodes",
        nargs="+",
        metavar="NODE_ID",
        help="Прошити тільки вказані вузли (напр.: --nodes A1 B2). За замовч. — всі.",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Прошивати всі вузли паралельно (за замовч. — послідовно)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показати що буде зроблено, не виконуючи реальних команд",
    )
    return parser.parse_args()


def main():
    """
    Головна функція: читає топологію, знаходить образи та ключі,
    запускає прошивку вузлів (послідовно або паралельно).
    """
    args = parse_args()

    topology_path = Path(args.topology)
    bin_dir = Path(args.bin_dir)
    keys_dir = Path(args.keys_dir)

    # --- Читаємо топологію ---
    if not topology_path.exists():
        print(f"Помилка: topology.json не знайдено: {topology_path}")
        sys.exit(1)

    with open(topology_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = data["nodes"]
    ip_map = assign_ips(nodes, args.subnet)

    # --- Фільтруємо вузли якщо передано --nodes ---
    if args.nodes:
        unknown = set(args.nodes) - set(ip_map.keys())
        if unknown:
            print(f"Попередження: невідомі вузли: {', '.join(unknown)}")
        target_ids = [n for n in sorted(ip_map.keys()) if n in args.nodes]
    else:
        target_ids = sorted(ip_map.keys())

    if not target_ids:
        print("Немає вузлів для прошивки.")
        sys.exit(1)

    # --- Перевіряємо наявність образів та ключів ---
    tasks = []
    skipped = []
    for node_id in target_ids:
        ip = ip_map[node_id]
        firmware = find_sysupgrade(bin_dir, node_id)
        key_path = keys_dir / f"{node_id}_id_rsa"

        missing = []
        if firmware is None:
            missing.append(f"sysupgrade.bin не знайдено в {bin_dir / node_id}/")
        if not key_path.exists():
            missing.append(f"SSH-ключ не знайдено: {key_path}")

        if missing:
            for m in missing:
                print(f"[{node_id}] ✗ Пропуск: {m}")
            skipped.append(node_id)
            continue

        tasks.append((node_id, ip, firmware, key_path))

    if not tasks:
        print("Немає вузлів для прошивки після перевірки. Виходимо.")
        sys.exit(1)

    # --- Підсумок перед запуском ---
    print(f"\n{'='*55}")
    print(f"  OTA sysupgrade: {len(tasks)} вузлів"
          + (" [DRY-RUN]" if args.dry_run else "")
          + (" [ПАРАЛЕЛЬНО]" if args.parallel else " [послідовно]"))
    print(f"{'='*55}")
    for node_id, ip, firmware, key_path in tasks:
        print(f"  {node_id:6s}  {ip:15s}  {firmware.name}")
    if skipped:
        print(f"\n  Пропущено: {', '.join(skipped)}")
    print(f"{'='*55}\n")

    if not args.dry_run:
        confirm = input("Продовжити? [y/N] ").strip().lower()
        if confirm != "y":
            print("Скасовано.")
            sys.exit(0)

    # --- Запуск прошивки ---
    results = {}
    start = time.time()

    if args.parallel:
        threads = []
        for node_id, ip, firmware, key_path in tasks:
            t = threading.Thread(
                target=upgrade_node,
                args=(node_id, ip, firmware, key_path, args.user, args.dry_run, results),
                name=node_id,
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    else:
        for node_id, ip, firmware, key_path in tasks:
            upgrade_node(node_id, ip, firmware, key_path, args.user, args.dry_run, results)

    # --- Підсумок ---
    elapsed = time.time() - start
    ok = [n for n, r in results.items() if r in ("ok", "dry-run")]
    failed = [n for n, r in results.items() if r not in ("ok", "dry-run")]

    print(f"\n{'='*55}")
    print(f"  Результат за {elapsed:.1f}с")
    print(f"  ✓ Успішно: {len(ok)}   ✗ Помилок: {len(failed)}")
    if failed:
        for n in failed:
            print(f"    {n}: {results[n]}")
    print(f"{'='*55}")
    print("\n⚠️  Зачекайте ~2 хвилини, доки всі вузли перезавантажаться.")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
