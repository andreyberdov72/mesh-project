# Розгортання у виробничому середовищі

Цей документ призначений для Release Engineer або DevOps-інженера, що відповідає за розгортання mesh-мережі на об'єкті.

---

## 1. Вимоги до апаратного забезпечення

### Машина оператора (ПК/ноутбук, де запускаються скрипти)

| Параметр | Мінімум | Рекомендовано |
|----------|---------|---------------|
| Архітектура | x86_64 | x86_64 |
| CPU | 2 ядра, 1.5 GHz | 4 ядра, 2.0 GHz |
| RAM | 2 GB | 4 GB |
| Диск | 10 GB (для ImageBuilder ~2–3 GB) | 20 GB SSD |
| ОС | Ubuntu 20.04 LTS+ / Debian 11+ | Ubuntu 22.04 LTS |
| Мережа | 1x LAN-порт (Ethernet) | 1x LAN-порт |

### Роутери (цільові пристрої)

Підтримуваний пристрій: **TP-Link TL-WR840N v4**

| Параметр | Значення |
|----------|----------|
| Чіп | MediaTek MT7628 (MIPS 24KEc) |
| RAM | 64 MB |
| Flash | 8 MB |
| Wi-Fi | 2.4 GHz 802.11n |
| LAN | 4x 100 Mbps |
| WAN | 1x 100 Mbps |
| Прошивка | OpenWrt 25.12.1 (ramips/mt76x8) |

---

## 2. Необхідне програмне забезпечення

### На машині оператора

```bash
sudo apt update && sudo apt install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    openssh-client \
    make \
    curl \
    net-tools \
    iproute2
```

### Python-залежності

```bash
python3 -m venv myvenv
source myvenv/bin/activate
pip install jinja2
```

### OpenWrt ImageBuilder

ImageBuilder завантажується з офіційного дзеркала OpenWrt і розпаковується в директорію `openwrt-generator/`:

```bash
cd openwrt-generator/
wget https://downloads.openwrt.org/releases/25.12.1/targets/ramips/mt76x8/openwrt-imagebuilder-25.12.1-ramips-mt76x8.Linux-x86_64.tar.zst
tar --zstd -xf openwrt-imagebuilder-25.12.1-ramips-mt76x8.Linux-x86_64.tar.zst
```

ImageBuilder потребує додаткових системних пакетів:

```bash
sudo apt install -y \
    build-essential \
    libncurses5-dev \
    libncursesw5-dev \
    zlib1g-dev \
    gawk \
    gettext \
    unzip \
    file \
    wget \
    python3-distutils
```

---

## 3. Налаштування мережі

### Підключення для прошивки

Роутер у режимі Recovery очікує TFTP-сервер за адресою **192.168.0.66** на порту **69**.

1. Підключіть ноутбук до **будь-якого LAN-порту** роутера кабелем Ethernet.
2. Налаштуйте статичний IP на інтерфейсі (замініть `eth0` на вашу назву):

```bash
# Знайти назву інтерфейсу
ip link show

# Налаштувати статичну адресу
sudo ip addr add 192.168.0.66/24 dev eth0
sudo ip link set eth0 up
```

3. Перевірте, що адреса встановлена:

```bash
ip addr show eth0
```

> ⚠️ **Важливо:** Ця адреса має бути налаштована **до** запуску `flasher.py` і **до** переведення роутера у режим Recovery.

### Переведення роутера в режим Recovery (TFTP boot)

1. Утримуйте кнопку **Reset** на роутері
2. Увімкніть роутер, тримаючи Reset ще ~5 секунд
3. Відпустіть кнопку — роутер перейде у режим Recovery і почне шукати TFTP-сервер

---

## 4. Конфігурація серверів

### Файл топології

Перед розгортанням підготуйте `topology.json` у форматі:

```json
{
  "nodes": [
    {"id": "A1", "x": 100, "y": 100},
    {"id": "B1", "x": 300, "y": 100}
  ],
  "links": [
    {"source": "A1", "target": "B1", "color": "#4CAF50"}
  ]
}
```

- `color: "blue"` — дротовий (Ethernet) зв'язок
- `color: "#4CAF50"` — бездротовий (Wi-Fi mesh 802.11s) зв'язок

Приклади топологій знаходяться у `topologies/`.

### Параметри генератора

Відредагуйте константи у `openwrt-generator/generate_configs.py` за потреби:

```python
IP_SUBNET = "10.0.0."       # Підмережа для mesh-вузлів
WIFI_CHANNEL = 6             # Канал Wi-Fi (1–13)
PROFILE = "tplink_tl-wr840n-v4"   # Профіль пристрою для ImageBuilder
PACKAGES = "batctl kmod-batman-adv ..."  # Пакети OpenWrt
```

---

## 5. Налаштування СУБД

Проект **не використовує** реляційну базу даних. Стан мережі зберігається у файлах:

| Файл/Папка | Призначення |
|-----------|-------------|
| `topology.json` | Опис топології мережі (вхідні дані) |
| `configs/` | Згенеровані UCI-конфіги для кожної ноди |
| `configs/keys/` | RSA-ключі для SSH-доступу до вузлів |
| `bin/` | Скомпільовані `.bin` образи прошивок |

> 🔒 **Безпека:** Папка `configs/keys/` містить приватні SSH-ключі. Після розгортання зберігайте їх у захищеному місці (наприклад, KeePass, HashiCorp Vault або зашифрований архів).

---

## 6. Розгортання коду

### Крок 1: Клонування та підготовка

```bash
git clone https://github.com/andreyberdov72/mesh-project.git
cd mesh-project
python3 -m venv myvenv
source myvenv/bin/activate
pip install jinja2
```

### Крок 2: Завантаження ImageBuilder

```bash
cd openwrt-generator/
wget https://downloads.openwrt.org/releases/25.12.1/targets/ramips/mt76x8/openwrt-imagebuilder-25.12.1-ramips-mt76x8.Linux-x86_64.tar.zst
tar --zstd -xf openwrt-imagebuilder-25.12.1-ramips-mt76x8.Linux-x86_64.tar.zst
```

### Крок 3: Підготовка топології

```bash
# Скопіюйте або відредагуйте файл топології
cp ../topologies/nodes.json topology.json
# або відредагуйте topology.json вручну
```

### Крок 4: Генерація конфігурацій та збірка прошивок

```bash
# Тільки конфіги (без збірки)
python3 generate_configs.py

# Повна збірка прошивок (займає 10–30 хв залежно від кількості вузлів)
python3 generate_configs.py --build
```

Очікуваний вивід:
```
Generated configs for A1
Generated configs for B1
...
Mesh network parameters:
A1 ↔ B1: mesh_id=mesh-A1-B1, key=258577f4cc1a59ad270a437076d83e4e
Building image for A1...
Built image for A1 in bin/A1
```

### Крок 5: Масова прошивка роутерів

```bash
cd ../bulk-flasher

# Налаштуйте мережевий інтерфейс (один раз)
sudo ip addr add 192.168.0.66/24 dev eth0

# Запустіть прошивальник
sudo python3 flasher.py ../openwrt-generator/bin
```

Скрипт:
1. Запустить TFTP-сервер на `0.0.0.0:69`
2. Для кожного вузла (в алфавітному порядку) покладе прошивку як `tp_recovery.bin`
3. Чекатиме на натискання `Enter` — підключайте наступний роутер після завершення прошивки

---

## 7. Перевірка працездатності

### Перевірка після прошивки кожного вузла

Після прошивки роутер перезавантажується. Підключіться до нього через SSH:

```bash
# Знайдіть IP вузла (з configs/keys/ — назва ключа відповідає вузлу)
# Наприклад, для вузла A1:
ssh -i ../openwrt-generator/configs/keys/A1_id_rsa root@10.0.0.1
```

### Перевірка mesh-мережі (batman-adv)

На вузлі після підключення через SSH:

```bash
# Статус batman-adv
batctl meshif bat0 n          # Список сусідів (neighbors)
batctl meshif bat0 tg         # Таблиця маршрутизації (translation table)
batctl meshif bat0 if         # Активні інтерфейси

# Пінг між вузлами
ping 10.0.0.2                 # Пінг сусіднього вузла (B1)
```

### Очікуваний стан системи

| Перевірка | Очікуваний результат |
|-----------|---------------------|
| `batctl meshif bat0 n` | Показує сусідні вузли з якістю зв'язку |
| `ip addr show bat0` | Показує статичну IP-адресу ноди |
| `ip addr show wlan0` | Wi-Fi інтерфейс активний |
| `ssh root@<node-ip>` | Вхід лише за ключем, без пароля |
| `ping <сусід-ip>` | RTT < 10 ms для вузлів у прямій видимості |

### Типові проблеми та рішення

| Проблема | Причина | Рішення |
|----------|---------|---------|
| TFTP-сервер не підключається | Неправильна IP-адреса інтерфейсу | Перевірте `ip addr show eth0` |
| Роутер не знаходить TFTP | Роутер не в режимі Recovery | Повторіть процедуру з кнопкою Reset |
| SSH-вхід відхилено | Ключ не збігається або відсутній | Перевірте `configs/keys/<node>_id_rsa.pub` vs `authorized_keys` на роутері |
| batman-adv не бачить сусідів | Wi-Fi канали не збігаються | Перевірте `WIFI_CHANNEL` у `generate_configs.py` — має бути однаковим |
| Немає пінгу між вузлами | Mesh-ключі не збігаються | Переконайтесь, що обидва вузли згенеровані з одного `topology.json` |
