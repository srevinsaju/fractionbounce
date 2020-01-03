# -*- coding: utf-8 -*-
# Copyright (c) 2011-14, Walter Bender
# Copyright (c) 2011 Paulina Clares, Chris Rowe
# Ported to GTK3 - 2012:
# Ignacio Rodríguez <ignaciorodriguez@sugarlabs.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk

from sugar3 import profile
from sugar3.activity import activity
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.toolbarbox import ToolbarButton
from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics.radiotoolbutton import RadioToolButton
from sugar3.graphics.alert import NotifyAlert
from sugar3.graphics import style

from sugarapp.widgets import SugarCompatibleActivity

from collabwrapper import CollabWrapper

from gettext import gettext as _

import logging
_logger = logging.getLogger('fractionbounce-activity')

from utils import chooser
from svg_utils import svg_str_to_pixbuf, generate_xo_svg

from bounce import Bounce
from aplay import aplay

BALLDICT = {'basketball': [_('basketball'), 'wood'],
            'soccerball': [_('soccer ball'), 'grass'],
            'rugbyball': [_('rugby ball'), 'grass'],
            'bowlingball': [_('bowling ball'), 'wood'],
            'beachball': [_('beachball'), 'sand'],
            'feather': [_('feather'), 'clouds'],
            'custom': [_('user defined'), None]}
BGDICT = {'grass': [_('grass'), 'grass_background.png'],
          'wood': [_('wood'), 'parquet_background.png'],
          'clouds': [_('clouds'), 'feather_background.png'],
          'sand': [_('sand'), 'beach_background.png'],
          'custom': [_('user defined'), None]}


class FractionBounceActivity(SugarCompatibleActivity):

    def __init__(self, handle):
        ''' Initiate activity. '''
        super(FractionBounceActivity, self).__init__(handle)

        self.nick = profile.get_nick_name()
        self.key = profile.get_pubkey()
        if profile.get_color() is not None:
            self._colors = profile.get_color().to_string().split(',')
        else:
            self._colors = ['#A0FFA0', '#FF8080']

        self.max_participants = 4  # sharing
        self._ignore_messages = False  # activity was asked to stop

        self._setup_toolbars()
        canvas = self._setup_canvas()

        # Read any custom fractions from the project metadata
        if 'custom' in self.metadata:
            custom = self.metadata['custom']
        else:
            custom = None

        self._current_ball = 'soccerball'

        self._toolbar_was_expanded = False

        # Initialize the canvas
        self._bounce_window = Bounce(canvas, activity.get_bundle_path(), self)

        Gdk.Screen.get_default().connect('size-changed', self._configure_cb)

        # Restore any custom fractions
        if custom is not None:
            fractions = custom.split(',')
            for f in fractions:
                self._bounce_window.add_fraction(f)

        self._bounce_window.buddies.append([self.nick, self.key])
        self._player_colors = [self._colors]
        self._player_pixbufs = [
            svg_str_to_pixbuf(generate_xo_svg(scale=0.8, colors=self._colors))
        ]

        def on_activity_joined_cb(me):
            logging.debug('activity joined')
            self._player.set_from_pixbuf(self._player_pixbufs[0])

        self.connect('joined', on_activity_joined_cb)

        def on_activity_shared_cb(me):
            logging.debug('activity shared')
            self._player.set_from_pixbuf(self._player_pixbufs[0])
            self._label.set_label(_('Wait for others to join.'))

        self.connect('shared', on_activity_shared_cb)

        self._collab = CollabWrapper(self)

        if self.shared_activity:
            # We're joining
            if not self.get_shared():
                self._label.set_label(_('Wait for the sharer to start.'))

        actions = {
            'j': self._new_joiner,
            'b': self._buddy_list,
            'f': self._receive_a_fraction,
            't': self._take_a_turn,
            'l': self._buddy_left,
        }

        def on_message_cb(collab, buddy, msg):
            logging.debug('on_message_cb buddy %r msg %r' % (buddy, msg))
            if not self._ignore_messages:
                actions[msg.get('action')](msg.get('data'))

        self._collab.connect('message', on_message_cb)

        def on_joined_cb(collab, msg):
            logging.debug('joined')
            self.send_event('j', [self.nick, self.key, self._colors])

        self._collab.connect('joined', on_joined_cb, 'joined')

        def on_buddy_joined_cb(collab, buddy, msg):
            logging.debug('on_buddy_joined_cb buddy %r' % (buddy.props.nick))

        self._collab.connect('buddy_joined', on_buddy_joined_cb,
                             'buddy_joined')

        def on_buddy_left_cb(collab, buddy, msg):
            logging.debug('on_buddy_left_cb buddy %r' % (buddy.props.nick))
            # synthesise a buddy left message in case it did not
            # arrive; this can happen when the peer terminates
            # unexpectedly, or the network connection between the
            # peers fails.
            self._buddy_left([buddy.props.nick, buddy.props.key])

        self._collab.connect('buddy_left', on_buddy_left_cb, 'buddy_left')

        self._collab.setup()

    def set_data(self, blob):
        pass

    def get_data(self):
        return None

    def close(self, **kwargs):
        self._bounce_window.pause()
        aplay.close()
        SugarCompatibleActivity.close(self, **kwargs)

    def _configure_cb(self, event):
        if Gdk.Screen.width() < 1024:
            self._label.set_size_request(275, -1)
            self._label.set_label('')
            self._separator.set_expand(False)
        else:
            self._label.set_size_request(500, -1)
            self._separator.set_expand(True)

        self._bounce_window.configure_cb(event)
        if self._toolbar_expanded():
            self._bounce_window.bar.bump_bars('up')
            self._bounce_window.ball.ball.move_relative(
                (0, -style.GRID_CELL_SIZE))

    def _toolbar_expanded(self):
        if self._activity_button.is_expanded():
            return True
        elif self._custom_toolbar_button.is_expanded():
            return True
        return False

    def _update_graphics(self, widget):
        # We need to catch opening and closing of toolbars and ignore
        # switching between open toolbars.
        if self._toolbar_expanded():
            if not self._toolbar_was_expanded:
                self._bounce_window.bar.bump_bars('up')
                self._bounce_window.ball.ball.move_relative(
                    (0, -style.GRID_CELL_SIZE))
                self._toolbar_was_expanded = True
        else:
            if self._toolbar_was_expanded:
                self._bounce_window.bar.bump_bars('down')
                self._bounce_window.ball.ball.move_relative(
                    (0, style.GRID_CELL_SIZE))
                self._toolbar_was_expanded = False

    def _setup_toolbars(self):
        custom_toolbar = Gtk.Toolbar()
        toolbox = ToolbarBox()
        self._toolbar = toolbox.toolbar
        self._activity_button = ActivityToolbarButton(self)
        self._activity_button.connect('clicked', self._update_graphics)
        self._toolbar.insert(self._activity_button, 0)
        self._activity_button.show()

        self._custom_toolbar_button = ToolbarButton(
            label=_('Custom'),
            page=custom_toolbar,
            icon_name='view-source')
        self._custom_toolbar_button.connect('clicked', self._update_graphics)
        custom_toolbar.show()
        self._toolbar.insert(self._custom_toolbar_button, -1)
        self._custom_toolbar_button.show()

        self._load_standard_buttons(self._toolbar)

        self._separator = Gtk.SeparatorToolItem()
        self._separator.props.draw = False
        self._separator.set_expand(True)
        self._toolbar.insert(self._separator, -1)
        self._separator.show()

        stop_button = StopButton(self)
        stop_button.props.accelerator = _('<Ctrl>Q')
        self._toolbar.insert(stop_button, -1)
        stop_button.show()
        self.set_toolbar_box(toolbox)
        toolbox.show()

        self._load_custom_buttons(custom_toolbar)

    def _load_standard_buttons(self, toolbar):
        fraction_button = RadioToolButton(group=None)
        fraction_button.set_icon_name('fraction')
        fraction_button.set_tooltip(_('fractions'))
        fraction_button.connect('clicked', self._fraction_cb)
        toolbar.insert(fraction_button, -1)
        fraction_button.show()

        sector_button = RadioToolButton(group=fraction_button)
        sector_button.set_icon_name('sector')
        sector_button.set_tooltip(_('sectors'))
        sector_button.connect('clicked', self._sector_cb)
        toolbar.insert(sector_button, -1)
        sector_button.show()

        percent_button = RadioToolButton(group=fraction_button)
        percent_button.set_icon_name('percent')
        percent_button.set_tooltip(_('percents'))
        percent_button.connect('clicked', self._percent_cb)
        toolbar.insert(percent_button, -1)
        percent_button.show()

        self._player = Gtk.Image()
        self._player.set_from_pixbuf(svg_str_to_pixbuf(
            generate_xo_svg(scale=0.8, colors=['#282828', '#282828'])))
        self._player.set_tooltip_text(self.nick)
        toolitem = Gtk.ToolItem()
        toolitem.add(self._player)
        self._player.show()
        toolbar.insert(toolitem, -1)
        toolitem.show()

        self._label = Gtk.Label(_("Click the ball to start."))
        self._label.set_line_wrap(True)
        if Gdk.Screen.width() < 1024:
            self._label.set_size_request(275, -1)
        else:
            self._label.set_size_request(500, -1)
        self.toolitem = Gtk.ToolItem()
        self.toolitem.add(self._label)
        self._label.show()
        toolbar.insert(self.toolitem, -1)
        self.toolitem.show()

    def _load_custom_buttons(self, toolbar):
        self.numerator = Gtk.Entry()
        self.numerator.set_text('')
        self.numerator.set_tooltip_text(_('numerator'))
        self.numerator.set_width_chars(3)
        toolitem = Gtk.ToolItem()
        toolitem.add(self.numerator)
        self.numerator.show()
        toolbar.insert(toolitem, -1)
        toolitem.show()

        label = Gtk.Label('   /   ')
        toolitem = Gtk.ToolItem()
        toolitem.add(label)
        label.show()
        toolbar.insert(toolitem, -1)
        toolitem.show()

        self.denominator = Gtk.Entry()
        self.denominator.set_text('')
        self.denominator.set_tooltip_text(_('denominator'))
        self.denominator.set_width_chars(3)
        toolitem = Gtk.ToolItem()
        toolitem.add(self.denominator)
        self.denominator.show()
        toolbar.insert(toolitem, -1)
        toolitem.show()

        button = ToolButton('list-add')
        button.set_tooltip(_('add new fraction'))
        button.props.sensitive = True
        button.props.accelerator = 'Return'
        button.connect('clicked', self._add_fraction_cb)
        toolbar.insert(button, -1)
        button.show()

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(False)
        toolbar.insert(separator, -1)
        separator.show()

        button = ToolButton('soccerball')
        button.set_tooltip(_('choose a ball'))
        button.props.sensitive = True
        button.connect('clicked', self._button_palette_cb)
        toolbar.insert(button, -1)
        button.show()
        self._ball_palette = button.get_palette()
        button_grid = Gtk.Grid()
        row = 0
        for ball in list(BALLDICT.keys()):
            if ball == 'custom':
                button = ToolButton('view-source')
            else:
                button = ToolButton(ball)
            button.connect('clicked', self._load_ball_cb, None, ball)
            eventbox = Gtk.EventBox()
            eventbox.connect('button_press_event', self._load_ball_cb,
                             ball)
            label = Gtk.Label(BALLDICT[ball][0])
            eventbox.add(label)
            label.show()
            button_grid.attach(button, 0, row, 1, 1)
            button.show()
            button_grid.attach(eventbox, 1, row, 1, 1)
            eventbox.show()
            row += 1
        self._ball_palette.set_content(button_grid)
        button_grid.show()

        button = ToolButton('insert-picture')
        button.set_tooltip(_('choose a background'))
        button.props.sensitive = True
        button.connect('clicked', self._button_palette_cb)
        toolbar.insert(button, -1)
        button.show()
        self._bg_palette = button.get_palette()
        button_grid = Gtk.Grid()
        row = 0
        for bg in list(BGDICT.keys()):
            if bg == 'custom':
                button = ToolButton('view-source')
            else:
                button = ToolButton(bg)
            button.connect('clicked', self._load_bg_cb, None, bg)
            eventbox = Gtk.EventBox()
            eventbox.connect('button_press_event', self._load_bg_cb, bg)
            label = Gtk.Label(BGDICT[bg][0])
            eventbox.add(label)
            label.show()
            button_grid.attach(button, 0, row, 1, 1)
            button.show()
            button_grid.attach(eventbox, 1, row, 1, 1)
            eventbox.show()
            row += 1
        self._bg_palette.set_content(button_grid)
        button_grid.show()

    def _button_palette_cb(self, button):
        palette = button.get_palette()
        if palette:
            if not palette.is_up():
                palette.popup(immediate=True)
            else:
                palette.popdown(immediate=True)

    def can_close(self):
        # Let everyone know we are leaving...
        if hasattr(self, '_bounce_window') and \
           self._bounce_window.we_are_sharing():
            self._ignore_messages = True
            self.send_event('l', [self.nick, self.key])
        return True

    def _setup_canvas(self):
        canvas = Gtk.DrawingArea()
        canvas.set_size_request(Gdk.Screen.width(),
                                Gdk.Screen.height())
        self.set_canvas(canvas)
        canvas.show()
        return canvas

    def _load_bg_cb(self, widget, event, bg):
        self._bg_palette.popdown(immediate=True)
        if bg == 'custom':
            chooser(self, 'Image', self._new_background_from_journal)
        else:
            self._bounce_window.set_background(BGDICT[bg][1])

    def _load_ball_cb(self, widget, event, ball):
        self._ball_palette.popdown(immediate=True)
        if ball == 'custom':
            chooser(self, 'Image', self._new_ball_from_journal)
        else:
            self._bounce_window.ball.new_ball(os.path.join(
                activity.get_bundle_path(), 'images', ball + '.svg'))
            self._bounce_window.set_background(BGDICT[BALLDICT[ball][1]][1])
        self._current_ball = ball

    def _reset_ball(self):
        ''' If we switch back from sector mode, we need to restore the ball '''
        if self._bounce_window.mode != 'sectors':
            return

        if self._current_ball == 'custom':  # TODO: Reload custom ball
            self._current_ball = 'soccerball'
        self._bounce_window.ball.new_ball(os.path.join(
            activity.get_bundle_path(), 'images', self._current_ball + '.svg'))

    def _new_ball_from_journal(self, dsobject):
        ''' Load an image from the Journal. '''
        self._bounce_window.ball.new_ball_from_image(
            dsobject,
            os.path.join(activity.get_activity_root(), 'custom.png'))

    def _new_background_from_journal(self, dsobject):
        ''' Load an image from the Journal. '''
        self._bounce_window.new_background_from_image(None, dsobject=dsobject)

    def _fraction_cb(self, arg=None):
        ''' Set fraction mode '''
        self._reset_ball()
        self._bounce_window.mode = 'fractions'

    def _percent_cb(self, arg=None):
        ''' Set percent mode '''
        self._reset_ball()
        self._bounce_window.mode = 'percents'

    def _sector_cb(self, arg=None):
        ''' Set sector mode '''
        self._bounce_window.mode = 'sectors'

    def _add_fraction_cb(self, arg=None):
        ''' Read entries and add a fraction to the list '''
        try:
            numerator = int(self.numerator.get_text().strip())
        except ValueError:
            self.numerator.set_text('NAN')
            numerator = 0
        try:
            denominator = int(self.denominator.get_text().strip())
        except ValueError:
            self.denominator.set_text('NAN')
            denominator = 1
        if denominator == 0:
            self.denominator.set_text('ZDE')
        if numerator > denominator:
            numerator = 0
        if numerator > 0 and denominator > 1:
            fraction = '%d/%d' % (numerator, denominator)
            self._bounce_window.add_fraction(fraction)
            if 'custom' in self.metadata:  # Save to Journal
                self.metadata['custom'] = '%s,%s' % (
                    self.metadata['custom'], fraction)
            else:
                self.metadata['custom'] = fraction

            self.alert(
                _('New fraction'),
                _('Your fraction, %s, has been added to the program' %
                  (fraction)))

    def reset_label(self, label):
        ''' update the challenge label '''
        self._label.set_label(label)

    def alert(self, title, text=None):
        alert = NotifyAlert(timeout=5)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)

    # Collaboration-related methods

    def _buddy_left(self, payload):
        [nick, key] = payload
        self._label.set_label(nick + ' ' + _('has left.'))
        if self._collab.props.leader:
            self._remove_player(nick, key)
            self.send_event(
                'b', [self._bounce_window.buddies, self._player_colors])
            # Restart from sharer's turn
            self._bounce_window.its_my_turn()

    def _new_joiner(self, payload):
        ''' Someone has joined; sharer adds them to the buddy list. '''
        [nick, key, colors] = payload
        self._label.set_label(nick + ' ' + _('has joined.'))
        if self._collab.props.leader:
            self._append_player(nick, key, colors)
            self.send_event(
                'b', [self._bounce_window.buddies, self._player_colors])
            if self._bounce_window.count == 0:  # Haven't started yet...
                self._bounce_window.its_my_turn()

    def _remove_player(self, nick, key):
        if [nick, key] in self._bounce_window.buddies:
            i = self._bounce_window.buddies.index([nick, key])
            self._bounce_window.buddies.remove([nick, key])
            self._player_colors.remove(self._player_colors[i])
            self._player_pixbufs.remove(self._player_pixbufs[i])

    def _append_player(self, nick, key, colors):
        ''' Keep a list of players, their colors, and an XO pixbuf '''
        if [nick, key] not in self._bounce_window.buddies:
            _logger.debug('appending %s to the buddy list', nick)
            self._bounce_window.buddies.append([nick, key])
            self._player_colors.append([str(colors[0]), str(colors[1])])
            self._player_pixbufs.append(svg_str_to_pixbuf(
                generate_xo_svg(scale=0.8,
                                colors=self._player_colors[-1])))

    def _buddy_list(self, payload):
        '''Sharer sent the updated buddy list, so regenerate internal lists'''
        if not self._collab.props.leader:
            [buddies, colors] = payload
            self._bounce_window.buddies = buddies[:]
            self._player_colors = colors[:]
            self._player_pixbufs = []
            for colors in self._player_colors:
                self._player_pixbufs.append(svg_str_to_pixbuf(
                    generate_xo_svg(scale=0.8,
                                    colors=[str(colors[0]), str(colors[1])])))

    def send_a_fraction(self, fraction):
        ''' Send a fraction to other players. '''
        self.send_event('f', fraction)

    def _receive_a_fraction(self, payload):
        ''' Receive a fraction from another player. '''
        self._bounce_window.play_a_fraction(payload)

    def _take_a_turn(self, payload):
        ''' If it is your turn, take it, otherwise, wait. '''
        [nick, key] = payload
        if [nick, key] == [self.nick, self.key]:
            self._bounce_window.its_my_turn()
        else:
            self._bounce_window.its_their_turn(nick, key)

    def send_event(self, action, data):
        ''' Send event through the tube. '''
        _logger.debug('send_event action=%r data=%r' % (action, data))
        self._collab.post({'action': action, 'data': data})

    def set_player_on_toolbar(self, nick, key):
        ''' Display the XO icon of the player whose turn it is. '''
        i = self._bounce_window.buddies.index([nick, key])
        self._player.set_from_pixbuf(self._player_pixbufs[i])
        self._player.set_tooltip_text(nick)
