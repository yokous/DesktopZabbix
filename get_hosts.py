from pyzabbix import ZabbixAPI

ZABBIX_SERVER = 'http://127.0.0.1/zabbix'
zapi = ZabbixAPI(ZABBIX_SERVER)
zapi.session.verify = False

try:
    zapi.login('Admin', 'zabbix')
    
    # Запрашиваем хосты. 
    # selectInterfaces нужен, чтобы вытащить IP-адрес устройства
    hosts = zapi.host.get(
        output=['hostid', 'name', 'status'],
        selectInterfaces=['ip']
    )
    
    print(f"Найдено устройств: {len(hosts)}")
    print("=" * 60)
    print(f"{'ID':<6} | {'Имя узла':<25} | {'IP-адрес':<15} | {'Статус'}")
    print("-" * 60)
    
    for host in hosts:
        # Получаем IP (если у узла несколько интерфейсов, берем первый)
        ip = host['interfaces'][0]['ip'] if host['interfaces'] else "Нет IP"
        
        # В Zabbix: status = '0' (монтиторинг включен), status = '1' (выключен)
        status = "Включен" if host['status'] == '0' else "Отключен"
        
        print(f"{host['hostid']:<6} | {host['name']:<25} | {ip:<15} | {status}")

except Exception as e:
    print(f"Ошибка: {e}")
