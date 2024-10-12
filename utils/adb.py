import subprocess

APK_PACKAGE_NAME = 'alvr.client.stable'

def get_device_info(device_serial):
    try:
        device_info = {}

        # Get model
        model = subprocess.check_output(
            ['adb', '-s', device_serial, 'shell', 'getprop', 'ro.product.model'], text=True).strip()
        device_info['Model'] = model

        # Get manufacturer
        manufacturer = subprocess.check_output(
            ['adb', '-s', device_serial, 'shell', 'getprop', 'ro.product.manufacturer'], text=True).strip()
        device_info['Manufacturer'] = manufacturer

        # Get Android version
        android_version = subprocess.check_output(
            ['adb', '-s', device_serial, 'shell', 'getprop', 'ro.build.version.release'], text=True).strip()
        device_info['Android Version'] = android_version

        # Get build version
        build_version = subprocess.check_output(
            ['adb', '-s', device_serial, 'shell', 'getprop', 'ro.build.display.id'], text=True).strip()
        device_info['Build Version'] = build_version

        # Get serial number (можно также использовать переданный device_serial)
        serial_number = subprocess.check_output(
            ['adb', '-s', device_serial, 'get-serialno'], text=True).strip()
        device_info['Serial Number'] = serial_number
        
        package_info = subprocess.run(
            ['adb', '-s', device_serial, 'shell', 'dumpsys', 'package', APK_PACKAGE_NAME],
            stdout=subprocess.PIPE, text=True
        ).stdout
        version_installed = None
        for line in package_info.splitlines():
            if 'versionName=' in line:
                version_installed = line.strip().split('versionName=')[1]
                break
        if version_installed:
            device_info['ALVR Version'] = version_installed
        else:
            device_info['ALVR Version'] = None
        

        print('Device Info:\n' + '\n'.join(
            [f"{key}: {value}" for key, value in device_info.items()]))

        return device_info

    except Exception as e:
        print(f"Device Info: Error fetching info: {e}")

        return None
