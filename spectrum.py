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
        freq_start = float(parts[2])
        freq_end = float(parts[3])
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

                # Map frequencies to screen width
                mapped_indices = np.linspace(0, max_x - 1, len(all_frequencies)).astype(int)
                normalized_powers = np.interp(all_powers, [min_power, max_power], [0, max_y - 4])

                spectrum.fill(0)
                for i, index in enumerate(mapped_indices):
                    spectrum[index] = max(spectrum[index], normalized_powers[i])

                for x in range(max_x):
                    height = int(spectrum[x])
                    for y in range(height):
                        stdscr.addch(max_y - 4 - y, x, '|')

                # Display debug log at the bottom
                for i, log in enumerate(debug_log):
                    stdscr.addstr(max_y - 3 + i, 0, log[:max_x])

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

