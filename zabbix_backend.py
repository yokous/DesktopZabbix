import time
import logging
from pyzabbix import ZabbixAPI

# Настраиваем логирование по ТЗ
logging.basicConfig(filename='app_errors.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ZabbixBackend:
    def __init__(self, server_url='http://100.84.142.92/zabbix'):
        # При работе из дома укажем глобальный IP от Tailscale!
        self.server_url = server_url
        self.zapi = ZabbixAPI(self.server_url)
        self.zapi.session.verify = False

    def connect(self, login, password):
        """Авторизация в Zabbix API"""
        try:
            self.zapi.login(login, password)
            return True
        except Exception as e:
            logging.error(f"Ошибка авторизации пользователя {login}: {e}")
            return False

    def get_all_hosts(self):
        """Получение списка всех узлов сети"""
        try:
            hosts = self.zapi.host.get(output=['hostid', 'name', 'status'], selectInterfaces=['ip'])
            result = []
            for h in hosts:
                ip = h['interfaces'][0]['ip'] if h['interfaces'] else "0.0.0.0"
                # Статус: 0 - включен, 1 - выключен
                is_available = h['status'] == '0'
                result.append({
                    'id': h['hostid'],
                    'name': h['name'],
                    'ip': ip,
                    'available': is_available
                })
            return result
        except Exception as e:
            logging.error(f"Ошибка получения списка хостов: {e}")
            return []

    def g


et_cpu_history(self, host_id):
        """Получение метрик CPU за последний час для графика"""
        try:
            items = self.zapi.item.get(hostids=host_id, search={'name': 'CPU utilization'}, output=['itemid', 'value_type'])
            if not items:
                return [], []
            
            item_id = items[0]['itemid']
            v_type = items[0]['value_type']
            
            now = int(time.time())
            one_hour_ago = now - 3600
            
            history = self.zapi.history.get(
                itemids=item_id, time_from=one_hour_ago, time_till=now,
                history=v_type, output=['clock', 'value'], sortfield='clock', sortorder='ASC'
            )
            
            times = [time.strftime('%H:%M', time.localtime(int(p['clock']))) for p in history]
            values = [float(p['value']) for p in history]
            return times, values
        except Exception as e:
            logging.error(f"Ошибка получения метрик для хоста {host_id}: {e}")
            return [], []
