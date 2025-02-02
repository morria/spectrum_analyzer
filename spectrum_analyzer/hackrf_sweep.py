#!/usr/bin/env python3
import sys
import curses
import numpy as np
import time
import threading
import queue

def parse_line(line):
    """Parses a single line from hackrf_sweep output and returns a timestamp and a frequency-to-power dictionary."""
    parts = [p.strip() for p in line.strip().split(',')]
    if len(parts) < 7:
        return None, None

    try:
        timestamp = parts[1]  # Grouping key for data collection
        freq_start = int(parts[2])
        freq_end = int(parts[3])
        freq_step = float(parts[4])
        if freq_step == 0:
            return None, None  # Prevent division by zero
        powers = list(map(float, parts[6:]))
        frequencies = np.linspace(freq_start, freq_end, len(powers))
        freq_power_map = dict(zip(frequencies, powers))
        return timestamp, freq_power_map
    except ValueError:
        return None, None

def sample_generator():
    """Generator yielding parsed lines from hackrf_sweep output."""
    for line in sys.stdin:
        yield parse_line(line)

def frequency_power_generator():
    """Generator that groups frequency data by timestamp and ensures ascending frequency order."""
    current_timestamp = None
    collected_data = {}

    for timestamp, freq_power_map in sample_generator():
        if timestamp is None or freq_power_map is None:
            continue

        if current_timestamp is None:
            current_timestamp = timestamp

        if timestamp == current_timestamp:
            collected_data.update(freq_power_map)
        else:
            yield current_timestamp, collected_data
            current_timestamp = timestamp
            collected_data = freq_power_map

    if collected_data:
        yield current_timestamp, collected_data
