#!/usr/bin/env python3
import json
import os
import sys
import hashlib
import subprocess
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
PACKAGES = "batctl kmod-batman-adv dropbear wpad-mesh-wolfssl -wpad-basic-mbedtls -dnsmasq -odhcpd -odhcp6c -ppp -ppp-mod-pppoe"

# ------------------------------------------------------------
# Functions
# ------------------------------------------------------------
def generate_mesh_key(node1, node2):
    salt = "openwrt_mesh"
    return hashlib.sha256(f"{node1}{node2}{salt}".encode()).hexdigest()[:32]

def assign_ips(nodes):
    sorted_nodes = sorted(nodes, key=lambda n: n["id"])
    return {node["id"]: f"{IP_SUBNET}{i+1}" for i, node in enumerate(sorted_nodes)}

def build_ethernet_ports(nodes, links):
    eth_links = [l for l in links if l["color"] == "blue"]
    graph = defaultdict(list)
    for link in eth_links:
        graph[link["source"]].append(link["target"])
        graph[link["target"]].append(link["source"])
    
    node_ports = {}
    for node in nodes:
        node_id = node["id"]
        neighbors = graph.get(node_id, [])
        active_ports = list(range(1, len(neighbors)+1))
        node_ports[node_id] = active_ports
    return node_ports

def build_wifi_mesh_links(links):
    wifi_links = [l for l in links if l["color"] == "#4CAF50"]
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
        subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", priv_key, "-N", "", "-q"], check=True)
    with open(pub_key, 'r') as f:
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
# Main func
# ------------------------------------------------------------
def main():
    with open("topology.json", "r") as f:
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
        import shutil
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
        network_conf = templates["network"].render(active_ports=active_ports, ip=ip)
        with open(os.path.join(node_dir, "network"), "w") as f:
            f.write(network_conf)

        # Wireless
        wireless_conf = templates["wireless"].render(
            channel=WIFI_CHANNEL,
            mesh_id=mesh["mesh_id"],
            mesh_key=mesh["mesh_key"]
        )
        with open(os.path.join(node_dir, "wireless"), "w") as f:
            f.write(wireless_conf)

        # Batman-adv
        batman_conf = templates["batman-adv"].render()
        with open(os.path.join(node_dir, "batman-adv"), "w") as f:
            f.write(batman_conf)

        # Firewall
        firewall_conf = templates["firewall"].render()
        with open(os.path.join(node_dir, "firewall"), "w") as f:
            f.write(firewall_conf)

        # System
        system_conf = templates["system"].render(hostname=node_id)
        with open(os.path.join(node_dir, "system"), "w") as f:
            f.write(system_conf)

        # Dropbear
        dropbear_conf = templates["dropbear"].render()
        with open(os.path.join(node_dir, "dropbear"), "w") as f:
            f.write(dropbear_conf)

        # Authorized keys
        pub_key = generate_ssh_keys(node_id, OUTPUT_DIR)
        auth_keys_dir = os.path.join(OUTPUT_DIR, node_id, "etc", "dropbear")
        os.makedirs(auth_keys_dir, exist_ok=True)
        with open(os.path.join(auth_keys_dir, "authorized_keys"), "w") as f:
            f.write(pub_key + "\n")

        print(f"Generated configs for {node_id}")

    print("\nMesh network parameters:")
    for link in [l for l in links if l["color"] == "#4CAF50"]:
        mesh_id = f"mesh-{link['source']}-{link['target']}"
        mesh_key = generate_mesh_key(link["source"], link["target"])
        print(f"{link['source']} ↔ {link['target']}: mesh_id={mesh_id}, key={mesh_key}")

    if "--build" in sys.argv:
        build_images(IMAGE_BUILDER_DIR, OUTPUT_DIR)

if __name__ == "__main__":
    main()
