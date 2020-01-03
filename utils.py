# -*- coding: utf-8 -*-
# Copyright (c) 2011, Walter Bender
# Ported to gtk 3: Ignacio Rodríguez
# <ignaciorodriguez@sugarlabs.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


from gi.repository import Gtk

from sugarapp.widgets import DesktopOpenChooser

def chooser(parent_window, filter, action):
    """ Choose an object from the datastore and take some action """
    chooser = None
    chooser = DesktopOpenChooser(parent_window)
    chooser.add_filter('.png', 'Portable Network Graphics (.png)')
    chooser.add_filter('.jpg', 'JPG Images (.jpg)')
    chooser.add_filter('.jpeg', 'JPG Images (.jpeg)')
    filepath = chooser.get_filename()
    if filepath is not None:
        action(filepath)
