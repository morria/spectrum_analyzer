#!/usr/bin/env python3
import sys
import curses
import numpy as np
import time
import threading
import logging
import argparse
from spectrum_analyzer import hackrf_sweep, transform_coordinates
from math import ceil, floor

# Default Constants
DEFAULT_FRAME_RATE = 16
DEFAULT_SPECTRUM_HEIGHT = 5
DEFAULT_MIN_POWER = -100.0
DEFAULT_MAX_POWER = -20.0
LABEL_SPACING = 8  # Spacing between frequency labels (6 characters label + 2 space)

def init_colors():
    curses.start_color()
    curses.init_pair(1, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    # Blue is showing up as red for some reason. My terminal is
    # being weird so I'm just going to exclude it.
    # curses.init_pair(2, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)

def get_color(power: float, min_power: float, max_power: float):
    """Maps power levels to corresponding color pairs."""
    # Clamp power to range
    power = max(min_power, min(power, max_power))

    # Map to [1, 6] range inclusive.
    if max_power == min_power:
        normalized = 1
    else:
        normalized = int(6 * (power - min_power) / (max_power - min_power)) + 1
        normalized = max(1, min(6, normalized))

    return curses.color_pair(normalized)

def spectrum_analyzer(stdscr, frequency_power_generator, stop_event, config):
    """Main function handling spectrum visualization and ncurses display."""
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(1)  # Enable non-blocking input
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    init_colors()

    # State variables
    paused = False
    peak_hold = False
    peak_data = {}
    show_help = False
    min_power = config['min_power']
    max_power = config['max_power']

    def init_windows():
        """Initialize or reinitialize windows after resize."""
        max_y, max_x = stdscr.getmaxyx()
        spectrum_height = config['spectrum_height']
        time_series_height = max(max_y - spectrum_height - 1, 0)

        stdscr.clear()
        spectrum_win = stdscr.subwin(spectrum_height, max_x, 0, 0)
        time_series_win = stdscr.subwin(time_series_height, max_x, spectrum_height, 0)
        status_win = stdscr.subwin(1, max_x, max_y - 1, 0)

        return spectrum_win, time_series_win, status_win, max_x, max_y, time_series_height

    spectrum_win, time_series_win, status_win, max_x, max_y, time_series_height = init_windows()
    time_series = []
    last_update_time = time.time()
    frame_interval = 1 / config['fps']

    try:
        for timestamp, frequency_power_map in frequency_power_generator:
            # Handle input (keyboard and mouse)
            try:
                key = stdscr.getch()
                if key == ord('q') or key == ord('Q'):
                    break
                elif key == ord('p') or key == ord('P'):
                    paused = not paused
                elif key == ord('h') or key == ord('H'):
                    show_help = not show_help
                elif key == ord('m') or key == ord('M'):
                    peak_hold = not peak_hold
                    if not peak_hold:
                        peak_data = {}
                elif key == curses.KEY_RESIZE:
                    spectrum_win, time_series_win, status_win, max_x, max_y, time_series_height = init_windows()
                    time_series = time_series[:time_series_height - 2]
                elif key == curses.KEY_MOUSE:
                    try:
                        _, mx, my, _, _ = curses.getmouse()
                        # Mouse clicked - could implement frequency selection here
                    except:
                        pass
            except:
                pass

            if not paused:
                # Store samples in time series before drawing
                time_series.insert(0, frequency_power_map)
                if len(time_series) > time_series_height - 2:
                    time_series.pop()

                # Update peak hold data
                if peak_hold:
                    for freq, power in frequency_power_map.items():
                        peak_data[freq] = max(peak_data.get(freq, float('-inf')), power)

            current_time = time.time()
            # Only update the display at frame rate intervals
            if current_time - last_update_time < frame_interval:
                continue
            last_update_time = current_time

            # Clear windows
            spectrum_win.erase()
            time_series_win.erase()
            status_win.erase()

            if show_help:
                # Display help overlay
                help_lines = [
                    "KEYBOARD SHORTCUTS:",
                    "  q - Quit",
                    "  p - Pause/Resume",
                    "  h - Toggle this help",
                    "  m - Toggle peak hold",
                    "",
                    "Press 'h' to close this help"
                ]
                start_y = max(0, (max_y - len(help_lines)) // 2)
                start_x = max(0, (max_x - 40) // 2)
                for i, line in enumerate(help_lines):
                    if start_y + i < max_y and len(line) < max_x:
                        try:
                            stdscr.addstr(start_y + i, start_x, line, curses.A_REVERSE)
                        except:
                            pass
            else:
                # Draw spectrum visualization
                spectrum_win.box()
                title = " Spectrograph "
                if peak_hold:
                    title += "[PEAK HOLD] "
                if paused:
                    title += "[PAUSED] "
                spectrum_win.addstr(0, 2, title)

                latest_data = time_series[0] if time_series else {}
                if peak_hold and peak_data:
                    display_data = peak_data.copy()
                else:
                    display_data = latest_data

                if display_data:
                    remapped_data = transform_coordinates.remap_x(display_data, max_x - 2)
                    sorted_x = sorted(remapped_data.keys())
                    sorted_powers = [remapped_data[freq] for freq in sorted_x]
                    mapped_indices = np.linspace(1, max_x - 2, len(sorted_x)).astype(int)
                    normalized_powers = np.interp(sorted_powers, [min_power, max_power], [0, config['spectrum_height'] - 2])

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

                    max_height = config['spectrum_height'] - 2
                    for i, index in enumerate(mapped_indices):
                        height = int(normalized_powers[i]*8)/8
                        for y in range(int(ceil(height))):
                            c = charmap[min(height-y, 1.0)]
                            try:
                                spectrum_win.addch(config['spectrum_height'] - 2 - y, index, c,
                                                 get_color(sorted_powers[i], min_power, max_power))
                            except:
                                pass

                    # Draw frequency labels with overlap prevention
                    sorted_frequencies = sorted(display_data.keys())
                    if sorted_frequencies:
                        min_freq = sorted_frequencies[0] / 1000000
                        max_freq = sorted_frequencies[-1] / 1000000

                        # Calculate how many labels we can fit
                        max_labels = max(1, (max_x - 2) // LABEL_SPACING)
                        label_positions = np.linspace(1, max_x - 7, max_labels).astype(int)
                        label_frequencies = np.linspace(min_freq, max_freq, len(label_positions))

                        for pos, freq in zip(label_positions, label_frequencies):
                            try:
                                if pos + 6 < max_x:
                                    spectrum_win.addstr(config['spectrum_height'] - 1, pos, f"{freq:6.2f}")
                            except:
                                pass

                # Update time series visualization
                time_series_win.box()
                time_series_win.addstr(0, 2, " Waterfall ")

                c = '\u2588'
                for row, data in enumerate(time_series[:time_series_height - 2]):
                    if data:
                        sorted_x = sorted(data.keys())
                        sorted_powers = [data[freq] for freq in sorted_x]
                        mapped_indices = np.linspace(1, max_x - 2, len(sorted_x)).astype(int)

                        for i, index in enumerate(mapped_indices):
                            try:
                                time_series_win.addch(row + 1, index, c,
                                                    get_color(sorted_powers[i], min_power, max_power))
                            except:
                                pass

            # Update status line
            status_text = f"Range: {min_power:.0f} to {max_power:.0f} dBm | FPS: {config['fps']} | Press 'h' for help"
            try:
                status_win.addstr(0, 0, status_text[:max_x-1])
            except:
                pass

            stdscr.refresh()
            spectrum_win.refresh()
            time_series_win.refresh()
            status_win.refresh()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        stop_event.set()
        print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Real-time spectrum analyzer for hackrf_sweep output',
        epilog='Example: hackrf_sweep -a 1 -p1 -f 90:102 -w 50000 | ./spectrum_analyzer.py'
    )
    parser.add_argument('--fps', type=int, default=DEFAULT_FRAME_RATE,
                        help=f'Frame rate (default: {DEFAULT_FRAME_RATE})')
    parser.add_argument('--min-power', type=float, default=DEFAULT_MIN_POWER,
                        help=f'Minimum power in dBm (default: {DEFAULT_MIN_POWER})')
    parser.add_argument('--max-power', type=float, default=DEFAULT_MAX_POWER,
                        help=f'Maximum power in dBm (default: {DEFAULT_MAX_POWER})')
    parser.add_argument('--height', type=int, default=DEFAULT_SPECTRUM_HEIGHT,
                        help=f'Spectrograph height in lines (default: {DEFAULT_SPECTRUM_HEIGHT})')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose debug logging')
    parser.add_argument('--log-file', type=str, default='debug.log',
                        help='Debug log file path (default: debug.log)')

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.basicConfig(
            filename=args.log_file,
            filemode='a',
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.info("Starting spectrum analyzer in verbose mode")
        logging.info(f"Configuration: fps={args.fps}, min_power={args.min_power}, "
                    f"max_power={args.max_power}, height={args.height}")
    else:
        # Disable logging if not verbose
        logging.basicConfig(level=logging.CRITICAL)

    # Build configuration dictionary
    config = {
        'fps': args.fps,
        'min_power': args.min_power,
        'max_power': args.max_power,
        'spectrum_height': args.height
    }

    stop_event = threading.Event()

    try:
        curses.wrapper(
            spectrum_analyzer,
            hackrf_sweep.frequency_power_generator(),
            stop_event,
            config
        )
    finally:
        stop_event.set()
