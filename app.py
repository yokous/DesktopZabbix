import logging
import csv
from PyQt6.QtCore import QTimer # Добавь QTimer в импорты из PyQt6.QtCore
from PyQt6.QtWidgets import QFileDialog # Добавь QFileDialog в импорты из PyQt6.QtWidgets
import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, 
                             QPushButton, QVBoxLayout, QHBoxLayout, 
                             QListWidget, QStackedWidget, QMessageBox, QListWidgetItem)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

# Импортируем наш бэкенд, который мы упаковали в файл zabbix_backend.py
from zabbix_backend import ZabbixBackend

logging.basicConfig(
    filename='app_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class LoginWindow(QWidget):
    """Окно авторизации"""
    def __init__(self, backend, on_login_success):
        super().__init__()
        self.backend = backend
        self.on_login_success = on_login_success
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Вход в Zabbix Desktop')
        self.setFixedSize(350, 220)

        layout = QVBoxLayout()

        self.lbl_title = QLabel('Авторизация в системе мониторинга', self)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(self.lbl_title)

        self.txt_login = QLineEdit(self)
        self.txt_login.setPlaceholderText('Логин (например, Admin)')
        self.txt_login.setText('Admin')  # Подставляем сразу для удобства тестов
        layout.addWidget(self.txt_login)

        self.txt_password = QLineEdit(self)
        self.txt_password.setPlaceholderText('Пароль')
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setText('zabbix')  # Подставляем сразу для удобства тестов
        layout.addWidget(self.txt_password)

        self.btn_login = QPushButton('Подключиться к API', self)
        self.btn_login.clicked.connect(self.handle_login)
        self.btn_login.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        layout.addWidget(self.btn_login)

        self.setLayout(layout)

    def handle_login(self):
        login = self.txt_login.text()
        password = self.txt_password.text()

        # Вызываем метод бэкенда для проверки логина/пароля в Zabbix
        if self.backend.connect(login, password):
            self.on_login_success()
        else:
            QMessageBox.critical(self, 'Ошибка доступа', 'Не удалось подключиться к Zabbix API!\nПроверьте данные или лог ошибок.')

class MainWindow(QWidget):
    """Главное окно мониторинга"""
    def export_to_csv(self):
        if not self.all_hosts_data:
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", "", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream, delimiter=';')
                    # Заголовки таблицы
                    writer.writerow(['ID узла', 'Имя устройства', 'IP адрес', 'Статус в системе'])
                    
                    # Записываем данные
                    for host in self.all_hosts_data:
                        status_text = "Активен" if host['available'] else "Недоступен"
                        writer.writerow([host['id'], host['name'], host['ip'], status_text])
                print(f"Данные успешно экспортированы в {path}")
            except Exception as e:
                logging.error(f"Ошибка при экспорте в CSV: {e}")
    
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.all_hosts_data = []  # Тут храним сырые данные от API (731 хост)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Панель мониторинга сетевой доступности (Zabbix API)')
        self.resize(1000, 650)

        main_layout = QHBoxLayout()

        # --- ЛЕВАЯ ЧАСТЬ: Поиск и список хостов ---
        left_layout = QVBoxLayout()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText('Поиск устройства по имени или IP...')
        self.search_bar.textChanged.connect(self.filter_hosts)
        left_layout.addWidget(self.search_bar)

        self.host_list = QListWidget()
        self.host_list.currentItemChanged.connect(self.on_host_selected)
        left_layout.addWidget(self.host_list)
        
        self.btn_refresh = QPushButton('Обновить данные вручную')
        self.btn_refresh.clicked.connect(self.load_data_from_zabbix)
        left_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(left_layout, stretch=1)

        # --- ПРАВАЯ ЧАСТЬ: Метрики и реальный график ---
        right_layout = QVBoxLayout()
        
        self.lbl_host_title = QLabel('Выберите узел сети из списка слева')
        self.lbl_host_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        right_layout.addWidget(self.lbl_host_title)

        # Интегрируем график Matplotlib в окно PyQt6
        self.figure, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        right_layout.addWidget(self.canvas)

        main_layout.addLayout(right_layout, stretch=2)
        self.setLayout(main_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.load_data_from_zabbix)
        self.timer.start(30000)  # 30000 миллисекунд = 30 секунд

    def load_data_from_zabbix(self):
        """Загрузка хостов из нашего бэкенда"""
        self.host_list.clear()
        self.all_hosts_data = self.backend.get_all_hosts()
        self.display_hosts(self.all_hosts_data)

    def display_hosts(self, hosts_list):
        """Отрисовка списка в интерфейсе с цветовой маркировкой (ТЗ)"""
        self.host_list.clear()
        for host in hosts_list:
            # Формируем строку для списка с индикатором
            icon = "🟢" if host['available'] else "🔴"
            item_text = f"{icon} {host['name']} ({host['ip']})"
            
            item = QListWidgetItem(item_text)
            # Привязываем скрытый ID хоста к элементу списка, чтобы знать, что запрашивать при клике
            item.setData(Qt.ItemDataRole.UserRole, host['id'])
            
            # Если хост лежит (🔴), подсвечиваем текст красным цветом
            if not host['available']:
                item.setForeground(QColor('red'))
                
            self.host_list.addItem(item)

    def filter_hosts(self, text):
        """Мгновенная фильтрация хостов при вводе в поиск"""
        filtered = [h for h in self.all_hosts_data if text.lower() in h['name'].lower() or text.lower() in h['ip']]
        self.display_hosts(filtered)

    def on_host_selected(self, current, previous):
        """Событие клика на хост — запрашиваем метрики CPU за час и рисуем график"""
        if not current:
            return
        
        host_id = current.data(Qt.ItemDataRole.UserRole)
        host_name = current.text()
        self.lbl_host_title.setText(f"Загрузка CPU за последний час для: {host_name}")

        # Тянем реальную историю изменений из бэкенда
        times, values = self.backend.get_cpu_history(host_id)

        # Очищаем старый график и рисуем новый
        self.ax.clear()
        if times and values:
            self.ax.plot(times, values, marker='o', linestyle='-', color='#1f77b4')
            self.ax.set_title("Нагрузка CPU (%)")
            self.ax.set_ylim(0, 100)
            # Отображаем каждую 10-ю подпись времени на оси X, чтобы текст не слипался
            self.ax.set_xticks(times[::10]) 
            self.ax.grid(True, linestyle='--', alpha=0.6)
        else:
            # Если метрика "CPU utilization" не привязана к этому устройству в самом Zabbix
            self.ax.text(0.5, 0.5, "Нет данных CPU для этого узла\n(Проверьте шаблоны в Zabbix)", 
                         ha='center', va='center', fontsize=12, color='gray')
            self.ax.set_title("Данные отсутствуют")
            
        self.canvas.draw()

class Controller:
    """Управление переключением окон (с логина на главное)"""
    def __init__(self):
        # ВНИМАНИЕ: При запуске дома поменяй '127.0.0.1' на твой Tailscale IP '100.84.142.92'
        self.backend = ZabbixBackend(server_url='http://192.168.101.220/zabbix')
        
        self.stacked_widget = QStackedWidget()
        self.login_window = LoginWindow(self.backend, self.show_main_window)
        self.main_window = MainWindow(self.backend)

        self.stacked_widget.addWidget(self.login_window)
        self.stacked_widget.addWidget(self.main_window)
        self.stacked_widget.setCurrentWidget(self.login_window)
        self.stacked_widget.show()

    def show_main_window(self):
        self.stacked_widget.setCurrentWidget(self.main_window)
        # Как только перешли на главное окно — сразу загружаем все хосты
        self.main_window.load_data_from_zabbix()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    controller = Controller()
    sys.exit(app.exec())