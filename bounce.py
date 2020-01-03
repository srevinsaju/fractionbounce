# -*- coding: utf-8 -*-
# Copyright (c) 2011-14, Walter Bender
# Copyright (c) 2011, Paulina Clares, Chris Rowe
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

# The challenges are arrays:
# [a fraction to display on the ball,
#  the number of segments in the bar,
#  the number of times this challenge has been played]

CHALLENGES = [[['1/2', 2, 0], ['1/3', 3, 0], ['1/4', 4, 0],
               ['2/4', 4, 0], ['2/3', 3, 0], ['3/4', 4, 0]],
              [['1/8', 8, 0], ['2/8', 8, 0], ['3/8', 8, 0],
               ['4/8', 8, 0], ['5/8', 8, 0], ['6/8', 8, 0],
               ['7/8', 8, 0]],
              [['1/6', 6, 0], ['2/6', 6, 0], ['3/6', 6, 0],
               ['4/6', 6, 0], ['5/6', 6, 0]],
              [['1/5', 10, 0], ['2/5', 10, 0], ['3/5', 10, 0],
               ['4/5', 10, 0]],
              [['1/10', 10, 0], ['2/10', 10, 0], ['3/10', 10, 0],
               ['4/10', 10, 0], ['5/10', 10, 0], ['6/10', 10, 0],
               ['7/10', 10, 0], ['8/10', 10, 0], ['9/10', 10, 0]],
              [['1/12', 12, 0], ['2/12', 12, 0], ['3/12', 12, 0],
               ['4/12', 12, 0], ['3/12', 12, 0], ['6/12', 12, 0],
               ['7/12', 12, 0], ['8/12', 12, 0], ['9/12', 12, 0],
               ['10/12', 12, 0], ['11/12', 12, 0]],
              [['1/16', 4, 0], ['2/16', 4, 0], ['3/16', 4, 0],
               ['4/16', 4, 0], ['5/16', 4, 0], ['6/16', 4, 0],
               ['7/16', 4, 0], ['8/16', 4, 0], ['9/16', 4, 0],
               ['10/16', 4, 0], ['11/16', 4, 0], ['12/16', 4, 0],
               ['13/16', 4, 0], ['14/16', 4, 0], ['15/16', 4, 0]]]

REWARD_HEIGHT = 25
STEPS = 100.  # number of time steps per bounce rise and fall
STEP_PAUSE = 50  # milliseconds between steps
BOUNCE_PAUSE = 3000  # milliseconds between bounces
DX = 10  # starting step size for horizontal movement
DDX = 1.25  # acceleration during keypress
ACCELEROMETER_DEVICE = '/sys/devices/platform/lis3lv02d/position'
CRASH = 'crash.ogg'  # wrong answer sound
LAUGH = 'bottle.ogg'  # correct answer sound
BUBBLES = 'bubbles.ogg'  # Easter Egg sound

import os
import subprocess
from random import uniform

from gi.repository import GLib, Gtk, Gdk, GdkPixbuf

from svg_utils import (svg_header, svg_footer, svg_rect, svg_str_to_pixbuf,
                       svg_from_file)
from aplay import aplay

from ball import Ball
from bar import Bar, BAR_HEIGHT

from gettext import gettext as _

import logging
_logger = logging.getLogger('fractionbounce-activity')

from sugar3 import profile
COLORS = profile.get_color().to_string().split(',')
from sugar3.graphics import style
GRID_CELL_SIZE = style.GRID_CELL_SIZE

from sprites import Sprites, Sprite


def _is_tablet_mode():
    if not os.path.exists('/dev/input/event4'):
        return False
    try:
        output = subprocess.call(
            ['evtest', '--query', '/dev/input/event4', 'EV_SW',
             'SW_TABLET_MODE'])
    except (OSError, subprocess.CalledProcessError):
        return False
    if str(output) == '10':
        return True
    return False


class Bounce():
    ''' The Bounce class is used to define the ball and the user
    interaction. '''

    def __init__(self, canvas, path, parent=None):
        ''' Initialize the canvas and set up the callbacks. '''
        self._activity = parent
        self._fraction = None
        self._path = path

        if parent is None:        # Starting from command line
            self._sugar = False
        else:                     # Starting from Sugar
            self._sugar = True

        self._canvas = canvas
        self._canvas.grab_focus()

        self._canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._canvas.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK)
        self._canvas.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self._canvas.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self._canvas.add_events(Gdk.EventMask.KEY_RELEASE_MASK)
        self._canvas.connect('draw', self.__draw_cb)
        self._canvas.connect('button-press-event', self._button_press_cb)
        self._canvas.connect('button-release-event', self._button_release_cb)
        self._canvas.connect('key-press-event', self._keypress_cb)
        self._canvas.connect('key-release-event', self._keyrelease_cb)
        self._canvas.set_can_focus(True)
        self._canvas.grab_focus()

        self._sprites = Sprites(self._canvas)

        self._width = Gdk.Screen.width()
        self._height = Gdk.Screen.height() - GRID_CELL_SIZE
        self._scale = Gdk.Screen.height() / 900.0

        self._step_sid = None  # repeating timeout between steps of ball move
        self._bounce_sid = None  # one-off timeout between bounces
        self.buddies = []  # used for sharing
        self._my_turn = False
        self.select_a_fraction = False

        self._easter_egg = int(uniform(1, 100))

        # Find paths to sound files
        self._path_to_success = os.path.join(path, LAUGH)
        self._path_to_failure = os.path.join(path, CRASH)
        self._path_to_bubbles = os.path.join(path, BUBBLES)

        self._create_sprites(path)

        self.mode = 'fractions'

        self._challenge = 0
        self._expert = False
        self._challenges = []
        for challenge in CHALLENGES[self._challenge]:
            self._challenges.append(challenge)
        self._fraction = 0.5  # the target of the current challenge
        self._label = '1/2'  # the label
        self.count = 0  # number of bounces played
        self._correct = 0  # number of correct answers
        self._press = None  # sprite under mouse click
        self._new_bounce = False
        self._n = 0
        self._accelerometer = self._check_accelerometer()
        self._accel_index = 0
        self._accel_flip = False
        self._accel_xy = [0, 0]
        self._guess_orientation()

        self._dx = 0.  # ball horizontal trajectory
        # acceleration (with dampening)
        self._ddy = (6.67 * self._height) / (STEPS * STEPS)
        self._dy = self._ddy * (1 - STEPS) / 2.  # initial step size

        if self._sugar:
            if _is_tablet_mode():
                self._activity.reset_label(
                    _('Click the ball to start. Rock the computer left '
                      'and right to move the ball.'))
            else:
                self._activity.reset_label(
                    _('Click the ball to start. Then use the arrow keys to '
                      'move the ball.'))

        self._keyrelease_id = None

    def _check_accelerometer(self):
        return os.path.exists(ACCELEROMETER_DEVICE) and _is_tablet_mode()

    def configure_cb(self, event):
        self._width = Gdk.Screen.width()
        self._height = Gdk.Screen.height() - GRID_CELL_SIZE
        self._scale = Gdk.Screen.height() / 900.0

        # We need to resize the backgrounds
        width, height = self._calc_background_size()
        for bg in list(self._backgrounds.keys()):
            if bg == 'custom':
                path = self._custom_dsobject
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    path, width, height)
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    os.path.join(self._path, 'images', bg),
                    width, height)
            if Gdk.Screen.height() > Gdk.Screen.width():
                pixbuf = self._crop_to_portrait(pixbuf)

            self._backgrounds[bg] = pixbuf

        self._background = Sprite(self._sprites, 0, 0,
                                  self._backgrounds[self._current_bg])
        self._background.set_layer(-100)
        self._background.type = 'background'

        # and resize and reposition the bars
        self.bar.resize_all()
        self.bar.show_bar(2)
        self._current_bar = self.bar.get_bar(2)

        # Calculate a new accerlation based on screen height.
        self._ddy = (6.67 * self._height) / (STEPS * STEPS)

        self._guess_orientation()

    def _create_sprites(self, path):
        ''' Create all of the sprites we'll need '''
        self.smiley_graphic = svg_str_to_pixbuf(svg_from_file(
            os.path.join(path, 'images', 'smiley.svg')))

        self.frown_graphic = svg_str_to_pixbuf(svg_from_file(
            os.path.join(path, 'images', 'frown.svg')))

        self.blank_graphic = svg_str_to_pixbuf(
            svg_header(REWARD_HEIGHT, REWARD_HEIGHT, 1.0) +
            svg_rect(REWARD_HEIGHT, REWARD_HEIGHT, 5, 5, 0, 0,
                     'none', 'none') +
            svg_footer())

        self.ball = Ball(self._sprites,
                         os.path.join(path, 'images', 'soccerball.svg'))
        self._current_frame = 0

        self.bar = Bar(self._sprites, self.ball.width(), COLORS)
        self._current_bar = self.bar.get_bar(2)

        self.ball_y_max = \
            self.bar.bar_y() - self.ball.height() + int(BAR_HEIGHT / 2.)
        self.ball.move_ball((int((self._width - self.ball.width()) // 2),
                             self.ball_y_max))

        self._backgrounds = {}
        width, height = self._calc_background_size()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            os.path.join(path, 'images', 'grass_background.png'),
            width, height)
        if Gdk.Screen.height() > Gdk.Screen.width():
            pixbuf = self._crop_to_portrait(pixbuf)

        self._backgrounds['grass_background.png'] = pixbuf

        self._background = Sprite(self._sprites, 0, 0, pixbuf)
        self._background.set_layer(-100)
        self._background.type = 'background'
        self._current_bg = 'grass_background.png'

    def _crop_to_portrait(self, pixbuf):
        tmp = GdkPixbuf.Pixbuf.new(0, True, 8, Gdk.Screen.width(),
                                   Gdk.Screen.height())
        x = int(Gdk.Screen.height() // 3)
        pixbuf.copy_area(x, 0, Gdk.Screen.width(), Gdk.Screen.height(),
                         tmp, 0, 0)
        return tmp

    def _calc_background_size(self):
        if Gdk.Screen.height() > Gdk.Screen.width():
            height = Gdk.Screen.height()
            return int(4 * height // 3), height
        else:
            width = Gdk.Screen.width()
            return width, int(3 * width // 4)

    def new_background_from_image(self, path, dsobject=None):
        if path is None:
            path = dsobject
        width, height = self._calc_background_size()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            path, width, height)

        if Gdk.Screen.height() > Gdk.Screen.width():
            pixbuf = self._crop_to_portrait(pixbuf)

        self._backgrounds['custom'] = pixbuf
        self.set_background('custom')
        self._custom_dsobject = dsobject
        self._current_bg = 'custom'

    def set_background(self, name):
        if name not in self._backgrounds:
            width, height = self._calc_background_size()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                os.path.join(self._path, 'images', name), width, height)
            if Gdk.Screen.height() > Gdk.Screen.width():
                pixbuf = self._crop_to_portrait(pixbuf)
            self._backgrounds[name] = pixbuf
        self._background.set_image(self._backgrounds[name])
        self.bar.mark.hide()
        self._current_bar.hide()
        self.ball.ball.hide()
        self.ball.ball.set_layer(3)
        self._current_bar.set_layer(2)
        self.bar.mark.set_layer(1)
        self._current_bg = name
        self._canvas.queue_draw()

    def pause(self):
        ''' Pause play when visibility changes '''
        if self._step_sid is not None:
            GLib.source_remove(self._step_sid)
            self._step_sid = None

        if self._bounce_sid is not None:
            GLib.source_remove(self._bounce_sid)
            self._bounce_sid = None

    def we_are_sharing(self):
        ''' If there is more than one buddy, we are sharing. '''
        if len(self.buddies) > 1:
            return True

    def its_my_turn(self):
        ''' When sharing, it is your turn... '''
        GLib.timeout_add(1000, self._take_a_turn)

    def _take_a_turn(self):
        ''' On your turn, choose a fraction. '''
        self._my_turn = True
        self.select_a_fraction = True
        self._activity.set_player_on_toolbar(
            self._activity.nick, self._activity.key)
        self._activity.reset_label(
            _("Click on the bar to choose a fraction."))

    def its_their_turn(self, nick, key):
        ''' When sharing, it is nick's turn... '''
        GLib.timeout_add(1000, self._wait_your_turn, nick, key)

    def _wait_your_turn(self, nick, key):
        ''' Wait for nick to choose a fraction. '''
        self._my_turn = False
        self._activity.set_player_on_toolbar(nick, key)
        self._activity.reset_label(
            _('Waiting for %(buddy)s') % {'buddy': nick})

    def play_a_fraction(self, fraction):
        ''' Play this fraction '''
        fraction_is_new = True
        for i, c in enumerate(self._challenges):
            if c[0] == fraction:
                fraction_is_new = False
                self._n = i
                break
        if fraction_is_new:
            self.add_fraction(fraction)
            self._n = len(self._challenges)
        self._choose_a_fraction()
        self._start_step()

    def _button_press_cb(self, win, event):
        ''' Callback to handle the button presses '''
        win.grab_focus()
        x, y = list(map(int, event.get_coords()))
        self._press = self._sprites.find_sprite((x, y))
        return True

    def _button_release_cb(self, win, event):
        ''' Callback to handle the button releases '''
        win.grab_focus()
        x, y = list(map(int, event.get_coords()))
        if self._press is not None:
            if self.we_are_sharing():
                if self.select_a_fraction and self._press == self._current_bar:
                    # Find the fraction closest to the click
                    fraction = self._search_challenges(
                        (x - self.bar.bar_x()) / float(self.bar.width()))
                    self.select_a_fraction = False
                    self._activity.send_a_fraction(fraction)
                    self.play_a_fraction(fraction)
            else:
                if self._step_sid is None and \
                   self._bounce_sid is None and \
                   self._press == self.ball.ball:
                    self._choose_a_fraction()
                    self._start_step()
        return True

    def _search_challenges(self, f):
        ''' Find the fraction which is closest to f in the list. '''
        dist = 1.
        closest = '1/2'
        for c in self._challenges:
            numden = c[0].split('/')
            delta = abs((float(numden[0]) / float(numden[1])) - f)
            if delta <= dist:
                dist = delta
                closest = c[0]
        return closest

    def _guess_orientation(self):
        if self._accelerometer:
            fh = open(ACCELEROMETER_DEVICE)
            string = fh.read()
            fh.close()
            xyz = string[1:-2].split(',')
            x = int(xyz[0])
            y = int(xyz[1])
            self._accel_xy = [x, y]
            if abs(x) > abs(y):
                self._accel_index = 1  # Portrait mode
                self._accel_flip = x > 0
            else:
                self._accel_index = 0  # Landscape mode
                self._accel_flip = y < 0

    def _defer_bounce(self, ms):
        ''' Pause and then start the ball again '''
        self._bounce_sid = GLib.timeout_add(ms, self._bounce)

    def _bounce(self):
        ''' Start the ball again '''
        self._accelerometer = self._check_accelerometer()
        self._start_step()
        self._bounce_sid = None
        return False

    def _start_step(self):
        ''' Start the ball and keep moving until boundary conditions '''
        if self._step():
            self._step_sid = GLib.timeout_add(STEP_PAUSE, self._step)

    def _step(self):
        ''' Move the ball once and test boundary conditions '''
        if self._new_bounce:
            self.bar.mark.move((0, self._height))  # hide the mark
            if not self.we_are_sharing():
                self._choose_a_fraction()
            self._new_bounce = False
            self._dy = self._ddy * (1 - STEPS) / 2  # initial step size

        if self._accelerometer:
            self._guess_orientation()
            self._dx = float(self._accel_xy[self._accel_index]) / 18.
            if self._accel_flip:
                self._dx *= -1

        if self.ball.ball_x() + self._dx > 0 and \
           self.ball.ball_x() + self._dx < self._width - self.ball.width():
            self.ball.move_ball_relative((int(self._dx), int(self._dy)))
        else:
            self.ball.move_ball_relative((0, int(self._dy)))

        # speed up ball in x while key is pressed
        self._dx *= DDX

        # accelerate in y
        self._dy += self._ddy

        # Calculate a new ball_y_max depending on the x position
        self.ball_y_max = \
            self.bar.bar_y() - self.ball.height() + self._wedge_offset()

        if self.ball.ball_y() >= self.ball_y_max:
            # hit the bottom
            self.ball.move_ball((self.ball.ball_x(), self.ball_y_max))
            self._test()
            self._new_bounce = True

            if self.we_are_sharing():
                if self._my_turn:
                    # Let the next player know it is their turn.
                    i = (self.buddies.index(
                        [self._activity.nick, self._activity.key]) + 1) % \
                        len(self.buddies)
                    [nick, key] = self.buddies[i]
                    self.its_their_turn(nick, key)
                    self._activity.send_event('t', self.buddies[i])
            else:
                if not self.we_are_sharing() and self._easter_egg_test():
                    self._animate()
                else:
                    ms = max(STEP_PAUSE,
                             BOUNCE_PAUSE - self.count * STEP_PAUSE)
                    self._defer_bounce(ms)
            self._step_sid = None
            return False
        else:
            return True

    def _wedge_offset(self):
        return int(BAR_HEIGHT * (1 - (self.ball.ball_x() /
                                      float(self.bar.width()))))

    def _mark_offset(self, x):
        return int(BAR_HEIGHT * (1 - (x / float(self.bar.width())))) - 12

    def _animate(self):
        ''' A little Easter Egg just for fun. '''
        if self._new_bounce:
            self._dy = self._ddy * (1 - STEPS) / 2  # initial step size
            self._new_bounce = False
            self._current_frame = 0
            self._frame_counter = 0
            self.ball.move_frame(self._current_frame,
                                 (self.ball.ball_x(), self.ball.ball_y()))
            self.ball.move_ball((self.ball.ball_x(), self._height))
            aplay.play(self._path_to_bubbles)

        if self._accelerometer:
            fh = open(ACCELEROMETER_DEVICE)
            string = fh.read()
            xyz = string[1:-2].split(',')
            self._dx = float(xyz[0]) / 18.
            fh.close()
        else:
            self._dx = uniform(-int(DX * self._scale), int(DX * self._scale))
        self.ball.move_frame_relative(
            self._current_frame, (int(self._dx), int(self._dy)))
        self._dy += self._ddy

        self._frame_counter += 1
        self._current_frame = self.ball.next_frame(self._frame_counter)

        if self.ball.frame_y(self._current_frame) >= self.ball_y_max:
            # hit the bottom
            self.ball.move_ball((self.ball.ball_x(), self.ball_y_max))
            self.ball.hide_frames()
            self._test(easter_egg=True)
            self._new_bounce = True
            self._defer_bounce(BOUNCE_PAUSE)
        else:
            GLib.timeout_add(STEP_PAUSE, self._animate)

    def add_fraction(self, string):
        ''' Add a new challenge; set bar to 2x demominator '''
        numden = string.split('/', 2)
        self._challenges.append([string, int(numden[1]), 0])

    def _get_new_fraction(self):
        ''' Select a new fraction challenge from the table '''
        if not self.we_are_sharing():
            n = int(uniform(0, len(self._challenges)))
        else:
            n = self._n
        fstr = self._challenges[n][0]
        if '/' in fstr:  # fraction
            numden = fstr.split('/', 2)
            fraction = float(numden[0].strip()) / float(numden[1].strip())
        elif '%' in fstr:  # percentage
            fraction = float(fstr.strip().strip('%').strip()) / 100.
        else:  # To do: add support for decimals (using locale)
            _logger.debug('Could not parse challenge (%s)', fstr)
            fstr = '1/2'
            fraction = 0.5
        return fraction, fstr, n

    def _choose_a_fraction(self):
        ''' choose a new fraction and set the corresponding bar '''
        # Don't repeat the same fraction twice in a row
        fraction, fstr, n = self._get_new_fraction()
        if not self.we_are_sharing():
            while fraction == self._fraction:
                fraction, fstr, n = self._get_new_fraction()

        self._fraction = fraction
        self._n = n
        if self.mode == 'percents':
            self._label = str(int(self._fraction * 100 + 0.5)) + '%'
        else:  # percentage
            self._label = fstr
        if self.mode == 'sectors':
            self.ball.new_ball_from_fraction(self._fraction)

        if not Gdk.Screen.width() < 1024:
            self._activity.reset_label(
                _('Bounce the ball to a position '
                  '%(fraction)s of the way from the left side of the bar.')
                % {'fraction': self._label})
        else:
            self._activity.reset_label(_('Bounce the ball to %(fraction)s')
                                       % {'fraction': self._label})

        self.ball.ball.set_label(self._label)

        self.bar.hide_bars()
        if self._expert:  # Show two-segment bar in expert mode
            nseg = 2
        else:
            if self.mode == 'percents':
                nseg = 10
            else:
                nseg = self._challenges[self._n][1]
        # generate new bar on demand
        self._current_bar = self.bar.get_bar(nseg)
        self.bar.show_bar(nseg)

    def _easter_egg_test(self):
        ''' Test to see if we show the Easter Egg '''
        delta = self.ball.width() / 8
        x = self.ball.ball_x() + self.ball.width() / 2
        f = self.bar.width() * self._easter_egg / 100.
        if x > f - delta and x < f + delta:
            return True
        else:
            return False

    def _test(self, easter_egg=False):
        ''' Test to see if we estimated correctly '''
        if self._expert:
            delta = self.ball.width() / 6
        else:
            delta = self.ball.width() / 3

        x = self.ball.ball_x() + self.ball.width() / 2
        f = int(self._fraction * self.bar.width())
        self.bar.mark.move((int(f - self.bar.mark_width() / 2),
                            int(self.bar.bar_y() + self._mark_offset(f))))
        if self._challenges[self._n][2] == 0:  # label the column
            spr = Sprite(self._sprites, 0, 0, self.blank_graphic)
            spr.set_label(self._label)
            spr.move((int(self._n * 27), 0))
            spr.set_layer(-1)
        self._challenges[self._n][2] += 1
        if x > f - delta and x < f + delta:
            spr = Sprite(self._sprites, 0, 0, self.smiley_graphic)
            self._correct += 1
            aplay.play(self._path_to_success)
        else:
            spr = Sprite(self._sprites, 0, 0, self.frown_graphic)
            aplay.play(self._path_to_failure)

        spr.move((int(self._n * 27), int(self._challenges[self._n][2] * 27)))
        spr.set_layer(-1)

        # after enough correct answers, up the difficulty
        if self._correct == len(self._challenges) * 2:
            self._challenge += 1
            if self._challenge < len(CHALLENGES):
                for challenge in CHALLENGES[self._challenge]:
                    self._challenges.append(challenge)
            else:
                self._expert = True

        self.count += 1
        self._dx = 0.  # stop horizontal movement between bounces

    def _keypress_cb(self, area, event):
        ''' Keypress: moving the slides with the arrow keys '''
        k = Gdk.keyval_name(event.keyval)
        if k in ['KP_Page_Down', 'KP_Home', 'h', 'Left', 'KP_Left']:
            self._dx = -DX * self._scale
        elif k in ['KP_Page_Up', 'KP_End', 'l', 'Right', 'KP_Right']:
            self._dx = DX * self._scale
        elif k in ['Return']:
            if self._step_sid:
                self._dy = - self._ddy * (1 - STEPS) * 2.
        else:
            self._dx = 0.
        if self._accel_flip:
            self._dx = -self._dx
        return True

    def _keyrelease_cb(self, area, event):
        ''' Keyrelease: stop horizontal movement '''

        def timer_cb():
            self._dx = 0.
            self._keyrelease_id = None
            return False

        if self._keyrelease_id is not None:
            GLib.source_remove(self._keyrelease_id)
        self._keyrelease_id = GLib.timeout_add(100, timer_cb)

        return True

    def __draw_cb(self, canvas, cr):
        self._sprites.redraw_sprites(cr=cr)

    def _destroy_cb(self, win, event):
        ''' Callback to handle quit '''
        Gtk.main_quit()
