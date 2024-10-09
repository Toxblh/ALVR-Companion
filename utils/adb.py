import subprocess

def get_device_info():
    try:
        device_info = {}

        # Get model
        model = subprocess.check_output(
            ['adb', 'shell', 'getprop', 'ro.product.model'], text=True).strip()
        device_info['Model'] = model

        # Get manufacturer
        manufacturer = subprocess.check_output(
            ['adb', 'shell', 'getprop', 'ro.product.manufacturer'], text=True).strip()
        device_info['Manufacturer'] = manufacturer

        # Get Android version
        android_version = subprocess.check_output(
            ['adb', 'shell', 'getprop', 'ro.build.version.release'], text=True).strip()
        device_info['Android Version'] = android_version

        # Get build version
        build_version = subprocess.check_output(
            ['adb', 'shell', 'getprop', 'ro.build.display.id'], text=True).strip()
        device_info['Build Version'] = build_version

        # Get serial number
        serial_number = subprocess.check_output(
            ['adb', 'get-serialno'], text=True).strip()
        device_info['Serial Number'] = serial_number

        print('Device Info:\n' + '\n'.join(
            [f"{key}: {value}" for key, value in device_info.items()]))
        
        return device_info
    
    except Exception as e:
        print(f"Device Info: Error fetching info: {e}")

        return None
