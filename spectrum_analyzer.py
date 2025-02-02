#!/usr/bin/env python3
import sys
import curses
import numpy as np
import time
import threading
# import queue
import logging
from spectrum_analyzer import hackrf_sweep, transform_coordinates

# Constants
FRAME_RATE = 8  # FPS limit
SPECTRUM_HEIGHT = 6
DEBUG_HEIGHT = 3

def init_colors():
    """Initializes color pairs for spectrum visualization."""
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)  # Min power
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)  # Max power

def get_color(power, min_power=-100, max_power=0):
    """Maps power levels to corresponding color pairs."""
    normalized = int(np.interp(power, [min_power, max_power], [1, 6]))
    return curses.color_pair(normalized)

def spectrum_analyzer(stdscr, frequency_power_generator, stop_event):
    """Main function handling spectrum visualization and ncurses display."""
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(1)  # Enable non-blocking input
    init_colors()
    max_y, max_x = stdscr.getmaxyx()
    time_series_height = max(max_y - DEBUG_HEIGHT - SPECTRUM_HEIGHT, 0)

    stdscr.addstr(0, 0, f"{time_series_height + SPECTRUM_HEIGHT + DEBUG_HEIGHT}")

    spectrum_win    = stdscr.subwin(SPECTRUM_HEIGHT,    max_x, 0,                       0)
    time_series_win = stdscr.subwin(time_series_height, max_x, SPECTRUM_HEIGHT,         0)
    # debug_win       = stdscr.subwin(DEBUG_HEIGHT,       max_x, SPECTRUM_HEIGHT + time_series_height, 0)
    # debug_message = []

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

            spectrum_win.clear()
            spectrum_win.box()
            spectrum_win.addstr(0, 2, " Spectrograph ")

            latest_data = time_series[0] if time_series else {}

            remapped_data = transform_coordinates.remap_x(latest_data, max_x - 2)

            sorted_frequencies = sorted(remapped_data.keys())
            sorted_powers = [remapped_data[freq] for freq in sorted_frequencies]
            mapped_indices = np.linspace(1, max_x - 2, len(sorted_frequencies)).astype(int)
            normalized_powers = np.interp(sorted_powers, [-100, 0], [1, SPECTRUM_HEIGHT - 2])

            for i, index in enumerate(mapped_indices):
                height = int(normalized_powers[i])
                for y in range(height):
                    spectrum_win.addch(SPECTRUM_HEIGHT - 2 - y, index, curses.ACS_CKBOARD, get_color(sorted_powers[i]))

            # Update time series visualization
            time_series_win.clear()
            time_series_win.box()
            time_series_win.addstr(0, 2, " Time Series ")

            for row, data in enumerate(time_series[:time_series_height - 2]):
                sorted_frequencies = sorted(data.keys())
                sorted_powers = [data[freq] for freq in sorted_frequencies]
                mapped_indices = np.linspace(1, max_x - 2, len(sorted_frequencies)).astype(int)

                for i, index in enumerate(mapped_indices):
                    time_series_win.addch(row + 1, index, curses.ACS_CKBOARD, get_color(sorted_powers[i]))

            # debug_win.clear()
            # debug_win.addstr(0, 0, f"{debug_message[:max_x-1]}")

            # Refresh all windows
            stdscr.refresh()
            spectrum_win.refresh()
            time_series_win.refresh()
            # debug_win.refresh()
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

