import re
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw

def create_list_device(name, version, image_path):
    action_row = Adw.ActionRow()
    action_row.set_title(name)
    ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$')

    if ip_pattern.match(version):
        last_octet = '.' + version.split('.')[-1].split(':')[0]
        version = f"WiFi: {last_octet}"
    else:
        version = f"USB: {version}"
    action_row.set_subtitle(version)

    image = Gtk.Image.new_from_file(image_path)
    image.set_pixel_size(32)
    action_row.add_prefix(image)

    return action_row
