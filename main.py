#!/usr/bin/env python3

import sys
import os
import threading
import subprocess
import requests
import platform

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QProgressBar,
                             QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

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


class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class DownloadThread(threading.Thread):
    def __init__(self, url, filepath, signals):
        super().__init__()
        self.url = url
        self.filepath = filepath
        self.signals = signals

    def run(self):
        try:
            response = requests.get(self.url, stream=True)
            total_length = response.headers.get('content-length')

            with open(self.filepath, 'wb') as f:
                if total_length is None:
                    f.write(response.content)
                    self.signals.progress.emit(100)
                else:
                    dl = 0
                    total_length = int(total_length)
                    for data in response.iter_content(chunk_size=4096):
                        dl += len(data)
                        f.write(data)
                        done = int(100 * dl / total_length)
                        self.signals.progress.emit(done)
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class InstallThread(threading.Thread):
    def __init__(self, device_id, apk_path, signals):
        super().__init__()
        self.device_id = device_id
        self.apk_path = apk_path
        self.signals = signals

    def run(self):
        try:
            process = subprocess.Popen(['adb', '-s', self.device_id, 'install', '-r', self.apk_path],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(output.strip())
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))


class ALVRInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.VERSION = get_alvr_version() or ALVR_LATEST
        self.APK_URL = f"https://github.com/alvr-org/ALVR/releases/download/v{self.VERSION}/alvr_client_android.apk"
        self.APK_FILE = f"/tmp/alvr_client_{self.VERSION}.apk"
        self.INFO_FILE = f"/tmp/alvr_client_{self.VERSION}.info"

        self.initUI()
        self.check_apk_status()
        self.start_adb_monitor()
        self.check_usb_forwarding_status()

    def initUI(self):
        self.setWindowTitle('ALVR Installer')

        self.apk_version_label = QLabel(f'APK Version: {get_alvr_version()}')
        self.apk_status_label = QLabel('APK Status: Checking...')
        self.apk_installed_label = QLabel('APK Installed: Checking...')
        self.device_info = QLabel('Device Info: Checking...')
        self.device_status_label = QLabel('Device Status: Checking...')
        self.install_status_label = QLabel('')

        self.download_button = QPushButton('Download APK')
        self.download_button.clicked.connect(self.download_apk)

        self.install_button = QPushButton('Install APK')
        self.install_button.clicked.connect(self.install_apk)
        self.install_button.setEnabled(False)

        self.device_combo = QComboBox()
        self.device_combo.setEnabled(False)

        self.usb_forward_button = QPushButton('Подключение по USB')
        self.usb_forward_button.clicked.connect(self.setup_usb_forwarding)

        self.usb_forward_status_label = QLabel('USB Forwarding: Checking...')

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        hbox = QHBoxLayout()
        hbox.addWidget(self.download_button)
        hbox.addWidget(self.install_button)

        vbox = QVBoxLayout()
        vbox.addWidget(self.apk_version_label)
        vbox.addWidget(self.apk_status_label)
        vbox.addWidget(self.apk_installed_label)
        vbox.addWidget(self.device_info)
        vbox.addWidget(self.device_status_label)
        vbox.addWidget(self.device_combo)
        vbox.addLayout(hbox)
        vbox.addWidget(self.usb_forward_button)
        vbox.addWidget(self.usb_forward_status_label)
        vbox.addWidget(self.progress_bar)
        vbox.addWidget(self.install_status_label)

        self.setLayout(vbox)
        self.resize(400, 250)
        self.show()

    def check_apk_status(self):
        if os.path.exists(self.APK_FILE) and os.path.exists(self.INFO_FILE):
            self.apk_status_label.setText('APK Status: Downloaded')
            self.download_button.setText('Re-download APK')
            self.install_button.setEnabled(True)
        else:
            self.apk_status_label.setText('APK Status: Not Downloaded')
            self.download_button.setText('Download APK')
            self.install_button.setEnabled(False)

    def download_apk(self):
        self.download_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.install_status_label.setText('Downloading APK...')
        self.signals = WorkerSignals()
        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.download_finished)
        self.signals.error.connect(self.download_error)

        self.download_thread = DownloadThread(
            self.APK_URL, self.APK_FILE, self.signals)
        self.download_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def download_finished(self):
        with open(self.INFO_FILE, 'w') as f:
            f.write('Downloaded')
        self.check_apk_status()
        self.install_status_label.setText('APK Downloaded.')
        self.download_button.setEnabled(True)
        self.install_button.setEnabled(True)

    def download_error(self, message):
        QMessageBox.critical(
            self, 'Download Error', f'An error occurred while downloading the APK:\n{message}')
        self.install_status_label.setText('Download Error.')
        self.download_button.setEnabled(True)
        self.install_button.setEnabled(False)

    def start_adb_monitor(self):
        self.adb_timer = QTimer()
        self.adb_timer.timeout.connect(self.check_adb_devices)
        self.adb_timer.timeout.connect(self.check_usb_forwarding_status)
        self.adb_timer.timeout.connect(self.check_installed_alvr_version)
        self.adb_timer.timeout.connect(self.check_device_info)
        self.adb_timer.start(2000)  # Check every 2 seconds

    def check_adb_devices(self):
        try:
            result = subprocess.check_output(['adb', 'devices'], text=True)
            lines = result.strip().split('\n')[1:]  # Skip the first line
            devices = [line.split('\t') for line in lines if line.strip()]
            self.devices = devices
            if not devices:
                self.device_status_label.setText(
                    'Device Status: No devices connected')
                self.device_combo.clear()
                self.device_combo.setEnabled(False)
                self.install_button.setEnabled(False)
            else:
                self.device_combo.clear()
                for device in devices:
                    self.device_combo.addItem(f"{device[0]} ({device[1]})")
                self.device_status_label.setText(
                    f'Device Status: {len(devices)} device(s) connected')
                self.device_combo.setEnabled(True)
                if os.path.exists(self.APK_FILE):
                    self.install_button.setEnabled(True)
                else:
                    self.install_button.setEnabled(False)
        except Exception as e:
            print(f"ADB Error: {e}")
            self.device_status_label.setText(
                'Device Status: Error checking devices')
            self.device_combo.clear()
            self.device_combo.setEnabled(False)
            self.install_button.setEnabled(False)

    def setup_usb_forwarding(self):
        try:
            subprocess.run(['adb', 'forward', 'tcp:9943', 'tcp:9943'])
            subprocess.run(['adb', 'forward', 'tcp:9944', 'tcp:9944'])
            self.check_usb_forwarding_status()
        except Exception as e:
            QMessageBox.critical(self, 'USB Forwarding Error',
                                 f'An error occurred while setting up USB forwarding:\n{e}')

    def check_usb_forwarding_status(self):
        try:
            result = subprocess.check_output(
                ['adb', 'forward', '--list'], text=True)
            if 'tcp:9943' in result and 'tcp:9944' in result:
                self.usb_forward_status_label.setText(
                    'USB Forwarding: Enabled')
            else:
                self.usb_forward_status_label.setText(
                    'USB Forwarding: Not enabled')
        except Exception as e:
            self.usb_forward_status_label.setText(
                'USB Forwarding: Error checking status')
            print(f"USB Forwarding Error: {e}")

    def check_installed_alvr_version(self):
        package_name = "alvr.client.stable"
        try:
            result = subprocess.check_output(
                ['adb', 'shell', 'dumpsys', 'package', package_name],
                text=True
            )
            for line in result.splitlines():
                if 'versionName' in line:
                    self.apk_installed_label.setText(f'APK Installed: {line.split("=")[1].strip()}')
                    return
            self.apk_installed_label.setText('APK Installed: ALVR not installed')
        except Exception as e:
            self.apk_installed_label.setText('APK Installed: Error fetching ALVR version')
            print(f"Error fetching ALVR version: {e}")

    def check_device_info(self):
        try:
            device_info = {}

            # Get model
            model = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.product.model'], text=True).strip()
            device_info['Model'] = model

            # Get manufacturer
            manufacturer = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.product.manufacturer'], text=True).strip()
            device_info['Manufacturer'] = manufacturer

            # Get Android version
            android_version = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.build.version.release'], text=True).strip()
            device_info['Android Version'] = android_version

            # Get build version
            build_version = subprocess.check_output(['adb', 'shell', 'getprop', 'ro.build.display.id'], text=True).strip()
            device_info['Build Version'] = build_version

            # Get serial number
            serial_number = subprocess.check_output(['adb', 'get-serialno'], text=True).strip()
            device_info['Serial Number'] = serial_number

            self.device_info.setText('Device Info:\n' + '\n'.join(
                [f"{key}: {value}" for key, value in device_info.items()]))
        except Exception as e:
            self.device_info.setText('Device Info: Error fetching info')
            print(f"Device Info: Error fetching info: {e}")
        
    def install_apk(self):
        if not os.path.exists(self.APK_FILE):
            QMessageBox.information(
                self, 'APK Not Downloaded', 'Please download the APK first.')
            return
        index = self.device_combo.currentIndex()
        if index == -1:
            QMessageBox.information(
                self, 'No Device Selected', 'Please select a device.')
            return
        device_id, status = self.devices[index]
        if status == 'unauthorized':
            QMessageBox.information(self, 'Device Unauthorized',
                                    'Device is unauthorized. Please authorize on your device.')
            return
        elif status != 'device':
            QMessageBox.information(self, 'Device Not Ready',
                                    f'Device {device_id} is not ready for installation.')
            return
        self.install_status_label.setText('Installing APK...')
        self.install_button.setEnabled(False)
        self.signals = WorkerSignals()
        self.signals.finished.connect(self.install_finished)
        self.signals.error.connect(self.install_error)

        self.install_thread = InstallThread(
            device_id, self.APK_FILE, self.signals)
        self.install_thread.start()

    def install_finished(self):
        self.install_status_label.setText('APK Installed.')
        self.install_button.setEnabled(True)

    def install_error(self, message):
        QMessageBox.critical(
            self, 'Install Error', f'An error occurred while installing the APK:\n{message}')
        self.install_status_label.setText('Install Error.')
        self.install_button.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    installer = ALVRInstaller()
    sys.exit(app.exec_())
