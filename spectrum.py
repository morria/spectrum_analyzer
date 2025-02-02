#!/usr/bin/env python3
import sys
import curses
import numpy as np

def parse_hackrf_sweep(line):
    """Parse a line from hackrf_sweep output and extract frequency and power."""
    parts = [p.strip() for p in line.strip().split(',')]
    if len(parts) < 7:
        return None, None, None

    try:
        timestamp = parts[1]  # Use time as a grouping key
        freq_start = int(parts[2])
        freq_end = int(parts[3])
        freq_step = float(parts[4])
        powers = list(map(float, parts[6:]))
        frequencies = np.arange(freq_start, freq_end, freq_step)
        return timestamp, frequencies, powers
    except ValueError:
        return None, None, None

def spectrograph(stdscr):
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(1)   # Non-blocking input
    max_y, max_x = stdscr.getmaxyx()
    spectrum = np.zeros(max_x)
    debug_log = ["" for _ in range(3)]
    last_timestamp = None
    all_frequencies = []
    all_powers = []

    while True:
        try:
            line = sys.stdin.readline()
            debug_log.append(f"Read line: {line.strip()}")
            debug_log.pop(0)

            if not line:
                debug_log.append("No input received.")
                debug_log.pop(0)
                continue

            timestamp, frequencies, powers = parse_hackrf_sweep(line)
            if timestamp is None or frequencies is None or powers is None:
                debug_log.append("Invalid input format or parsing error.")
                debug_log.pop(0)
                continue

            if last_timestamp is None:
                last_timestamp = timestamp

            if timestamp == last_timestamp:
                all_frequencies.extend(frequencies)
                all_powers.extend(powers)
            else:
                stdscr.clear()

                min_freq, max_freq = min(all_frequencies), max(all_frequencies)
                min_power, max_power = -100, 0  # dBm range

                debug_log.append(f"Freq range: {min_freq} - {max_freq}, Data points: {len(all_frequencies)}")
                debug_log.pop(0)

                # Draw spectrum panel with box
                spectrum_height = max_y - 6
                spectrum_win = stdscr.subwin(spectrum_height, max_x, 0, 0)
                spectrum_win.box()
                spectrum_win.addstr(0, 2, " Spectrum Display ", curses.A_REVERSE)

                # Map frequencies to screen width
                mapped_indices = np.linspace(1, max_x - 2, len(all_frequencies)).astype(int)
                normalized_powers = np.interp(all_powers, [min_power, max_power], [1, spectrum_height - 2])

                spectrum.fill(0)
                for i, index in enumerate(mapped_indices):
                    spectrum[index] = max(spectrum[index], normalized_powers[i])

                for x in range(1, max_x - 1):
                    height = int(spectrum[x])
                    for y in range(height):
                        spectrum_win.addch(spectrum_height - 2 - y, x, '|')

                # Draw debug panel with box
                debug_start = spectrum_height
                debug_win = stdscr.subwin(5, max_x, debug_start, 0)
                debug_win.box()
                debug_win.addstr(0, 2, " Debug Log ", curses.A_REVERSE)
                for i, log in enumerate(debug_log):
                    debug_win.addstr(i + 1, 1, log[:max_x - 2])

                stdscr.refresh()
                curses.napms(50)

                last_timestamp = timestamp
                all_frequencies = frequencies.tolist()
                all_powers = powers

            if stdscr.getch() == ord('q'):
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            debug_log.append(f"Error: {str(e)}")
            debug_log.pop(0)

if __name__ == "__main__":
    curses.wrapper(spectrograph)

