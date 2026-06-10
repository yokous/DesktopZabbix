import time
from pyzabbix import ZabbixAPI

ZABBIX_SERVER = 'http://127.0.0.1/zabbix'
zapi = ZabbixAPI(ZABBIX_SERVER)
zapi.session.verify = False

try:
    zapi.login('Admin', 'zabbix')
    
    # Будем тестировать на самом Zabbix сервере (его ID 10084)
    HOST_ID = '10084' 
    
    print(f"Ищем метрики процессора для хоста ID {HOST_ID}...")
    
    # 1. Получаем список элементов данных (Items), связанных с CPU
    # Ищем элементы, в названии которых есть "CPU utilization"
    items = zapi.item.get(
        hostids=HOST_ID,
        search={'name': 'CPU utilization'},
        output=['itemid', 'name', 'value_type']
    )
    
    if not items:
        print("Метрика 'CPU utilization' не найдена для этого хоста.")
    else:
        item = items[0]
        print(f"Успешно нашли метрику: {item['name']} (ID: {item['itemid']})")
        print("-" * 50)
        
        # Вычисляем временное окно: текущее время и 1 час назад (3600 секунд)
        now = int(time.time())
        one_hour_ago = now - 3600
        
        # 2. Запрашиваем историю изменений за этот час
        # value_type берем из самого item (обычно 0 - это число с плавающей точкой)
        history = zapi.history.get(
            itemids=item['itemid'],
            time_from=one_hour_ago,
            time_till=now,
            history=item['value_type'], 
            output=['clock', 'value'],
            sortfield='clock',
            sortorder='ASC'
        )
        
        print(f"Получено точек данных за последний час: {len(history)}")
        print("-" * 50)
        
        # Выведем первые 10 записей для проверки
        for point in history[:10]:
            # Переводим Unix-время в понятный формат времени
            readable_time = time.strftime('%H:%M:%S', time.localtime(int(point['clock'])))
            print(f"Время: {readable_time} | Загрузка CPU: {float(point['value'])}%")

except Exception as e:
    print(f"Ошибка при получении метрик: {e}")
