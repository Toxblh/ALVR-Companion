import re
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw

def is_ip_value(value):
    ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$')
    return ip_pattern.match(value)

def create_list_device(name, version, image_path, is_wifi):
    action_row = Adw.ActionRow()
    action_row.set_title(name)

    if is_wifi:
        version = f"WiFi: {version}"
    else:
        version = f"USB: {version}"
    action_row.set_subtitle(version)

    image = Gtk.Image.new_from_file(image_path)
    image.set_pixel_size(32)
    action_row.add_prefix(image)

    return action_row
