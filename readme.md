# Засоби побудови меш-мережі на базі старих роутерів

[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://andreyberdov72.github.io/mesh-project/)

Цей репозиторій містить скрипти для генерації прошивок з заздалегідь вбудованою конфігурацією залежно від позиції ноди, а також скрипт для напівавтоматичної прошивки.

📖 **Повна документація доступна тут:** [https://andreyberdov72.github.io/mesh-project/](https://andreyberdov72.github.io/mesh-project/)

---

## 🚀 Швидкий старт для розробника

Ця інструкція розрахована на розробника зі свіжо встановленою ОС (Ubuntu/Debian).

### 1. Встановлення системних залежностей

```bash
sudo apt update && sudo apt install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    openssh-client \
    make
```

### 2. Клонування репозиторію

```bash
git clone https://github.com/andreyberdov72/mesh-project.git
cd mesh-project
```

### 3. Налаштування віртуального середовища Python

```bash
# Створення venv
python3 -m venv myvenv

# Активація (Linux/macOS)
source myvenv/bin/activate

# Встановлення залежностей для документації
pip install -r docs/requirements.txt

# Встановлення залежностей для скриптів
pip install jinja2
```

> **Примітка:** Залежності для скриптів — лише `jinja2`. Усі інші бібліотеки (`hashlib`, `subprocess`, `json` тощо) — стандартні і входять у Python 3.

### 4. Перевірка коректності встановлення

```bash
# Запустіть doctest-тести (всі мають пройти)
cd docs
make doctest SPHINXBUILD=../myvenv/bin/sphinx-build
cd ..
```

### 5. Запуск генератора конфігурацій

```bash
cd openwrt-generator

# Переконайтесь, що файл топології є (за замовчуванням — topology.json)
ls topology.json

# Запуск генерації конфігурацій для кожної ноди
python3 generate_configs.py

# Результат буде у папці configs/
ls configs/
```

Для генерації прошивок (потребує завантаженого OpenWrt ImageBuilder):
```bash
python3 generate_configs.py --build
```

### 6. Запуск bulk-flasher

```bash
cd ../bulk-flasher

# Переконайтесь, що бінарники зібрані
ls ../openwrt-generator/bin/

# Запуск прошивальника (потребує sudo для TFTP на порту 69)
sudo python3 flasher.py
# або з явним шляхом до папки bin:
sudo python3 flasher.py ../openwrt-generator/bin
```

### 7. Генерація документації локально

```bash
cd docs
source ../myvenv/bin/activate

# Українська версія
make html SPHINXBUILD=../myvenv/bin/sphinx-build

# Англійська версія
make en SPHINXBUILD=../myvenv/bin/sphinx-build

# Відкрити у браузері
xdg-open _build/html/ua/index.html
```

### Базові команди для розробника

| Команда | Опис |
|---------|------|
| `python3 generate_configs.py` | Генерація конфігів для топології |
| `python3 generate_configs.py --build` | Генерація конфігів + збірка прошивок |
| `sudo python3 flasher.py` | Запуск масової прошивки |
| `flake8 .` | Перевірка стилю коду |
| `pylint openwrt-generator/ bulk-flasher/` | Глибокий аналіз коду |
| `bandit -r .` | Перевірка безпеки коду |
| `cd docs && make html SPHINXBUILD=...` | Збірка документації (UA) |
| `cd docs && make en SPHINXBUILD=...` | Збірка документації (EN) |
| `cd docs && make doctest SPHINXBUILD=...` | Запуск doctest-тестів |

---

## Використані технології та проекти

* [OpenWrt](https://openwrt.org/) — прошивка для роутерів
* [batman-adv](https://www.open-mesh.org/projects/batman-adv/wiki) — mesh-маршрутизація на рівні L2
* Python 3 — мова скриптів
* [Jinja2](https://jinja.palletsprojects.com/) — шаблонізатор конфігурацій
* [tftp-now](https://github.com/halfer53/tftp-now) — легковажний TFTP-сервер
* [Sphinx](https://www.sphinx-doc.org/) — генератор документації

---

## Як використовувати

### openwrt-generator.py
Скрипт шукає файл з топологією певного формату, приклад є в репозиторії.
Для вибраної моделі роутеру генерується прошивка для кожної ноди з необхідними пакетами та конфігурацією доступу, шифрування зв'язку, залежно від шаблонів у папці `templates`. Результати конфігурації для кожної ноди зберігаються у `configs`, а результати збірки у `bin`.

### bulk-flasher.py
Прошивання роутерів TP-WR840N потребує підключення по LAN і налаштування на відповідному інтерфейсі адреси `192.168.0.66`, за якою роутер у режимі прошивання шукатиме TFTP-сервер на порту 69. Прошивання відбувається за алфавітним порядком відштовхуючись від зібраних бінарників. Скрипт підніме TFTP-сервер і покладе необхідний для ноди бінарник у корінь сервера. Прошиття відбувається циклічно.

---

## Структура проекту

| Файл / Папка | Призначення |
|--------------|-------------|
| **bulk-flasher/** | Інструмент для масової прошивки пристроїв через TFTP |
| `bulk-flasher/flasher.py` | Скрипт, який автоматизує прошивку всіх вузлів: запускає TFTP-сервер, копіює прошивку як `tp_recovery.bin` і чекає на підключення кожного роутера |
| **openwrt-generator/** | Генератор конфігурацій OpenWrt для mesh-мережі |
| `openwrt-generator/generate_configs.py` | Основний скрипт, що читає топологію з JSON, генерує індивідуальні конфігурації для кожного вузла, створює SSH-ключі та (опціонально) запускає збірку образів |
| `openwrt-generator/topology.json` | Файл топології мережі: опис вузлів (id, координати) та зв'язків (Ethernet – сині, Wi-Fi – зелені) |
| **openwrt-generator/templates/** | Jinja2 шаблони конфігураційних файлів OpenWrt |
| `templates/batman-adv.j2` | Налаштування Batman-adv: інтерфейси, що входять у bat0, алгоритм маршрутизації BATMAN_IV |
| `templates/dropbear.j2` | Конфігурація SSH-сервера Dropbear: вимкнено вхід за паролем, лише за ключами |
| `templates/firewall.j2` | Правила фаєрволу: дозволено SSH, заборонено переадресацію, LAN-зона об'єднує bat0, wlan, lan |
| `templates/network.j2` | Мережеві інтерфейси: налаштування switch (активні порти), lan (bridge), wlan, bat0 зі статичною IP-адресою |
| `templates/system.j2` | Системні параметри: hostname вузла, часовий пояс UTC |
| `templates/wireless.j2` | Налаштування Wi-Fi: один радіомодуль (radio0), режим mesh (802.11s), унікальні mesh_id та mesh_key для кожної пари |
| **topologies/** | Приклади файлів топологій для тестування |
| `topologies/nodes-simple.json` | Проста топологія з базовими вузлами |
| `topologies/nodes.json` | Розширена топологія з додатковими параметрами |
| `topologies/supernodes.json` | Топологія з групуванням вузлів у суперноди (A, B, C, D, E) |
| **docs/** | Sphinx-документація проекту |
