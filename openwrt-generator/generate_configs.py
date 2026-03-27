#!/usr/bin/env python3
import json
import os
import sys
import hashlib
import subprocess
import shutil
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
OUTPUT_DIR = "configs"
IP_SUBNET = "10.0.0."
WIFI_CHANNEL = 6
IMAGE_BUILDER_DIR = "./openwrt-imagebuilder-25.12.1-ramips-mt76x8.Linux-x86_64"
PROFILE = "tplink_tl-wr840n-v4"
PACKAGES = (
    "batctl kmod-batman-adv dropbear wpad-mesh-wolfssl -wpad-basic-mbedtls "
    "-dnsmasq -odhcpd -odhcp6c -ppp -ppp-mod-pppoe"
)

# ------------------------------------------------------------
# Functions
# ------------------------------------------------------------
def generate_mesh_key(node1: str, node2: str) -> str:
    """
    Генерує унікальний ключ шифрування для mesh-з'єднання між двома вузлами.

    Ключ створюється на основі імен вузлів та фіксованої солі, щоб забезпечити
    детерміноване, але унікальне значення для кожної пари.

    Args:
        node1: Ідентифікатор першого вузла (наприклад, "A1").
        node2: Ідентифікатор другого вузла.

    Returns:
        Рядок із 32 шістнадцятковими символами — ключ PSK для 802.11s.

    Example:
        >>> generate_mesh_key("A1", "B1")
        '258577f4cc1a59ad270a437076d83e4e'
    """
    salt = "openwrt_mesh"
    return hashlib.sha256(f"{node1}{node2}{salt}".encode()).hexdigest()[:32]


def assign_ips(nodes):
    """
    Призначає статичні IP-адреси вузлам на основі їхнього ідентифікатора.

    Адреси призначаються послідовно (починаючи з X.X.X.1) після сортування
    вузлів за їхнім ідентифікатором за алфавітом. Це гарантує детермінованість
    розподілу адрес при повторних запусках генератора.

    Args:
        nodes: Список словників із даними про вузли, де обов'язковим є ключ "id".

    Returns:
        Словник, де ключ — ідентифікатор вузла, а значення — його статична IP-адреса.

    Example:
        >>> nodes = [{"id": "NodeB"}, {"id": "NodeA"}]
        >>> assign_ips(nodes)
        {'NodeA': '10.0.0.1', 'NodeB': '10.0.0.2'}
    """
    sorted_nodes = sorted(nodes, key=lambda n: n["id"])
    return {node["id"]: f"{IP_SUBNET}{i+1}" for i, node in enumerate(sorted_nodes)}


def build_ethernet_ports(nodes, links):
    """
    Визначає, які Ethernet-порти потрібно активувати на кожному вузлі,
    ґрунтуючись на топології синіх (дротових) зв'язків.

    Args:
        nodes: Список словників із даними про вузли (ключ "id").
        links: Список словників зв'язків (ключі "source", "target", "color").

    Returns:
        Словник, де ключ — id вузла, значення — список номерів портів,
        які треба активувати (нумерація з 1). Якщо вузол не має дротових сусідів,
        повертає порожній список.

    Example:
        >>> nodes = [{"id": "A1"}, {"id": "A2"}]
        >>> links = [{"source": "A1", "target": "A2", "color": "blue"}]
        >>> build_ethernet_ports(nodes, links)
        {'A1': [1], 'A2': [1]}
    """
    eth_links = [link for link in links if link["color"] == "blue"]
    graph = defaultdict(list)
    for link in eth_links:
        graph[link["source"]].append(link["target"])
        graph[link["target"]].append(link["source"])

    node_ports = {}
    for node in nodes:
        node_id = node["id"]
        neighbors = graph.get(node_id, [])
        active_ports = list(range(1, len(neighbors) + 1))
        node_ports[node_id] = active_ports
    return node_ports


def build_wifi_mesh_links(links):
    """
    Аналізує зелені (безпровідні) зв'язки графа топології та генерує
    ідентифікатори і ключі шифрування для 802.11s mesh-мереж.

    Args:
        links: Список словників зв'язків з топології (з ключами "source", "target", "color").

    Returns:
        Словник, де ключ — ідентифікатор вузла, а значення — словник
        з 'mesh_id' та 'mesh_key' для його Wi-Fi інтерфейсу.

    Example:
        >>> links = [{"source": "A", "target": "B", "color": "#4CAF50"}]
        >>> build_wifi_mesh_links(links)
        {'A': {'mesh_id': 'mesh-A-B', 'mesh_key': '8d78b5ee6d2c905261337fc22767b6a4'}, 'B': {'mesh_id': 'mesh-A-B', 'mesh_key': '8d78b5ee6d2c905261337fc22767b6a4'}}
    """
    wifi_links = [link for link in links if link["color"] == "#4CAF50"]
    node_mesh = {}
    for link in wifi_links:
        src, tgt = link["source"], link["target"]
        mesh_id = f"mesh-{src}-{tgt}"
        mesh_key = generate_mesh_key(src, tgt)
        node_mesh[src] = {"mesh_id": mesh_id, "mesh_key": mesh_key}
        node_mesh[tgt] = {"mesh_id": mesh_id, "mesh_key": mesh_key}
    return node_mesh


def generate_ssh_keys(node_id, output_dir):
    key_dir = os.path.join(output_dir, "keys")
    os.makedirs(key_dir, exist_ok=True)
    priv_key = os.path.join(key_dir, f"{node_id}_id_rsa")
    pub_key = f"{priv_key}.pub"
    if not os.path.exists(priv_key):
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", priv_key, "-N", "", "-q"],
            check=True
        )
    with open(pub_key, 'r', encoding='utf-8') as f:
        pub = f.read().strip()
    return pub


def build_images(image_builder_dir, output_dir):
    if not os.path.isdir(image_builder_dir):
        print(f"Image builder directory {image_builder_dir} not found. Skipping build.")
        return
    project_root = os.path.dirname(os.path.abspath(__file__))
    bin_root = os.path.join(project_root, "bin")
    os.makedirs(bin_root, exist_ok=True)
    for node_id in os.listdir(output_dir):
        node_path = os.path.join(output_dir, node_id)
        if not os.path.isdir(node_path) or node_id == "keys":
            continue
        bin_dir = os.path.join(bin_root, node_id)
        os.makedirs(bin_dir, exist_ok=True)
        cmd = [
            "make", "image",
            f"PROFILE={PROFILE}",
            f"PACKAGES={PACKAGES}",
            f"FILES={node_path}",
            f"BIN_DIR={bin_dir}"
        ]
        print(f"Building image for {node_id}...")
        subprocess.run(cmd, cwd=image_builder_dir, check=True)
        for f in os.listdir(bin_dir):
            if f.endswith('.bin'):
                base, ext = os.path.splitext(f)
                new_name = f"{base}-{node_id}{ext}"
                os.rename(os.path.join(bin_dir, f), os.path.join(bin_dir, new_name))
                print(f"  Renamed {f} -> {new_name}")
        print(f"Built image for {node_id} in {bin_dir}")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def render_config_file(template, path, **kwargs):
    """Helper to render a template and write to a file."""
    content = template.render(**kwargs)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    with open("topology.json", "r", encoding='utf-8') as f:
        data = json.load(f)
    nodes = data["nodes"]
    links = data["links"]

    ip_map = assign_ips(nodes)
    ethernet_ports = build_ethernet_ports(nodes, links)
    wifi_mesh = build_wifi_mesh_links(links)

    env = Environment(loader=FileSystemLoader("templates"))
    templates = {
        "network": env.get_template("network.j2"),
        "wireless": env.get_template("wireless.j2"),
        "batman-adv": env.get_template("batman-adv.j2"),
        "firewall": env.get_template("firewall.j2"),
        "system": env.get_template("system.j2"),
        "dropbear": env.get_template("dropbear.j2"),
    }

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    for node in nodes:
        node_id = node["id"]
        ip = ip_map[node_id]
        active_ports = ethernet_ports.get(node_id, [])
        mesh = wifi_mesh.get(node_id)
        if not mesh:
            print(f"Warning: {node_id} has no Wi-Fi link. Skipping.")
            continue

        node_dir = os.path.join(OUTPUT_DIR, node_id, "etc", "config")
        os.makedirs(node_dir, exist_ok=True)

        # Network
        render_config_file(
            templates["network"],
            os.path.join(node_dir, "network"),
            active_ports=active_ports,
            ip=ip
        )

        # Wireless
        render_config_file(
            templates["wireless"],
            os.path.join(node_dir, "wireless"),
            channel=WIFI_CHANNEL,
            mesh_id=mesh["mesh_id"],
            mesh_key=mesh["mesh_key"]
        )

        # Batman-adv
        render_config_file(
            templates["batman-adv"],
            os.path.join(node_dir, "batman-adv")
        )

        # Firewall
        render_config_file(
            templates["firewall"],
            os.path.join(node_dir, "firewall")
        )

        # System
        render_config_file(
            templates["system"],
            os.path.join(node_dir, "system"),
            hostname=node_id
        )

        # Dropbear
        render_config_file(
            templates["dropbear"],
            os.path.join(node_dir, "dropbear")
        )

        # Authorized keys
        pub_key = generate_ssh_keys(node_id, OUTPUT_DIR)
        auth_keys_dir = os.path.join(OUTPUT_DIR, node_id, "etc", "dropbear")
        os.makedirs(auth_keys_dir, exist_ok=True)
        with open(os.path.join(auth_keys_dir, "authorized_keys"), 'w', encoding='utf-8') as f:
            f.write(pub_key + "\n")

        print(f"Generated configs for {node_id}")

    print("\nMesh network parameters:")
    for link in [link for link in links if link["color"] == "#4CAF50"]:
        mesh_id = f"mesh-{link['source']}-{link['target']}"
        mesh_key = generate_mesh_key(link["source"], link["target"])
        print(f"{link['source']} ↔ {link['target']}: mesh_id={mesh_id}, key={mesh_key}")

    if "--build" in sys.argv:
        build_images(IMAGE_BUILDER_DIR, OUTPUT_DIR)


if __name__ == "__main__":
    main()
