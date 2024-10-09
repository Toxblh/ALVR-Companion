#!/usr/bin/env python3

import os
import sys
import threading
import subprocess

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio

import requests

APP_VERSION = "0.1.1"
ALVR_LATEST = "20.11.1"

def check_command(command):
    """Check if a command can be executed."""
    try:
        # Run the command with --version to see if it exists
        subprocess.check_output([command, '--version'], text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_alvr_version():
    # Check for Arch Linux (pacman)
    if check_command('pacman'):
        try:
            result = subprocess.check_output(
                ['pacman', '-Qi', 'alvr'], text=True)
            for line in result.splitlines():
                if 'Version' in line:
                    return line.split(':')[1].strip()
        except subprocess.CalledProcessError:
            print("Failed to retrieve ALVR version from pacman.")

    # Check for rpm-based systems (rpm)
    if check_command('rpm'):
        try:
            result = subprocess.check_output(['rpm', '-qi', 'alvr'], text=True)
            for line in result.splitlines():
                if 'Version' in line:
                    return line.split(':')[1].strip()
        except subprocess.CalledProcessError:
            print("Failed to retrieve ALVR version from rpm.")

    return None

class ALVRInstaller(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.ALVRInstaller')
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        self.set_title('ALVR Installer')
        self.set_default_size(800, 600)
        
        self.VERSION = get_alvr_version() or ALVR_LATEST
        self.APK_URL = f"https://github.com/alvr-org/ALVR/releases/download/v{self.VERSION}/alvr_client_android.apk"
        self.APK_FILE = f"/tmp/alvr_client_{self.VERSION}.apk"
        self.INFO_FILE = f"/tmp/alvr_client_{self.VERSION}.info"

        self.init_ui()
        self.check_apk_status()
        self.start_adb_monitor()

    def init_ui(self):
        # Create the main vertical box
        self.window_box = Adw.NavigationSplitView()
        self.window_box.set_max_sidebar_width(220)
        self.window_box.set_min_sidebar_width(220)
        self.set_content(self.window_box)

        # Левая боковая панель
        self.sidebar = Adw.NavigationPage()
        self.sidebar.set_title("ALVR Компаньон")

        self.left_side = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        
        menu = Gio.Menu()
        about_item = Gio.MenuItem.new("О программе", "app.about")
        menu.append_item(about_item)
        
        menu_button.set_menu_model(menu)
        header_bar.pack_end(menu_button)
        
        self.left_side.add_top_bar(header_bar)
        
        # Add action for "О программе"
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self.show_about_dialog)
        self.get_application().add_action(action)
        
        self.left_content = Gtk.ScrolledWindow()
        self.left_side.set_content(self.left_content)
        
        self.sidebar.set_child(self.left_side)
        
        
        
        list = Gtk.ListBox()
        list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        list.set_vexpand(True)
        list.set_css_classes(["navigation-sidebar"])
        placeholder = Adw.StatusPage(title="Подключите устройство", icon_name="drive-harddisk-usb-symbolic")
        placeholder.set_css_classes(["compact"])
        list.set_placeholder(placeholder)
        self.left_content.set_child(list)
        
        
        # Элемент списка
        action_row = Adw.ActionRow()
        action_row.set_title("Oculus Quest 2")
        action_row.set_subtitle("APK: 20.11.1")
        
        image = Gtk.Image.new_from_file('./assets/oculusquest2.png')
        image.set_pixel_size(32)
        action_row.add_prefix(image)
        
        list.append(action_row)    
        
        
        # -----Элемент списка------
        action_row1 = Adw.ActionRow()
        action_row1.set_title("Pico 4")
        action_row1.set_subtitle("APK: 20.8.0")
        
        image1 = Gtk.Image.new_from_file('./assets/pico4.png')
        image1.set_pixel_size(32)
        action_row1.add_prefix(image1)
        
        list.append(action_row1)   
        # -----Элемент списка 1 ----
        action_row2 = Adw.ActionRow()
        action_row2.set_title("Lynx R1")
        action_row2.set_subtitle("APK: Не установлен")
        
        image2 = Gtk.Image.new_from_file('./assets/lynxr1.png')
        image2.set_pixel_size(32)
        action_row2.add_prefix(image2)
        
        list.append(action_row2)   
        # -----Элемент списка 2 ----
        
        
        
        
        # Основная правая область контента
        self.content = Adw.NavigationPage()
        self.content.set_title("Устройство")
        
        self.right_side = Adw.ToolbarView()
        self.right_header = Adw.HeaderBar()
        
        more_info = Gtk.Button(label="Показать детали")
        more_info.connect('clicked', self.show_details_window)
        self.right_header.pack_start(more_info)
        
        self.right_side.add_top_bar(self.right_header)
        
        
        self.main_body = Gtk.ScrolledWindow() # Adw.ViewStack()
        self.right_side.set_content(self.main_body)

        self.content.set_child(self.right_side)
        
        # Разделение на боковую панель и основной контент
        self.window_box.set_sidebar(self.sidebar)
        self.window_box.set_content(self.content)
        
        # -------------------------
        
        
        # Презентация устройства
        
        # Banner for unauthorized device
        self.unauthorized_banner = Adw.Banner()
        self.unauthorized_banner.set_title("Устройство не авторизовано! Разрешите подключение по USB на устройстве")
        self.unauthorized_banner.set_button_label("Показать как")
        self.unauthorized_banner.set_revealed(False)

        # Add the banner to the main content
        self.right_side.add_top_bar(self.unauthorized_banner)

        # Create a box to hold the device information and actions
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        device_box.set_margin_top(20)

        # Create a horizontal box for the device image and name
        device_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        device_image = Gtk.Image.new_from_file('./assets/oculusquest2.png')
        device_image.set_pixel_size(128)
        device_image.set_css_classes(["icon", "icon-dropshadow"])
        device_info_box.append(device_image)

        # Create a vertical box for the device name and version
        device_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
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
        android_version_label_label = Gtk.Label(label="Android version:")
        android_version_label_label.add_css_class("description")
        android_version_label_label.set_halign(Gtk.Align.START)
        android_version_label = Gtk.Label(label="12")
        android_version_label.set_halign(Gtk.Align.START)

        # Create the Build version label
        build_version_label_label = Gtk.Label(label="Build version:")
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
        
        install_button = Gtk.Button(label="Установить")
        install_button.add_css_class("suggested-action")
        install_button.set_size_request(100, 30)
        install_button.connect('clicked', self.on_install_button_clicked)

        # Create a progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_top(-8)
        self.progress_bar.set_visible(False)
        

        # Add the button and progress bar to the button box
        button_box.append(install_button)
        button_box.append(self.progress_bar)
        
        usb_button = Gtk.Button(label="USB Подключение")
        usb_button.add_css_class("destructive-action")
        usb_button.set_size_request(100, 30)
        
        button_box.append(install_button)
        button_box.append(usb_button)
        
        # Align the button box to the end (right side)
        device_info_box.append(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True))  # Spacer
        device_info_box.append(button_box)

        # Add the device info box to the main device box
        device_box.append(device_info_box)

        # Create a preferences group for settings
        settings_group = Adw.PreferencesGroup(title="Настройки")

        # Create a row for the auto-update setting
        auto_update_row = Adw.SwitchRow(title="Автоматически обновлять", subtitle="Обновлять ALVR автоматически при подключении")
        settings_group.add(auto_update_row)

        # Create a row for the auto USB connection setting
        auto_usb_row = Adw.SwitchRow(title="Автоматически подключать по USB", subtitle="Подготовливать устройство автоматически для работы по USB вместо Wi-Fi")
        settings_group.add(auto_usb_row)

        # Add the settings group to the main device box
        device_box.append(settings_group)

        # Wrap the device box in an AdwClamp
        clamped_device_box = Adw.Clamp(child=device_box)
        
        self.main_body.set_child(clamped_device_box)
        
        # --- Презентация устройства ---
        
        
        

        self.apk_status_label = Gtk.Label(label='APK Status: Checking...')
        self.device_status_label = Gtk.Label(label='Device Status: Checking...')
        self.install_status_label = Gtk.Label()

        self.download_button = Gtk.Button(label='Download APK')
        self.download_button.connect('clicked', self.on_download_button_clicked)

        self.install_button = Gtk.Button(label='Install APK')
        self.install_button.connect('clicked', self.on_install_button_clicked)
        self.install_button.set_sensitive(False)

        # Use Gtk.DropDown instead of Gtk.ComboBoxText
        self.device_list = Gtk.StringList()
        self.device_combo = Gtk.DropDown.new(self.device_list)
        self.device_combo.set_sensitive(False)

        # self.progress_bar = Gtk.ProgressBar()
        # self.progress_bar.set_show_text(True)

        # Arrange the widgets
        # self.side_panel.append(self.apk_status_label)
        # self.side_panel.append(self.device_status_label)
        # self.side_panel.append(self.device_combo)

        # button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        # button_box.append(self.download_button)
        # button_box.append(self.install_button)
        # self.side_panel.append(button_box)

        # self.side_panel.append(self.progress_bar)
        # self.side_panel.append(self.install_status_label)

    def show_about_dialog(self, action, param):       
        dialog = Adw.AboutDialog()
        dialog.set_application_icon("ru.toxblh.AlvrCompanion")
        dialog.set_application_icon('ru.toxblh.AlvrCompanion')
        dialog.set_application_name("ALVR Companion")
        dialog.set_developer_name("Anton Palgunov (Toxblh)")
        dialog.set_version(APP_VERSION)
        dialog.set_copyright("© 2024 Anton Palgunov (Toxblh)")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_translator_credits("translator-credits")
        dialog.set_issue_url("https://github.com/Toxblh/ALVR-Companion/issues")
        dialog.add_link("GitHub", "https://github.com/Toxblh/ALVR-Companion")
        dialog.add_link("Donate", "https://www.buymeacoffee.com/toxblh")

        dialog.present(self.get_application().get_active_window())

    def check_apk_status(self):
        if os.path.exists(self.APK_FILE) and os.path.exists(self.INFO_FILE):
            self.apk_status_label.set_text('APK Status: Downloaded')
            self.download_button.set_label('Re-download APK')
            self.install_button.set_sensitive(True)
        else:
            self.apk_status_label.set_text('APK Status: Not Downloaded')
            self.download_button.set_label('Download APK')
            self.install_button.set_sensitive(False)

    def on_download_button_clicked(self, button):
        self.download_button.set_sensitive(False)
        self.install_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0)
        self.progress_bar.set_text('')
        self.install_status_label.set_text('Downloading APK...')

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
                    GLib.idle_add(self.update_progress_bar, 1.0, 'Download complete')
                else:
                    dl = 0
                    total_length = int(total_length)
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        fraction = dl / total_length
                        GLib.idle_add(self.update_progress_bar, fraction, f'Downloading... {int(fraction*100)}%')
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
        dialog.set_body(f'An error occurred while downloading the APK:\n{message}')
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.show()
        self.install_status_label.set_text('Download Error.')
        self.download_button.set_sensitive(True)
        self.install_button.set_sensitive(False)
        return False

    def start_adb_monitor(self):
        self.devices = []
        self.adb_monitor_id = GLib.timeout_add(1000, self.check_adb_devices)

    def check_adb_devices(self):
        try:
            result = subprocess.check_output(['adb', 'devices'], text=True)
            lines = result.strip().split('\n')[1:]  # Skip the first line
            devices = [line.split('\t') for line in lines if line.strip()]
            self.devices = devices
            if not devices:
                self.device_status_label.set_text('Device Status: No devices connected')
                self.device_list = Gtk.StringList()
                self.device_combo.set_model(self.device_list)
                self.device_combo.set_sensitive(False)
                self.install_button.set_sensitive(False)
            else:
                device_strings = [f"{device[0]} ({device[1]})" for device in devices]
                self.device_list = Gtk.StringList.new(device_strings)
                self.device_combo.set_model(self.device_list)
                self.device_combo.set_selected(0)
                self.device_status_label.set_text(f'Device Status: {len(devices)} device(s) connected')
                self.device_combo.set_sensitive(True)
                if os.path.exists(self.APK_FILE):
                    self.install_button.set_sensitive(True)
                else:
                    self.install_button.set_sensitive(False)
        except Exception as e:
            print(f"ADB Error: {e}")
            self.device_status_label.set_text('Device Status: Error checking devices')
            self.device_list = Gtk.StringList()
            self.device_combo.set_model(self.device_list)
            self.device_combo.set_sensitive(False)
            self.install_button.set_sensitive(False)
        return True  # Continue calling this function

    def on_install_button_clicked(self, button):
        self.progress_bar.set_visible(True)
        if not os.path.exists(self.APK_FILE):
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='APK Not Downloaded')
            dialog.set_markup('Please download the APK first.')
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return

        index = self.device_combo.get_selected()
        if index == -1:
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='No Device Selected')
            dialog.set_markup('Please select a device.')
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return

        device_id = self.devices[index][0]
        status = self.devices[index][1]
        if status == 'unauthorized':
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='Device Unauthorized')
            dialog.set_markup('Device is unauthorized. Please authorize on your device.')
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return
        elif status != 'device':
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                       buttons=Gtk.ButtonsType.OK, text='Device Not Ready')
            dialog.set_markup(f'Device {device_id} is not ready for installation.')
            dialog.connect('response', lambda d, r: d.destroy())
            dialog.show()
            return

        # Check if ALVR is already installed and get its version
        try:
            package_info = subprocess.getoutput(f'adb -s {device_id} shell dumpsys package com.polygraphene.alvr')
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
            
        if version_installed:
            message = _('ALVR version {version_installed} is already installed.\nDo you want to reinstall it?' if version_installed == self.VERSION else 'ALVR version {version_installed} is installed.\nDo you want to update to version {self.VERSION}?').format(version_installed=version_installed, self=self)
            heading = _('ALVR Already Installed' if version_installed == self.VERSION else 'Update Available')

            dialog = Adw.MessageDialog(
                transient_for=self,
                body=message,
                heading=heading,
                body_use_markup=True,
            )
            dialog.add_response('cancel', _("Cancel"))
            dialog.add_response('yes', _('Yes'))
            dialog.set_response_appearance('yes', Adw.ResponseAppearance.SUGGESTED)
            dialog.connect('response', on_install_dialog_response)
            dialog.present()

        self.install_button.set_sensitive(False)
        self.download_button.set_sensitive(False)
        self.install_status_label.set_text('Installing APK...')
        self.progress_bar.set_fraction(0)
        self.progress_bar.set_text('')

        # Start installation in a separate thread
        self.install_thread = threading.Thread(target=self.install_apk, args=(device_id,))
        self.install_thread.start()

        # Start progress bar animation
        self.progress_timeout_id = GLib.timeout_add(500, self.increment_progress)

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
        dialog.set_markup(f'An error occurred while installing the APK:\n{message}')
        dialog.connect('response', lambda d, r: d.destroy())
        dialog.show()
        self.install_button.set_sensitive(True)
        self.download_button.set_sensitive(True)
        return False
    
    def show_details_window(self, button):
        window = Gtk.Window(title="Device Details")
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

        device_label = Gtk.Label(label="Device: Oculus Quest 2")
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

def main():
    app = ALVRInstaller()
    app.run(sys.argv)

if __name__ == '__main__':
    main()
