#!/usr/bin/env python3

import os
import subprocess
import sys
import threading

import gi
import requests
import yaml

from utils.adb import get_device_info
from utils.get_alvr_version import get_alvr_version
from views.list_device import create_list_device
import gettext

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

APK_PACKAGE_NAME = 'alvr.client.stable'
APP_VERSION = "0.1.1"
ALVR_LATEST = "20.11.1"

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "ALVR-Companion")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
DEVICES_FILE = os.path.join("devices.yaml")

gettext.bindtextdomain('alvr_companion', localedir='locale')
gettext.textdomain('alvr_companion')
_ = gettext.gettext

class ALVRInstaller(Adw.Application):
    def __init__(self):
        super().__init__(application_id='ru.toxblh.AlvrCompanion')
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()
        
    def on_shutdown(self, app):
        # Perform any cleanup tasks here
        print("Shutting down ALVR Companion...")

        # Disconnect all Wi-Fi devices
        for serial in self.win.devices_info.keys():
            self.win.disconnect_device_wifi(serial)

        # Stop the ADB monitor
        if hasattr(self.win, 'adb_monitor_id') and self.win.adb_monitor_id:
            GLib.source_remove(self.win.adb_monitor_id)
            self.win.adb_monitor_id = None


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        
        # Add custom styles
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        button.green {
            background-color: green;
            color: white;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.set_title(_('ALVR Companion'))
        self.set_default_size(800, 600)

        self.VERSION = get_alvr_version() or ALVR_LATEST
        self.APK_URL = f"https://github.com/alvr-org/ALVR/releases/download/v{
            self.VERSION}/alvr_client_android.apk"
        self.APK_FILE = f"/tmp/alvr_client_{self.VERSION}.apk"
        self.INFO_FILE = f"/tmp/alvr_client_{self.VERSION}.info"

        # Загрузка конфигурации устройств
        self.load_devices_config()

        # Загрузка настроек пользователя
        self.load_user_config()
        
        self.current_serial = None
        self.init_ui()
        self.start_adb_monitor()
        self.connect_wifi_devices()

# Config files
    def load_devices_config(self):
        with open(DEVICES_FILE, 'r', encoding='utf-8') as f:
            self.devices_config = yaml.safe_load(f)

    def load_user_config(self):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.user_config = yaml.safe_load(f)
        else:
            self.user_config = {}

    def save_user_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(self.user_config, f)
# End Config files


    def init_ui(self):
        # Add custom styles
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        button.green {
            background-color: green;
            color: white;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        
        self.window_box = Adw.NavigationSplitView()
        self.window_box.set_min_sidebar_width(230)
        self.set_content(self.window_box)

        # Левая боковая панель
        about_item = Gio.MenuItem.new(_('About'), "app.about")

        menu = Gio.Menu()
        menu.append_item(about_item)

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_menu_model(menu)

        header_bar = Adw.HeaderBar()
        header_bar.pack_end(menu_button)

        # Add action
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self.show_about_dialog)
        self.get_application().add_action(action)

        self.left_content = Gtk.ScrolledWindow()

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_vexpand(True)
        self.list.set_css_classes(["navigation-sidebar"])
        self.list.connect('row-selected', self.on_device_selected)
        placeholder = Adw.StatusPage(
            title=_("Connect a device"), icon_name="drive-harddisk-usb-symbolic")
        placeholder.set_css_classes(["compact"])
        self.list.set_placeholder(placeholder)
        self.left_content.set_child(self.list)

        self.left_side = Adw.ToolbarView()
        self.left_side.add_top_bar(header_bar)
        self.left_side.set_content(self.left_content)

        self.sidebar = Adw.NavigationPage.new(
            child=self.left_side,
            title=_('ALVR Companion')
        )

        self.window_box.set_sidebar(self.sidebar)

        # -------------------------

        # Основная правая область контента
        more_info = Gtk.Button(label=_("Show Details"))
        more_info.connect('clicked', self.show_details_window)

        main_warp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.main_body = Gtk.ScrolledWindow()
        self.main_body.set_vexpand(True)
        main_warp.append(self.main_body)
        
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.window_box)
        main_warp.append(self.toast_overlay)

        self.right_header = Adw.HeaderBar()
        self.right_header.pack_start(more_info)

        self.right_side = Adw.ToolbarView()
        self.right_side.add_top_bar(self.right_header)
        self.right_side.set_content(main_warp)

        self.content = Adw.NavigationPage.new(
            child=self.right_side,
            title=_("Device")
        )

        # Разделение на боковую панель и основной контент
        self.window_box.set_content(self.content)

        # Кнопка установки APK
        self.install_button = None
        self.progress_bar = None
        self.streaming_button = None
        self.usb_button = None

        # Banner for unauthorized device
        self.unauthorized_banner = Adw.Banner()
        self.unauthorized_banner.set_title(
            _("Device not authorized! Allow USB connection on the device"))
        self.unauthorized_banner.set_button_label(_("Show how"))
        self.unauthorized_banner.set_revealed(False)
        self.right_side.add_top_bar(self.unauthorized_banner)

        # Словарь для хранения информации об устройствах
        self.device_pages = {}

    def on_device_selected(self, listbox, row):
        if row:
            device_serial = row.get_name()
            self.show_device_page(device_serial)
            self.current_serial = device_serial

    def show_device_page(self, device_serial, force_update=False):
        if device_serial in self.device_pages and not force_update:
            page = self.device_pages[device_serial]
        else:
            device_info = self.devices_info[device_serial]
            page = self.create_device_page(device_info)
            self.device_pages[device_serial] = page
        self.main_body.set_child(page)

    def create_device_page(self, device_info):
        # Создание страницы устройства
        device_serial = device_info['Serial Number']
        device_model = device_info['Model']
        alvr_version = device_info['ALVR Version']
        android_version = device_info['Android Version']
        authorized = device_info.get('Authorized', False)
        image_path = self.get_device_image_path(device_model)
        
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        device_box.set_margin_top(20)

        device_info_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        device_image = Gtk.Image.new_from_file(image_path)
        device_image.set_pixel_size(128)
        device_image.set_css_classes(["icon", "icon-dropshadow"])
        device_info_box.append(device_image)

        # Название устройства
        device_text_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5)
        device_name_label = Gtk.Label(label=device_model)
        device_name_label.set_css_classes(["title-1"])
        device_name_label.set_halign(Gtk.Align.START)

        # Create a grid for the device version
        device_version_grid = Gtk.Grid()
        device_version_grid.set_column_spacing(20)

        # Create the ALVR label
        alvr_label = Gtk.Label(label=_("ALVR installed:"))
        alvr_label.add_css_class("description")
        alvr_label.set_halign(Gtk.Align.START)

        # Create the version label
        version_label = Gtk.Label(label=alvr_version)
        version_label.set_halign(Gtk.Align.START)

        # Create the Android version label
        android_version_label_label = Gtk.Label(label=_("Android version:"))
        android_version_label_label.add_css_class("description")
        android_version_label_label.set_halign(Gtk.Align.START)
        android_version_label = Gtk.Label(label=android_version)
        android_version_label.set_halign(Gtk.Align.START)

        # Attach the new labels to the grid
        device_version_grid.attach(android_version_label_label, 0, 1, 1, 1)
        device_version_grid.attach(android_version_label, 1, 1, 1, 1)

        # Add the new labels to the device text box

        # Attach the labels to the grid
        device_version_grid.attach(alvr_label, 0, 0, 1, 1)
        device_version_grid.attach(version_label, 1, 0, 1, 1)

        self.usb_forward_status_label = Gtk.Label()

        # Add the grid to the device text box
        version_label.set_halign(Gtk.Align.START)
        device_text_box.append(device_name_label)
        device_text_box.append(device_version_grid)
        device_text_box.append(self.usb_forward_status_label)
        device_info_box.append(device_text_box)

        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Кнопка установки APK
        self.install_button = Gtk.Button(label=_("Install"))
        self.install_button.add_css_class("suggested-action")
        self.install_button.set_size_request(100, 30)
        
        if alvr_version == self.VERSION:
            self.install_button.set_label(_("Re-install"))
        
        self.install_button.connect(
            'clicked', self.on_install_button_clicked, device_serial)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_top(-8)
        self.progress_bar.set_visible(False)
        self.progress_bar.set_text("")
        
        self.streaming_button = Gtk.Button(label=_("Streaming"))
        self.streaming_button.connect(
            'clicked', self.on_streaming_button_clicked)
        
        self.usb_button = Gtk.Button(label=_("USB Connection"))
        self.usb_button.set_size_request(100, 30)
        self.usb_button.connect('clicked', self.setup_usb_forwarding)

        button_box.append(self.install_button)
        button_box.append(self.progress_bar)
        button_box.append(self.streaming_button)
        button_box.append(self.usb_button)

        device_info_box.append(
            Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True))  # Spacer
        device_info_box.append(button_box)

        # Add the device info box to the main device box
        device_box.append(device_info_box)

        settings_group = Adw.PreferencesGroup(title=_("Settings"))

        # Create a row for the auto-update setting
        auto_update_row = Adw.SwitchRow(
            title=_("Automatically update"), subtitle=_("Automatically update ALVR when connected"))
        settings_group.add(auto_update_row)

        # Create a row for the auto USB connection setting
        auto_usb_row = Adw.SwitchRow(title=_("Automatically connect via USB"),
                                     subtitle=_("Automatically prepare the device for USB connection instead of Wi-Fi"))
        settings_group.add(auto_usb_row)

        # Create a row for the auto USB connection setting
        wifi_switch = Adw.SwitchRow(title=_("Use Wi-Fi"), subtitle=_("Switch connection to Wi-Fi"))
        wifi_switch.set_active(self.user_config.get('devices', {}).get(
            device_serial, {}).get('wifi_enabled', False))
        wifi_switch.connect('notify::active', self.on_wifi_switch_toggled)
        settings_group.add(wifi_switch)

        # Add the settings group to the main device box
        device_box.append(settings_group)


        # Wrap the device box in an AdwClamp
        clamped_device_box = Adw.Clamp(child=device_box)
        
        if not authorized:
            self.unauthorized_banner.set_revealed(True)
            self.unauthorized_banner.connect('button_clicked', self.on_show_how_clicked, device_model)
            self.install_button.set_sensitive(False)
            self.streaming_button.set_sensitive(False)
            self.usb_button.set_sensitive(False)

        return clamped_device_box

    def get_device_image_path(self, model):
        # Получение пути к изображению устройства
        for device in self.devices_config['devices']:
            if device['model'] == model:
                return device['image']
        return './assets/default.png'  # Изображение по умолчанию

    def on_show_how_clicked(self, button, device_model):
        # Открытие окна с инструкцией
        self.show_instruction_window(device_model)

    def show_instruction_window(self, device_model):
        # Загрузка инструкции из конфигурационного файла и отображение окна
        instruction_file = f"assets/instructions/{device_model}.yaml"
        if os.path.exists(instruction_file):
            with open(instruction_file, 'r') as f:
                instructions = yaml.safe_load(f)
            # Создание окна с инструкцией
            instruction_window = Gtk.Window(title="Инструкция")
            instruction_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=10)
            instruction_window.set_child(instruction_box)

            for step in instructions['steps']:
                step_label = Gtk.Label(label=step['text'])
                instruction_box.append(step_label)
                if 'image' in step:
                    step_image = Gtk.Image.new_from_file(step['image'])
                    instruction_box.append(step_image)

            instruction_window.present()
        else:
            self.show_toast("Инструкция недоступна")

# USB Forwading

    def setup_usb_forwarding(self, _):
        try:
            subprocess.run(['adb', 'forward', 'tcp:9943', 'tcp:9943'])
            subprocess.run(['adb', 'forward', 'tcp:9944', 'tcp:9944'])
            self.check_usb_forwarding_status()
        except Exception as e:
            self.show_toast(f'USB Forwarding Error: {e}')

    def check_usb_forwarding_status(self):
        try:
            result = subprocess.check_output(
                ['adb', 'forward', '--list'], text=True)
            if 'tcp:9943' in result and 'tcp:9944' in result:
                self.usb_button.add_css_class("green")
                self.usb_forward_status_label.set_label(
                    'USB Forwarding: Enabled')
            else:
                self.usb_button.remove_css_class("green")
                self.usb_forward_status_label.set_label(
                    'USB Forwarding: Not enabled')
        except Exception as e:
            self.usb_button.remove_css_class("green")
            self.usb_button.add_css_class("destructive-action")
            self.usb_forward_status_label.set_label(
                'USB Forwarding: Error checking status')
            print(f"USB Forwarding Error: {e}")

# End USB Forwarding


# Streaming

    def on_streaming_button_clicked(self, button):
        # Запуск scrcpy с возможностью изменения параметра --crop
        self.start_scrcpy(self.current_serial)

    def start_scrcpy(self, device_serial):
        # Получение настроек scrcpy из конфигурации
        device_settings = self.user_config.get(
            'devices', {}).get(device_serial, {})
        use_crop = device_settings.get('use_crop', False)
        crop_params = device_settings.get('crop_params', '')

        # Формирование команды для запуска scrcpy с передачей серийного номера устройства
        # Добавляем опцию -s для выбора устройства
        scrcpy_command = ['scrcpy', '-s', device_serial]
        if use_crop and crop_params:
            scrcpy_command.extend(['--crop', crop_params])

        # Запуск scrcpy с указанным серийным номером устройства
        try:
            subprocess.Popen(scrcpy_command)
        except Exception as e:
            print(f"Ошибка при запуске scrcpy: {e}")

# End Streaming


# Wi-Fi

    def on_wifi_switch_toggled(self, switch, state):
        # Переключение соединения на Wi-Fi
        if switch.get_active():
            self.connect_device_wifi(self.current_serial)
        else:
            self.disconnect_device_wifi(self.current_serial)

    def connect_device_wifi(self, device_serial):
        try:
            device_config = self.user_config.get('devices', {}).get(device_serial, {})
            ip_address = device_config.get('ip_address')

            if ip_address:
                try:
                    subprocess.run(['adb', 'connect', f'{ip_address}:5555'], check=True)
                    self._update_wifi_config(device_serial, ip_address)
                    return
                except subprocess.CalledProcessError:
                    pass

            result = subprocess.run(['adb', '-s', device_serial, 'shell', 'ip', 'addr', 'show', 'wlan0'], 
                                    capture_output=True, text=True)
            ip_address = next((line.split()[1].split('/')[0] for line in result.stdout.split('\n') if 'inet ' in line), None)
            if not ip_address:
                raise Exception("Не удалось получить IP адрес устройства")

            subprocess.run(['adb', 'connect', f'{ip_address}:5555'], check=True)
            self._update_wifi_config(device_serial, ip_address)
        except Exception as e:
            self.show_toast(f"Ошибка подключения по Wi-Fi: {e}")

    def _update_wifi_config(self, device_serial, ip_address):
        device_config = self.user_config.setdefault('devices', {}).setdefault(device_serial, {})
        device_config.update({'wifi_enabled': True, 'ip_address': ip_address, 'wifi_serial': f"{ip_address}:5555"})
        self.save_user_config()
        self.show_toast("Устройство подключено по Wi-Fi")

    def disconnect_device_wifi(self, device_serial):
        # Отключение устройства от Wi-Fi
        try:
            subprocess.run(['adb', '-s', device_serial, 'disconnect'], check=True)
            self.show_toast("Устройство отключено от Wi-Fi")
            
            # Сохранение настройки
            self.user_config.setdefault('devices', {}).setdefault(
                self.current_serial, {})['wifi_enabled'] = False
            self.save_user_config()
            
        except Exception as e:
            self.show_toast(f"Ошибка отключения от Wi-Fi: {e}")

    def connect_wifi_devices(self):
        for serial, device_config in self.user_config.get('devices', {}).items():
            if device_config.get('wifi_enabled', False):
                self.connect_device_wifi(serial)

# End Wi-Fi

    def show_about_dialog(self, action, param):
        dialog = Adw.AboutDialog()
        dialog.set_application_name(_("ALVR Companion"))
        dialog.set_developer_name(_("Anton Palgunov (Toxblh)"))
        dialog.set_version(APP_VERSION)
        dialog.set_copyright(_("© 2024 Anton Palgunov (Toxblh)"))
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_translator_credits("translator-credits")
        dialog.set_issue_url("https://github.com/Toxblh/ALVR-Companion/issues")
        dialog.add_link("GitHub", "https://github.com/Toxblh/ALVR-Companion")
        dialog.add_link("Donate", "https://www.buymeacoffee.com/toxblh")

        dialog.present(self.get_application().get_active_window())

# Download APK

    def download_apk(self):
        try:
            response = requests.get(self.APK_URL, stream=True)
            total_length = response.headers.get('content-length')

            with open(self.APK_FILE, 'wb') as f:
                if total_length is None:
                    f.write(response.content)
                    GLib.idle_add(self.update_progress_bar,
                                  1.0, _('Download complete'))
                else:
                    dl = 0
                    total_length = int(total_length)
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        fraction = dl / total_length
                        GLib.idle_add(self.update_progress_bar, fraction, f'Downloading... {
                                      int(fraction*100)}%')
            with open(self.INFO_FILE, 'w') as f:
                f.write('Downloaded')
            GLib.idle_add(self.on_download_complete)
        except Exception as e:
            GLib.idle_add(self.on_download_error, str(e))

    def update_progress_bar(self, fraction, text):
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(text)
        return False

    def on_download_complete(self):
        self.progress_bar.set_visible(False)
        self.show_toast(_("APK Downloaded"))
        self.install_button.set_label(_("Install"))
        return False

    def on_download_error(self, message):
        self.progress_bar.set_visible(False)
        self.show_toast(_(f"Download APK Error: {message}"))
        return False

# End Download APK

    def start_adb_monitor(self):
        self.devices_info = {}
        self.adb_monitor_id = GLib.timeout_add(1000, self.check_adb_devices)

    def check_adb_devices(self):
        try:
            result = subprocess.check_output(['adb', 'devices'], text=True)
            lines = result.strip().split('\n')[1:]  # Пропускаем первую строку
            devices = [line.split('\t') for line in lines if line.strip()]
            connected_serials = [device[0] for device in devices]
            unauthorized_serials = [device[0] for device in devices if device[1] == 'unauthorized']

            # Обновление списка устройств
            current_serials = set(self.devices_info.keys())
            new_serials = set(connected_serials) - current_serials
            removed_serials = current_serials - set(connected_serials)

            # Check for devices that have changed authorization status
            for serial in current_serials & set(connected_serials):
                if serial in unauthorized_serials and self.devices_info[serial]['Authorized']:
                    # Device became unauthorized
                    self.devices_info[serial]['Authorized'] = False
                    self.update_device_in_sidebar(serial)
                elif serial not in unauthorized_serials and not self.devices_info[serial]['Authorized']:
                    # Device became authorized
                    device_info = get_device_info(serial)
                    self.devices_info[serial] = device_info
                    self.devices_info[serial]['Authorized'] = True
                    self.update_device_in_sidebar(serial)

            for serial in new_serials:
                if serial in unauthorized_serials:
                    unauth_device = {
                        'Authorized': False,
                        'Serial Number': serial, 
                        'Model': 'Unauthorized Device',
                        'ALVR Version': None,
                        'Android Version': None,
                        'Build Version': None,
                        'Manufacturer': None
                        }
                    self.devices_info[serial] = unauth_device
                    self.add_device_to_sidebar(unauth_device)
                    if self.current_serial == None:
                        self.current_serial = serial
                        self.show_device_page(serial)
                else:    
                    device_info = get_device_info(serial)
                    self.devices_info[serial] = device_info
                    self.devices_info[serial]['Authorized'] = True
                    self.add_device_to_sidebar(device_info)

            for serial in removed_serials:
                self.remove_device_from_sidebar(serial)
                del self.devices_info[serial]

        except Exception as e:
            print(f"ADB Error: {e}")
        return True  # Продолжаем вызывать эту функцию

    def add_device_to_sidebar(self, device_info):
        # Добавление устройства в боковую панель
        serial = device_info['Serial Number']
        model = device_info['Model']
        image_path = self.get_device_image_path(model)
        row = create_list_device(model, serial, image_path)
        row.set_name(serial)
        self.list.append(row)
        
    def update_device_in_sidebar(self, serial):
        self.remove_device_from_sidebar(serial)
        self.add_device_to_sidebar(self.devices_info[serial])
        if self.current_serial == serial:
            self.show_device_page(self.current_serial, force_update=True)

    def remove_device_from_sidebar(self, serial):
        # Удаление устройства из боковой панели
        for row in self.list:
            if row.get_name() == serial:
                self.list.remove(row)
        self.show_toast(_("Device disconnected"))

    def on_install_button_clicked(self, _1, _2):
        self.install_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        if not os.path.exists(self.APK_FILE):
            self.install_button.set_sensitive(False)
            self.install_button.set_label(_('Downloading...'))
            self.download_apk()

        device_id = self.current_serial
 
        self.install_button.set_sensitive(False)
        self.install_button.set_label(_('Installing...'))
        self.progress_bar.set_fraction(0)
        self.progress_bar.set_text('')

        # Start installation in a separate thread
        self.install_thread = threading.Thread(
            target=self.install_apk, args=(device_id,))
        self.install_thread.start()

        # Start progress bar animation
        self.progress_timeout_id = GLib.timeout_add(
            250, self.increment_progress)

    def increment_progress(self):
        fraction = self.progress_bar.get_fraction()
        fraction += 0.05
        if fraction > 1.0:
            fraction = 0.0
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text('Installing...')
        return True  # Continue calling this function

    def install_apk(self, device_id):
        try:
            process = subprocess.Popen(['adb', '-s', device_id, 'install', '-r', self.APK_FILE],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                GLib.idle_add(self.on_install_finished)
            else:
                GLib.idle_add(self.on_install_error, stderr)
        except Exception as e:
            GLib.idle_add(self.on_install_error, str(e))

    def on_install_finished(self):
        self.progress_bar.set_visible(False)
        if hasattr(self, 'progress_timeout_id') and self.progress_timeout_id:
            GLib.source_remove(self.progress_timeout_id)
            self.progress_timeout_id = None
        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text('Installation Complete')
        self.show_toast('APK Installed Successfully.')
        self.install_button.set_sensitive(True)
        if self.devices_info[self.current_serial]['ALVR Version'] == self.VERSION:
            self.install_button.set_label(_('Re-install'))
        else:
            self.install_button.set_label(_('Install'))
        return False

    def on_install_error(self, message):
        if hasattr(self, 'progress_timeout_id') and self.progress_timeout_id:
            GLib.source_remove(self.progress_timeout_id)
            self.progress_timeout_id = None
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text('')
        self.show_toast('Installation Error.')
        print(message)
        self.install_button.set_sensitive(True)
        self.install_button.set_label(_('Install'))
        return False

    def show_details_window(self, _):
        try:
            device_info =  self.devices_info[self.current_serial]
            window = Gtk.Window(title="Device Details")
            window.set_transient_for(self)
            window.set_modal(True)
            window.set_default_size(400, 300)
            window.set_resizable(False)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            label = Gtk.Label(label="Device Information")
            info = Gtk.Label(label=f"Model: {device_info['Model']}\n"
                             f"Manufacturer: {device_info['Manufacturer']}\n"
                             f"Android Version: {device_info['Android Version']}\n"
                             f"Build Version: {device_info['Build Version']}\n"
                             f"ALVR Version: {device_info['ALVR Version']}\n"
                             f"Serial Number: {device_info['Serial Number']}\n"
                             f"ALVR Latest: {self.VERSION}\n")
            box.append(label)
            box.append(info)
            window.set_child(box)

            window.present()

            print('Device Info:\n' + '\n'.join(
                [f"{key}: {value}" for key, value in device_info.items()]))
        except Exception as e:
            print(f"Device Info: Error fetching info: {e}")
            
    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        self.toast_overlay.add_toast(toast)
        print(message)

def main():
    # Переключение adb в режим tcpip
    subprocess.run(['adb', 'tcpip', '5555'])
    app = ALVRInstaller()
    app.run(sys.argv)

if __name__ == '__main__':
    main()
