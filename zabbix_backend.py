"""
zabbix_backend.py
"""

import logging
import logging.handlers
import time
import sqlite3
from datetime import datetime
from pyzabbix import ZabbixAPI

logger = logging.getLogger('zabbix_app')
logger.setLevel(logging.ERROR)
_h = logging.handlers.RotatingFileHandler(
    'app_errors.log', maxBytes=5*1024*1024, backupCount=1, encoding='utf-8')
_h.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(_h)


class ZabbixBackend:

    def __init__(self, server_url='http://192.168.101.220/zabbix'):
        self.server_url = server_url
        self.zapi = None
        self._db_path = 'comments.db'
        self._init_db()

    # ── Авторизация ──────────────────────────────────────────────────────────
    def connect(self, username, password):
        try:
            self.zapi = ZabbixAPI(self.server_url)
            self.zapi.session.verify = False
            self.zapi.login(username, password)
            print(f'[OK] Подключились к {self.server_url}')
            return True
        except Exception as e:
            logger.error(f'Ошибка авторизации: {e}', exc_info=True)
            self.zapi = None
            return False

    # ── Хосты ────────────────────────────────────────────────────────────────
    def get_all_hosts(self):
        if not self.zapi:
            return []
        try:
            zabbix_hosts = self.zapi.host.get(
                output=['hostid', 'name', 'status'],
                selectInterfaces=['ip', 'available', 'type'],
                selectGroups=['name'],
                selectTriggers=['triggerid', 'value'],
            )

            if not zabbix_hosts:
                return []

            hosts = []
            for h in zabbix_hosts:
                # ── IP ──
                ip_addr = '0.0.0.0'
                iface_available = False

                interfaces = h.get('interfaces', [])
                if interfaces:
                    ip_addr = interfaces[0].get('ip', '0.0.0.0')
                    # available: '1'=OK, '2'=FAIL, '0'=unknown
                    # Если есть хоть один интерфейс со статусом '1' — считаем доступным
                    for iface in interfaces:
                        if str(iface.get('available', '0')) == '1':
                            iface_available = True
                            break

                # Хост включён в мониторинг (status='0' = enabled)
                host_enabled = str(h.get('status', '1')) == '0'

                # ── Доступность ──
                # Логика: если хост enabled И хоть один интерфейс отвечает → доступен
                # Для хостов без агента (только ICMP) available всегда '0' в интерфейсе,
                # поэтому для них смотрим на отсутствие PROBLEM-триггеров
                triggers = h.get('triggers', [])
                has_problems = any(str(t.get('value', '0')) == '1' for t in triggers)

                if host_enabled and iface_available:
                    available = True
                elif host_enabled and not interfaces:
                    available = True   # хост без интерфейсов — считаем включённым
                elif host_enabled and not has_problems:
                    # нет активных проблем → скорее всего доступен
                    available = True
                else:
                    available = host_enabled  # хотя бы включён

                # ── Группа ──
                groups_list = h.get('groups', [])
                group_name = groups_list[0]['name'] if groups_list else '—'

                hosts.append({
                    'id':           h['hostid'],
                    'name':         h['name'],
                    'ip':           ip_addr,
                    'group':        group_name,
                    'available':    available,
                    'has_problems': has_problems,
                })
            return hosts
        except Exception as e:
            logger.error(f'Ошибка получения хостов: {e}', exc_info=True)
            return []

    # ── Метрики ──────────────────────────────────────────────────────────────
    def _find_item(self, host_id, names):
        """
        Ищет первый подходящий item.
        1) Пробует API-поиск (search + wildcards) по каждому варианту имени.
        2) Если ничего не нашлось — забирает ВСЕ item'ы хоста и ищет
           регистронезависимое совпадение по подстроке локально (страхует
           от разницы в регистре/пробелах, на которые Zabbix LIKE может
           реагировать иначе, чем ожидается).
        """
        if not self.zapi:
            return None
        for name in names:
            try:
                items = self.zapi.item.get(
                    hostids=host_id,
                    output=['itemid', 'value_type', 'name'],
                    search={'name': name},
                    searchWildcardsEnabled=True,
                    sortfield='name',
                    limit=5,
                )
                if items:
                    # Если есть несколько совпадений — берём то, чьё имя точнее всего
                    # совпадает (регистронезависимо) с искомым
                    exact = [i for i in items if i['name'].strip().lower() == name.strip().lower()]
                    chosen = exact[0] if exact else items[0]
                    print(f'[item] Найдено "{chosen["name"]}" по запросу "{name}" (host={host_id})')
                    return chosen
            except Exception as e:
                logger.error(f'Ошибка поиска item "{name}": {e}')

        # ── Fallback: локальный регистронезависимый поиск по всем item'ам хоста ──
        try:
            all_items = self.zapi.item.get(
                hostids=host_id,
                output=['itemid', 'value_type', 'name'],
            )
            for name in names:
                target = name.strip().lower()
                for it in all_items:
                    if target in it['name'].strip().lower():
                        print(f'[item][fallback] Найдено "{it["name"]}" по запросу "{name}" (host={host_id})')
                        return it
        except Exception as e:
            logger.error(f'Ошибка fallback-поиска item: {e}')

        print(f'[item] Ничего не найдено для host={host_id}, варианты: {names}')
        return None

    def _get_history(self, host_id, names, hours=1):
        """
        Возвращает (times, values, real_name).
        Ищет item строго по списку имён (порядок = приоритет).
        real_name — настоящее имя найденного item'а в Zabbix.
        """
        if not self.zapi:
            return [], [], None
        item = self._find_item(host_id, names)
        if not item:
            return [], [], None
        real_name = item['name']
        try:
            now = int(time.time())
            data = self.zapi.history.get(
                itemids=item['itemid'],
                time_from=now - hours * 3600,
                time_till=now,
                output=['clock', 'value'],
                history=item['value_type'],
                sortfield='clock',
                sortorder='ASC',
                limit=600,
            )
            if not data:
                print(f'[history] Пусто для item={item["itemid"]} ("{real_name}"), пробуем trends…')
                try:
                    data = self.zapi.trend.get(
                        itemids=item['itemid'],
                        time_from=now - hours * 3600,
                        time_till=now,
                        output=['clock', 'value_avg'],
                        sortfield='clock',
                        sortorder='ASC',
                    )
                    if data:
                        print(f'[trend] Найдено {len(data)} точек для "{real_name}"')
                        times  = [datetime.fromtimestamp(int(p['clock'])).strftime('%H:%M') for p in data]
                        values = [float(p['value_avg']) for p in data]
                        return times, values, real_name
                    else:
                        print(f'[trend] Тоже пусто для "{real_name}" (itemid={item["itemid"]})')
                except Exception as e:
                    logger.error(f'Ошибка trend.get для "{real_name}": {e}')
                return [], [], real_name
            print(f'[history] Найдено {len(data)} точек для "{real_name}"')
            times  = [datetime.fromtimestamp(int(p['clock'])).strftime('%H:%M') for p in data]
            values = [float(p['value']) for p in data]
            return times, values, real_name
        except Exception as e:
            logger.error(f'Ошибка истории item {item["itemid"]}: {e}', exc_info=True)
            return [], [], real_name

    # ── Определение типа хоста: есть агент или только ICMP ────────────────────
    def host_has_agent(self, host_id) -> bool:
        """Проверяет, есть ли у хоста хотя бы один настоящий агентский item (CPU/RAM/Disk/Net)."""
        if not self.zapi:
            return False
        try:
            items = self.zapi.item.get(
                hostids=host_id,
                output=['itemid'],
                search={'name': 'CPU utilization'},
                searchWildcardsEnabled=True,
                limit=1,
            )
            return bool(items)
        except Exception:
            return False

    # ── 4 слота метрик: либо агентские, либо честные ICMP ─────────────────────
    # Названия слотов фиксированы — это то, что отображается в заголовках вкладки.
    AGENT_SLOTS = {
        'CPU':  ['CPU utilization', 'CPU idle time', 'CPU busy time',
                 'Processor load (1 min average per core)', 'CPU load average (1m avg)'],
        'RAM':  ['Memory utilization', 'Used memory in %', 'Available memory in %',
                 'Memory used percentage'],
        'Диск': ['Used disk space on / in %', 'Space utilization', 'Disk space usage /',
                 '/ space utilization', 'C: space utilization'],
        'Сеть': ['Bits received', 'Interface * bits received', 'Incoming network traffic on *',
                 'Outgoing network traffic on *', 'Bits sent', 'Packets received'],
    }

    # Для ICMP-хостов (без агента) — 4 реальные метрики под честными именами-слотами
    ICMP_SLOTS = {
        'ICMP ping':          ['ICMP ping'],
        'ICMP response time': ['ICMP response time'],
        'ICMP loss':          ['ICMP loss'],
        'PING response time': ['PING response time'],
    }

    def get_metric_slots(self, host_id) -> list:
        """
        Динамически определяет, какие метрики РЕАЛЬНО существуют у хоста,
        и возвращает только их названия (от 1 до 4 слотов — без заглушек).

        Сначала проверяет агентские метрики (CPU/RAM/Диск/Сеть).
        Если хотя бы одна из них есть — хост считается агентским,
        и возвращаются только агентские слоты, которые реально нашлись.
        Иначе проверяет ICMP-метрики и возвращает только найденные.
        """
        if not self.zapi:
            return []
        try:
            all_items = self.zapi.item.get(
                hostids=host_id,
                output=['name'],
            )
            names_lower = [it['name'].strip().lower() for it in all_items]
        except Exception as e:
            logger.error(f'Ошибка получения списка item\'ов хоста: {e}', exc_info=True)
            return []

        def slot_exists(candidates):
            for cand in candidates:
                cand_l = cand.strip().lower()
                # Убираем wildcard '*' для локального substring-сравнения
                cand_plain = cand_l.replace('*', '')
                for n in names_lower:
                    if cand_plain and cand_plain in n:
                        return True
            return False

        agent_found = [slot for slot, cands in self.AGENT_SLOTS.items() if slot_exists(cands)]
        if agent_found:
            # Сохраняем порядок CPU → RAM → Диск → Сеть
            order = ['CPU', 'RAM', 'Диск', 'Сеть']
            return [s for s in order if s in agent_found]

        icmp_found = [slot for slot, cands in self.ICMP_SLOTS.items() if slot_exists(cands)]
        if icmp_found:
            order = ['ICMP ping', 'ICMP response time', 'ICMP loss', 'PING response time']
            return [s for s in order if s in icmp_found]

        return []

    def get_metric_history(self, host_id, slot_name, hours=1):
        """
        Возвращает (times, values, real_name) для конкретного слота (заголовка графика).
        slot_name — один из ключей AGENT_SLOTS или ICMP_SLOTS.
        """
        names = self.AGENT_SLOTS.get(slot_name) or self.ICMP_SLOTS.get(slot_name)
        if not names:
            return [], [], None
        return self._get_history(host_id, names, hours)

    # ── Список доступных метрик для хоста ────────────────────────────────────
    def get_available_items(self, host_id):
        """Возвращает все item'ы хоста — для отладки."""
        if not self.zapi:
            return []
        try:
            items = self.zapi.item.get(
                hostids=host_id,
                output=['itemid', 'name', 'value_type'],
                limit=50,
                sortfield='name',
            )
            return items
        except Exception:
            return []

    # ── Комментарии ──────────────────────────────────────────────────────────
    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute('''CREATE TABLE IF NOT EXISTS comments (
                host_id TEXT PRIMARY KEY, text TEXT NOT NULL, updated TEXT NOT NULL)''')
            conn.commit(); conn.close()
        except Exception as e:
            logger.error(f'Ошибка инициализации БД: {e}', exc_info=True)

    def get_comment(self, host_id):
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute('SELECT text FROM comments WHERE host_id=?', (host_id,)).fetchone()
            conn.close()
            return row[0] if row else ''
        except Exception:
            return ''

    def save_comment(self, host_id, text):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute('''INSERT INTO comments(host_id,text,updated) VALUES(?,?,?)
                ON CONFLICT(host_id) DO UPDATE SET text=excluded.text,updated=excluded.updated''',
                (host_id, text, datetime.now().isoformat()))
            conn.commit(); conn.close()
        except Exception as e:
            logger.error(f'Ошибка сохранения комментария: {e}', exc_info=True)

    def delete_comment(self, host_id):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute('DELETE FROM comments WHERE host_id=?', (host_id,))
            conn.commit(); conn.close()
        except Exception as e:
            logger.error(f'Ошибка удаления комментария: {e}', exc_info=True)
