import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw

def create_list_device(name, version, image_path):
    action_row = Adw.ActionRow()
    action_row.set_title(name)
    action_row.set_subtitle(version)
    
    image = Gtk.Image.new_from_file(image_path)
    image.set_pixel_size(32)
    action_row.add_prefix(image)

    return action_row