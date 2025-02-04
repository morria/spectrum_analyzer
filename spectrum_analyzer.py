#!/usr/bin/env python3
import sys
import curses
import numpy as np
import time
import threading
import logging
from spectrum_analyzer import hackrf_sweep, transform_coordinates
from math import ceil

# Constants
FRAME_RATE = 16
SPECTRUM_HEIGHT = 5
DEBUG_HEIGHT = 1
LABEL_SPACING = 8  # Spacing between frequency labels (6 characters label + 2 space)

def init_colors():
    """Initializes color pairs for spectrum visualization."""
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)  # Min power
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)  # Max power

def get_color(power: float):
    """Maps power levels to corresponding color pairs."""
    min_power=-100
    max_power=0
    normalized = int(np.interp(power, [min_power, max_power], [1, 6]))
    # logging.info(f"{power}:{normalized}")
    return curses.color_pair(normalized)

def spectrum_analyzer(stdscr, frequency_power_generator, stop_event):
    """Main function handling spectrum visualization and ncurses display."""
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(1)  # Enable non-blocking input
    init_colors()
    max_y, max_x = stdscr.getmaxyx()
    time_series_height = max(max_y - DEBUG_HEIGHT - SPECTRUM_HEIGHT, 0)

    spectrum_win    = stdscr.subwin(SPECTRUM_HEIGHT,    max_x, 0,                       0)
    time_series_win = stdscr.subwin(time_series_height, max_x, SPECTRUM_HEIGHT,         0)

    time_series = []
    last_update_time = time.time()
    frame_interval = 1 / FRAME_RATE

    try:
        for timestamp, frequency_power_map in frequency_power_generator:
            current_time = time.time()

            # Store samples in time series before drawing
            time_series.insert(0, frequency_power_map)
            if len(time_series) > time_series_height - 2:
                time_series.pop()

            # Only update the display at frame rate intervals
            if current_time - last_update_time < frame_interval:
                continue
            last_update_time = current_time

            spectrum_win.box()
            spectrum_win.addstr(0, 2, " Spectrograph ")

            latest_data = time_series[0] if time_series else {}
            remapped_data = transform_coordinates.remap_x(latest_data, max_x - 2)
            sorted_x = sorted(remapped_data.keys())
            sorted_powers = [remapped_data[freq] for freq in sorted_x]
            mapped_indices = np.linspace(1, max_x - 2, len(sorted_x)).astype(int)
            normalized_powers = np.interp(sorted_powers, [-80, -20], [0, SPECTRUM_HEIGHT - 2])

            charmap = {
                8.0/8.0: '\u2588',
                7.0/8.0: '\u2587',
                6.0/8.0: '\u2586',
                5.0/8.0: '\u2585',
                4.0/8.0: '\u2584',
                3.0/8.0: '\u2583',
                2.0/8.0: '\u2582',
                1.0/8.0: '\u2581',
            }

            max_height = SPECTRUM_HEIGHT - 2
            for i, index in enumerate(mapped_indices):
                height = int(normalized_powers[i]*8)/8
                for y in range(int(ceil(height))):
                    c = charmap[min(height-y, 1.0)]
                    spectrum_win.addch(SPECTRUM_HEIGHT - 2 - y, index, c, get_color(sorted_powers[i]))
                for y in range(int(ceil(height)), max_height):
                    spectrum_win.addch(SPECTRUM_HEIGHT - 2 - y, index, ' ', get_color(sorted_powers[i]))

            # Draw frequency labels under the spectrograph
            label_positions = range(1, max_x - 6, LABEL_SPACING)
            sorted_frequencies = sorted(latest_data.keys())
            label_frequencies = np.linspace(sorted_frequencies[0]/1000000, sorted_frequencies[-1]/1000000, len(label_positions))
            for pos, freq in zip(label_positions, label_frequencies):
                spectrum_win.addstr(SPECTRUM_HEIGHT - 1, pos, f"{freq:.2f}")

            # Update time series visualization
            time_series_win.box()
            time_series_win.addstr(0, 2, " Time Series ")

            c = '\u2588'
            for row, data in enumerate(time_series[:time_series_height - 2]):
                sorted_x = sorted(data.keys())
                sorted_powers = [data[freq] for freq in sorted_x]
                mapped_indices = np.linspace(1, max_x - 2, len(sorted_x)).astype(int)

                for i, index in enumerate(mapped_indices):
                    time_series_win.addch(row + 1, index, c, get_color(sorted_powers[i]))

            stdscr.refresh()
            spectrum_win.refresh()
            time_series_win.refresh()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        stop_event.set()
        print("\n")

if __name__ == "__main__":
    stop_event = threading.Event()

    logging.basicConfig(
        filename='debug.log',
        filemode='a',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        curses.wrapper(
            spectrum_analyzer,
            hackrf_sweep.frequency_power_generator(),
            stop_event
        )
    finally:
        stop_event.set()
