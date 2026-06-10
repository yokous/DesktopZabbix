import sys
from pyzabbix import ZabbixAPI

# Локальный адрес Zabbix на этой же машине
ZABBIX_SERVER = 'http://127.0.0.1/zabbix'

print("Пробуем подключиться к Zabbix API...")

try:
    zapi = ZabbixAPI(ZABBIX_SERVER)
    # Отключаем строгую проверку SSL, если веб-сервер работает по HTTP
    zapi.session.verify = False
    
    # Входим под стандартными данными Admin / zabbix
    zapi.login('Admin', 'zabbix')
    print("Успешное подключение! Мост Python -> Zabbix работает.")
    
    # Запрашиваем версию Zabbix API для проверки
    print(f"Версия Zabbix API: {zapi.api_version()}")

except Exception as e:
    print(f"\n[Ошибка] Не удалось авторизоваться в Zabbix.")
    print(f"Детали ошибки: {e}")
    print("\nВозможные причины: Zabbix еще не запущен до конца, либо пароль 'zabbix' изменен.")
