#!/usr/bin/env python3

import os
import subprocess
import sys
import threading

import gi
import requests
import yaml
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from utils.adb import get_device_info
from utils.get_alvr_version import get_alvr_version
from views.list_device import create_list_device
import gettext

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

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

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        

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
        
        self.init_ui()
        self.check_apk_status()
        self.start_adb_monitor()

    def load_devices_config(self):
        # Загрузка конфигурации устройств
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
        # Сохранение пользовательских настроек
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(self.user_config, f)
            
    def init_ui(self):
        # Create the main vertical box
        self.window_box = Adw.NavigationSplitView()
        # self.window_box.set_max_sidebar_width(300)
        # self.window_box.set_min_sidebar_width(300)
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
        
        self.main_body = Gtk.ScrolledWindow()
        
        self.right_header = Adw.HeaderBar()
        self.right_header.pack_start(more_info)

        self.right_side = Adw.ToolbarView()
        self.right_side.add_top_bar(self.right_header)
        self.right_side.set_content(self.main_body)

        self.content = Adw.NavigationPage.new(
            child=self.right_side,
            title=_("Device")
        )

        # Разделение на боковую панель и основной контент
        self.window_box.set_content(self.content)

        # -------------------------
        

        # Banner for unauthorized device
        self.unauthorized_banner = Adw.Banner()
        self.unauthorized_banner.set_title(
            _("Device not authorized! Allow USB connection on the device"))
        self.unauthorized_banner.set_button_label(_("Show how"))
        self.unauthorized_banner.set_revealed(False)

        # Add the banner to the main content
        self.right_side.add_top_bar(self.unauthorized_banner)

        # Create a box to hold the device information and actions
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        device_box.set_margin_top(20)

        # Create a horizontal box for the device image and name
        device_info_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        device_image = Gtk.Image.new_from_file('./assets/oculusquest2.png')
        device_image.set_pixel_size(128)
        device_image.set_css_classes(["icon", "icon-dropshadow"])
        device_info_box.append(device_image)

        # Create a vertical box for the device name and version
        device_text_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5)
        device_name_label = Gtk.Label(label="Oculus Quest 2")
        device_name_label.set_css_classes(["title-1"])
        device_name_label.set_halign(Gtk.Align.START)

        # Create a grid for the device version
        device_version_grid = Gtk.Grid()
        device_version_grid.set_column_spacing(20)

        # Create the ALVR label
        alvr_label = Gtk.Label(label="ALVR")
        alvr_label.add_css_class("description")
        alvr_label.set_halign(Gtk.Align.START)

        # Create the version label
        version_label = Gtk.Label(label="20.11.1")
        version_label.set_halign(Gtk.Align.START)

        # Create the Android version label
        android_version_label_label = Gtk.Label(label=_("Android version:"))
        android_version_label_label.add_css_class("description")
        android_version_label_label.set_halign(Gtk.Align.START)
        android_version_label = Gtk.Label(label="12")
        android_version_label.set_halign(Gtk.Align.START)

        # Create the Build version label
        build_version_label_label = Gtk.Label(label=_("Build version:"))
        build_version_label_label.set_halign(Gtk.Align.START)
        build_version_label = Gtk.Label(label="SQ3A.22.A1")
        build_version_label.set_halign(Gtk.Align.START)

        # Attach the new labels to the grid
        device_version_grid.attach(android_version_label_label, 0, 1, 1, 1)
        device_version_grid.attach(android_version_label, 1, 1, 1, 1)
        device_version_grid.attach(build_version_label_label, 0, 2, 1, 1)
        device_version_grid.attach(build_version_label, 1, 2, 1, 1)

        # Add the new labels to the device text box

        # Attach the labels to the grid
        device_version_grid.attach(alvr_label, 0, 0, 1, 1)
        device_version_grid.attach(version_label, 1, 0, 1, 1)

        # Add the grid to the device text box
        version_label.set_halign(Gtk.Align.START)
        device_text_box.append(device_name_label)
        device_text_box.append(device_version_grid)
        device_info_box.append(device_text_box)

        # Create buttons for installing and USB connection
        # Create a vertical box for the buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self.download_button = Gtk.Button(label=_("Download"))
        self.download_button.set_size_request(100, 30)
        self.download_button.connect(
            'clicked', self.on_download_button_clicked)

        self.install_button = Gtk.Button(label=_("Install"))
        self.install_button.add_css_class("suggested-action")
        self.install_button.set_size_request(100, 30)
        self.install_button.connect('clicked', self.on_install_button_clicked)

        # Create a progress bar
        self.progress_bar = Gtk.ProgressBar()
        # self.progress_bar.set_margin_top(-8)
        # self.progress_bar.set_visible(False)
        self.progress_bar.set_text("123")

        # Add the button and progress bar to the button box
        button_box.append(self.install_button)
        button_box.append(self.progress_bar)
        usb_button = Gtk.Button(label=_("USB Connection"))
        # usb_button.add_css_class("destructive-action")
        usb_button.set_size_request(100, 30)

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

        # Apply the custom style to the button
        usb_button.add_css_class("green")

        button_box.append(self.download_button)
        button_box.append(usb_button)

        # Align the button box to the end (right side)
        device_info_box.append(
            Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True))  # Spacer
        device_info_box.append(button_box)

        # Add the device info box to the main device box
        device_box.append(device_info_box)

        # Create a preferences group for settings
        settings_group = Adw.PreferencesGroup(title=_("Settings"))

        # Create a row for the auto-update setting
        auto_update_row = Adw.SwitchRow(
            title=_("Automatically update"), subtitle=_("Automatically update ALVR when connected"))
        settings_group.add(auto_update_row)

        # Create a row for the auto USB connection setting
        auto_usb_row = Adw.SwitchRow(title=_("Automatically connect via USB"),
                         subtitle=_("Automatically prepare the device for USB connection instead of Wi-Fi"))
        settings_group.add(auto_usb_row)

        # Add the settings group to the main device box
        device_box.append(settings_group)

        # Wrap the device box in an AdwClamp
        clamped_device_box = Adw.Clamp(child=device_box)

        self.main_body.set_child(clamped_device_box)

        # --- Презентация устройства ---

        self.apk_status_label = Gtk.Label(label=_('APK Status: Checking...'))
        self.device_status_label = Gtk.Label(label=_('Device Status: Checking...'))
        self.install_status_label = Gtk.Label()

        # self.download_button = Gtk.Button(label='Download APK')
        # self.download_button.connect('clicked', self.on_download_button_clicked)

        # self.install_button = Gtk.Button(label='Install APK')
        # self.install_button.connect('clicked', self.on_install_button_clicked)
        # self.install_button.set_sensitive(False)

        # Use Gtk.DropDown instead of Gtk.ComboBoxText
        self.device_list = Gtk.StringList()
        self.device_combo = Gtk.DropDown.new(self.device_list)
        self.device_combo.set_sensitive(False)
        
        # Создание ToastOverlay для уведомлений
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.window_box)
        # self.main_body.append(self.toast_overlay)

        # Словарь для хранения информации об устройствах
        self.device_pages = {}


    def on_device_selected(self, listbox, row):
        if row:
            device_serial = row.get_name()
            self.show_device_page(device_serial)

    def show_device_page(self, device_serial):
        if device_serial in self.device_pages:
            page = self.device_pages[device_serial]
        else:
            device_info = self.devices_info[device_serial]
            page = self.create_device_page(device_info)
            self.device_pages[device_serial] = page
            self.main_body.set_child(page)
        # self.main_body.set_visible_child(page)
        
    def create_device_page(self, device_info):
        # Создание страницы устройства
        device_serial = device_info['Serial Number']
        device_model = device_info['Model']
        device_manufacturer = device_info['Manufacturer']
        alvr_version = device_info['ALVR Version']
        android_version = device_info['Android Version']
        image_path = self.get_device_image_path(device_model)
        
        # Banner for unauthorized device
        self.unauthorized_banner = Adw.Banner()
        self.unauthorized_banner.set_title(
            _("Device not authorized! Allow USB connection on the device"))
        self.unauthorized_banner.set_button_label(_("Show how"))
        self.unauthorized_banner.set_revealed(False)
        # self.unauthorized_banner.connect('clicked', self.on_show_how_clicked, device_model)

        self.right_side.add_top_bar(self.unauthorized_banner)
        
        # Основной контейнер
        # device_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        # device_page.set_margin_top(10)
        # device_page.set_margin_bottom(10)
        # device_page.set_margin_start(10)
        # device_page.set_margin_end(10)
        
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        device_box.set_margin_top(20)

        # Изображение устройства
        # device_image = Gtk.Image.new_from_file(image_path)
        # device_image.set_pixel_size(128)
        # device_page.append(device_image)

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
        alvr_label = Gtk.Label(label="ALVR")
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

        # Create the Build version label
        build_version_label_label = Gtk.Label(label=_("Build version:"))
        build_version_label_label.set_halign(Gtk.Align.START)
        build_version_label = Gtk.Label(label="SQ3A.22.A1")
        build_version_label.set_halign(Gtk.Align.START)

        # Attach the new labels to the grid
        device_version_grid.attach(android_version_label_label, 0, 1, 1, 1)
        device_version_grid.attach(android_version_label, 1, 1, 1, 1)
        device_version_grid.attach(build_version_label_label, 0, 2, 1, 1)
        device_version_grid.attach(build_version_label, 1, 2, 1, 1)

        # Add the new labels to the device text box

        # Attach the labels to the grid
        device_version_grid.attach(alvr_label, 0, 0, 1, 1)
        device_version_grid.attach(version_label, 1, 0, 1, 1)

        # Add the grid to the device text box
        version_label.set_halign(Gtk.Align.START)
        device_text_box.append(device_name_label)
        device_text_box.append(device_version_grid)
        device_info_box.append(device_text_box)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Статус APK
        # apk_status_label = Gtk.Label()
        # device_page.append(apk_status_label)
        # self.update_apk_status_label(version_label, device_serial)
        

        # Кнопка установки APK
        install_button = Gtk.Button(label=_("Install"))
        install_button.add_css_class("suggested-action")
        install_button.set_size_request(100, 30)
        install_button.connect('clicked', self.on_install_button_clicked, device_serial)
        
        
        
        # install_button = Gtk.Button(label="Установить ALVR")
        # install_button.connect('clicked', self.on_install_button_clicked, device_serial)
        # device_page.append(install_button)
        
        button_box.append(self.install_button)

        # Кнопка "Показать как"
        # show_how_button = Gtk.Button(label="Показать как")
        # show_how_button.connect('clicked', self.on_show_how_clicked, device_model)
        # device_page.append(show_how_button)
        
        self.progress_bar = Gtk.ProgressBar()
        # self.progress_bar.set_margin_top(-8)
        # self.progress_bar.set_visible(False)
        self.progress_bar.set_text("123")
        button_box.append(self.progress_bar)

        # Кнопка "Стриминг"
        streaming_button = Gtk.Button(label=_("Streaming"))
        streaming_button.connect('clicked', self.on_streaming_button_clicked, device_serial)
        button_box.append(streaming_button)
        
                
        
        usb_button = Gtk.Button(label=_("USB Connection"))
        # usb_button.add_css_class("destructive-action")
        usb_button.set_size_request(100, 30)

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

        # Apply the custom style to the button
        usb_button.add_css_class("green")

        button_box.append(usb_button)
        
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
        wifi_switch = Adw.SwitchRow(title=_("Automatically connect via USB"),
                         subtitle=_("Automatically prepare the device for USB connection instead of Wi-Fi"))
        wifi_switch.set_active(self.user_config.get('devices', {}).get(device_serial, {}).get('wifi_enabled', False))
        # wifi_switch.connect('state-set', self.on_wifi_switch_toggled, device_serial)
        settings_group.add(wifi_switch)

        # Add the settings group to the main device box
        device_box.append(settings_group)

        # Переключатель Wi-Fi
        # wifi_switch = Gtk.Switch()
        # wifi_switch.set_active(self.user_config.get('devices', {}).get(device_serial, {}).get('wifi_enabled', False))
        # wifi_switch.connect('state-set', self.on_wifi_switch_toggled, device_serial)
        # wifi_row = Adw.ActionRow(title="Использовать Wi-Fi", subtitle="Переключение соединения на Wi-Fi")
        # wifi_row.add_suffix(wifi_switch)
        # device_box.append(wifi_row)

        # Wrap the device box in an AdwClamp
        clamped_device_box = Adw.Clamp(child=device_box)

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
            instruction_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            instruction_window.set_child(instruction_box)

            for step in instructions['steps']:
                step_label = Gtk.Label(label=step['text'])
                instruction_box.append(step_label)
                if 'image' in step:
                    step_image = Gtk.Image.new_from_file(step['image'])
                    instruction_box.append(step_image)

            instruction_window.present()
        else:
            toast = Adw.Toast.new("Инструкция недоступна")
            self.toast_overlay.add_toast(toast)


    def on_streaming_button_clicked(self, button, device_serial):
        # Запуск scrcpy с возможностью изменения параметра --crop
        self.start_scrcpy(device_serial)


    def start_scrcpy(self, device_serial):
        # Получение настроек scrcpy из конфигурации
        device_settings = self.user_config.get('devices', {}).get(device_serial, {})
        use_crop = device_settings.get('use_crop', False)
        crop_params = device_settings.get('crop_params', '')

        # Формирование команды для запуска scrcpy с передачей серийного номера устройства
        scrcpy_command = ['scrcpy', '-s', device_serial]  # Добавляем опцию -s для выбора устройства
        if use_crop and crop_params:
            scrcpy_command.extend(['--crop', crop_params])

        # Запуск scrcpy с указанным серийным номером устройства
        try:
            subprocess.Popen(scrcpy_command)
        except Exception as e:
            print(f"Ошибка при запуске scrcpy: {e}")


    def on_wifi_switch_toggled(self, switch, state, device_serial):
        # Переключение соединения на Wi-Fi
        if state:
            self.connect_device_wifi(device_serial)
        else:
            self.disconnect_device_wifi(device_serial)
        # Сохранение настройки
        self.user_config.setdefault('devices', {}).setdefault(device_serial, {})['wifi_enabled'] = state
        self.save_user_config()

    def connect_device_wifi(self, device_serial):
        # Подключение устройства по Wi-Fi через adb
        subprocess.run(['adb', '-s', device_serial, 'shell', 'svc', 'wifi', 'enable'])
        toast = Adw.Toast.new("Устройство подключено по Wi-Fi")
        self.toast_overlay.add_toast(toast)

    def disconnect_device_wifi(self, device_serial):
        # Отключение устройства от Wi-Fi
        subprocess.run(['adb', '-s', device_serial, 'shell', 'svc', 'wifi', 'disable'])
        toast = Adw.Toast.new("Устройство отключено от Wi-Fi")
        self.toast_overlay.add_toast(toast)

    
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

    def check_apk_status(self):
        if os.path.exists(self.APK_FILE) and os.path.exists(self.INFO_FILE):
            self.apk_status_label.set_text(_('APK Status: Downloaded'))
            self.download_button.set_label(_('Re-download APK'))
            self.install_button.set_sensitive(True)
        else:
            self.apk_status_label.set_text(_('APK Status: Not Downloaded'))
            self.download_button.set_label(_('Download APK'))
            self.install_button.set_sensitive(False)

    def on_download_button_clicked(self, _):
        self.download_button.set_sensitive(False)
        self.install_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0)
        self.progress_bar.set_text('')
        self.install_status_label.set_text(_('Downloading APK...'))

        # Start download in a separate thread
        self.download_thread = threading.Thread(target=self.download_apk)
        self.download_thread.start()

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
        return False  # Stop calling this function

    def on_download_complete(self):
        self.progress_bar.set_visible(False)
        self.check_apk_status()
        self.install_status_label.set_text('APK Downloaded.')
        self.download_button.set_sensitive(True)
        if len(self.devices) > 0:
            self.install_button.set_sensitive(True)
        return False

    def on_download_error(self, message):
        self.progress_bar.set_visible(False)
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK, text='Download Error')
        dialog.set_body(
            f'An error occurred while downloading the APK:\n{message}')
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.show()
        self.install_status_label.set_text('Download Error.')
        self.download_button.set_sensitive(True)
        self.install_button.set_sensitive(False)
        return False

    def start_adb_monitor(self):
        self.devices_info = {}
        self.adb_monitor_id = GLib.timeout_add(1000, self.check_adb_devices)

    def check_adb_devices(self):
        try:
            result = subprocess.check_output(['adb', 'devices'], text=True)
            lines = result.strip().split('\n')[1:]  # Пропускаем первую строку
            devices = [line.split('\t') for line in lines if line.strip()]
            connected_serials = [device[0] for device in devices if device[1] == 'device']

            # Обновление списка устройств
            current_serials = set(self.devices_info.keys())
            new_serials = set(connected_serials) - current_serials
            removed_serials = current_serials - set(connected_serials)

            for serial in new_serials:
                device_info = get_device_info(serial)  # Передаём серийный номер устройства
                self.devices_info[serial] = device_info
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
        row = create_list_device(model, f"Serial: {serial}", image_path)
        row.set_name(serial)
        self.list.append(row)
        toast = Adw.Toast.new(f"Устройство {model} подключено")
        self.toast_overlay.add_toast(toast)


    def remove_device_from_sidebar(self, serial):
        # Удаление устройства из боковой панели
        for row in self.list.get_children():
            if row.get_name() == serial:
                self.list.remove(row)
                break
        toast = Adw.Toast.new(f"Устройство отключено")
        self.toast_overlay.add_toast(toast)

    def on_install_button_clicked(self, _):
        self.progress_bar.set_visible(True)
        if not os.path.exists(self.APK_FILE):
            self.download_apk()

        index = self.device_combo.get_selected()

        device_id = self.devices[index][0]
        status = self.devices[index][1]
        if status == 'unauthorized':
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='Device Unauthorized')
            dialog.set_markup(
                _('Device is unauthorized. Please authorize on your device.'))
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return
        elif status != 'device':
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='Device Not Ready')
            dialog.set_markup(
                f'Device {device_id} is not ready for installation.')
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return

        # Check if ALVR is already installed and get its version
        try:
            package_info = subprocess.getoutput(
                f'adb -s {device_id} shell dumpsys package {APK_PACKAGE_NAME}')
            version_installed = None
            for line in package_info.splitlines():
                if 'versionName=' in line:
                    version_installed = line.strip().split('versionName=')[1]
                    break
        except Exception:
            version_installed = None
            
            
            

            
        def on_install_dialog_response(self, dialog, response):
            if response != 'yes':
                return

        # if version_installed:
        #     message = _('ALVR version {version_installed} is already installed.\nDo you want to reinstall it?' if version_installed ==
        #                 self.VERSION else 'ALVR version {version_installed} is installed.\nDo you want to update to version {self.VERSION}?').format(version_installed=version_installed, self=self)
        #     heading = _('ALVR Already Installed' if version_installed ==
        #                 self.VERSION else 'Update Available')

        #     dialog = Adw.MessageDialog(
        #         transient_for=self,
        #         body=message,
        #         heading=heading,
        #         body_use_markup=True,
        #     )
        #     dialog.add_response('cancel', _("Cancel"))
        #     dialog.add_response('yes', _('Yes'))
        #     dialog.set_response_appearance(
        #         'yes', Adw.ResponseAppearance.SUGGESTED)
        #     dialog.connect('response', on_install_dialog_response)
        #     dialog.present()

        self.install_button.set_sensitive(False)
        self.download_button.set_sensitive(False)
        self.install_status_label.set_text(_('Installing APK...'))
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
        self.install_status_label.set_text('APK Installed Successfully.')
        
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK, text='Installation Complete')
        dialog.set_markup('ALVR client installed successfully.')
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.show()
        
        self.install_button.set_sensitive(True)
        self.download_button.set_sensitive(True)
        return False

    def on_install_error(self, message):
        if hasattr(self, 'progress_timeout_id') and self.progress_timeout_id:
            GLib.source_remove(self.progress_timeout_id)
            self.progress_timeout_id = None
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text('')
        self.install_status_label.set_text('Installation Error.')
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK, text='Installation Error')
        dialog.set_markup(
            f'An error occurred while installing the APK:\n{message}')
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.show()
        self.install_button.set_sensitive(True)
        self.download_button.set_sensitive(True)
        return False

    def show_details_window(self, _):
        try:
            device_info = get_device_info()
            window = Gtk.Window(title=_("Device Details"))
            window.set_transient_for(self)
            window.set_modal(True)
            window.set_default_size(400, 300)
            window.set_resizable(False)

            grid = Gtk.Grid()
            grid.set_valign(Gtk.Align.CENTER)
            grid.set_halign(Gtk.Align.CENTER)
            grid.set_column_spacing(10)
            grid.set_row_spacing(10)
            grid.set_margin_top(10)
            grid.set_margin_bottom(10)
            grid.set_margin_start(10)
            grid.set_margin_end(10)

            device_label = Gtk.Label(label=device_info)
            device_label.set_halign(Gtk.Align.START)
            grid.attach(device_label, 0, 0, 2, 1)

            version_label = Gtk.Label(label="ALVR Version: 20.11.1")
            version_label.set_halign(Gtk.Align.START)
            grid.attach(version_label, 0, 1, 2, 1)

            android_version_label = Gtk.Label(label="Android Version: 12")
            android_version_label.set_halign(Gtk.Align.START)
            grid.attach(android_version_label, 0, 2, 2, 1)

            build_version_label = Gtk.Label(label="Build Version: SQ3A.22.A1")
            build_version_label.set_halign(Gtk.Align.START)
            grid.attach(build_version_label, 0, 3, 2, 1)

            close_button = Gtk.Button(label="Close")
            close_button.connect('clicked', lambda b: window.destroy())
            grid.attach(close_button, 0, 4, 2, 1)

            clamped_grid = Adw.Clamp(child=grid)
            window.set_child(clamped_grid)

            window.present()

            print('Device Info:\n' + '\n'.join(
                [f"{key}: {value}" for key, value in device_info.items()]))
        except Exception as e:
            print(f"Device Info: Error fetching info: {e}")


def main():
    app = ALVRInstaller()
    app.run(sys.argv)

if __name__ == '__main__':
    main()
