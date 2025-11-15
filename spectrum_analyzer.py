#!/usr/bin/env python3
import sys
import numpy as np
import time
import threading
import logging
import argparse
from spectrum_analyzer import hackrf_sweep, transform_coordinates
from math import ceil

from textual.app import App, ComposeResult
from textual.widgets import Static, Footer, Header
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual import events
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

# Default Constants
DEFAULT_FRAME_RATE = 16
DEFAULT_SPECTRUM_HEIGHT = 5
DEFAULT_MIN_POWER = -100.0
DEFAULT_MAX_POWER = -20.0
LABEL_SPACING = 8  # Spacing between frequency labels

# Color mapping for power levels
COLORS = [
    "magenta",
    "magenta",
    "cyan",
    "green",
    "yellow",
    "red"
]

def get_color(power: float, min_power: float, max_power: float) -> str:
    """Maps power levels to corresponding colors."""
    # Clamp power to range
    power = max(min_power, min(power, max_power))

    # Map to color index [0, 5]
    if max_power == min_power:
        index = 0
    else:
        index = int(6 * (power - min_power) / (max_power - min_power))
        index = max(0, min(5, index))

    return COLORS[index]


class SpectrumWidget(Static):
    """Widget to display the real-time spectrum graph."""

    data = reactive({})
    peak_data = reactive({})
    min_power = reactive(DEFAULT_MIN_POWER)
    max_power = reactive(DEFAULT_MAX_POWER)
    peak_hold = reactive(False)
    paused = reactive(False)
    spectrum_height = reactive(DEFAULT_SPECTRUM_HEIGHT)

    def render(self) -> Text:
        """Render the spectrum graph."""
        width = self.size.width
        height = self.size.height

        if height < 3 or width < 3:
            return Text("")

        # Create title
        title = "Spectrograph"
        if self.peak_hold:
            title += " [PEAK HOLD]"
        if self.paused:
            title += " [PAUSED]"

        # Determine what data to display
        display_data = self.peak_data if self.peak_hold and self.peak_data else self.data

        if not display_data:
            result = Text(f"╭─ {title} ", style="bold")
            result.append("─" * (width - len(title) - 4) + "╮\n")
            for _ in range(height - 3):
                result.append("│" + " " * (width - 2) + "│\n")
            result.append("╰" + "─" * (width - 2) + "╯")
            return result

        # Remap data to screen coordinates
        remapped_data = transform_coordinates.remap_x(display_data, width - 2)
        sorted_x = sorted(remapped_data.keys())
        sorted_powers = [remapped_data[freq] for freq in sorted_x]
        mapped_indices = np.linspace(0, width - 3, len(sorted_x)).astype(int)

        # Normalize powers to display height
        graph_height = height - 3  # Account for box borders and labels
        normalized_powers = np.interp(
            sorted_powers,
            [self.min_power, self.max_power],
            [0, graph_height]
        )

        # Character map for sub-line resolution
        charmap = {
            8.0/8.0: '█',
            7.0/8.0: '▇',
            6.0/8.0: '▆',
            5.0/8.0: '▅',
            4.0/8.0: '▄',
            3.0/8.0: '▃',
            2.0/8.0: '▂',
            1.0/8.0: '▁',
        }

        # Build display grid
        grid = [[' ' for _ in range(width - 2)] for _ in range(graph_height)]
        colors = [[None for _ in range(width - 2)] for _ in range(graph_height)]

        for i, index in enumerate(mapped_indices):
            if index >= width - 2:
                continue
            height_val = int(normalized_powers[i] * 8) / 8
            color = get_color(sorted_powers[i], self.min_power, self.max_power)

            for y in range(int(ceil(height_val))):
                if y >= graph_height:
                    break
                c = charmap[min(height_val - y, 1.0)]
                row = graph_height - 1 - y
                grid[row][index] = c
                colors[row][index] = color

        # Build output
        result = Text()
        result.append(f"╭─ {title} ", style="bold")
        result.append("─" * (width - len(title) - 4) + "╮\n")

        # Draw graph
        for row_idx, (row, color_row) in enumerate(zip(grid, colors)):
            result.append("│")
            for char, color in zip(row, color_row):
                if color:
                    result.append(char, style=color)
                else:
                    result.append(char)
            result.append("│\n")

        # Draw frequency labels
        sorted_frequencies = sorted(display_data.keys())
        if sorted_frequencies:
            min_freq = sorted_frequencies[0] / 1000000
            max_freq = sorted_frequencies[-1] / 1000000

            label_line = "│"
            max_labels = max(1, (width - 2) // LABEL_SPACING)
            label_positions = np.linspace(0, width - 9, max_labels).astype(int)
            label_frequencies = np.linspace(min_freq, max_freq, len(label_positions))

            # Build label line
            label_chars = [' '] * (width - 2)
            for pos, freq in zip(label_positions, label_frequencies):
                label = f"{freq:6.2f}"
                for i, c in enumerate(label):
                    if pos + i < len(label_chars):
                        label_chars[pos + i] = c

            result.append("│")
            result.append(''.join(label_chars))
            result.append("│\n")
        else:
            result.append("│" + " " * (width - 2) + "│\n")

        result.append("╰" + "─" * (width - 2) + "╯")
        return result


class WaterfallWidget(Static):
    """Widget to display the waterfall (time series) view."""

    time_series = reactive([])
    min_power = reactive(DEFAULT_MIN_POWER)
    max_power = reactive(DEFAULT_MAX_POWER)

    def render(self) -> Text:
        """Render the waterfall display."""
        width = self.size.width
        height = self.size.height

        if height < 3 or width < 3:
            return Text("")

        result = Text()
        result.append("╭─ Waterfall ", style="bold")
        result.append("─" * (width - 13) + "╮\n")

        # Calculate available height for waterfall data
        available_height = height - 2  # Subtract top and bottom borders

        # Block character for waterfall
        block = '█'

        # Draw waterfall rows
        for row in range(available_height):
            result.append("│")

            if row < len(self.time_series):
                data = self.time_series[row]
                if data:
                    sorted_x = sorted(data.keys())
                    sorted_powers = [data[freq] for freq in sorted_x]
                    mapped_indices = np.linspace(0, width - 3, len(sorted_x)).astype(int)

                    # Build row
                    row_chars = [' '] * (width - 2)
                    for i, index in enumerate(mapped_indices):
                        if index < len(row_chars):
                            color = get_color(sorted_powers[i], self.min_power, self.max_power)
                            row_chars[index] = (block, color)

                    # Output with colors
                    for item in row_chars:
                        if isinstance(item, tuple):
                            result.append(item[0], style=item[1])
                        else:
                            result.append(item)
                else:
                    result.append(" " * (width - 2))
            else:
                result.append(" " * (width - 2))

            result.append("│\n")

        result.append("╰" + "─" * (width - 2) + "╯")
        return result


class StatusLine(Static):
    """Widget to display the status line."""

    min_power = reactive(DEFAULT_MIN_POWER)
    max_power = reactive(DEFAULT_MAX_POWER)
    fps = reactive(DEFAULT_FRAME_RATE)

    def render(self) -> Text:
        """Render the status line."""
        text = f"Range: {self.min_power:.0f} to {self.max_power:.0f} dBm | FPS: {self.fps} | Press '?' for help | 'q' to quit"
        return Text(text, style="bold reverse")


class HelpOverlay(Static):
    """Widget to display help information."""

    def render(self) -> Text:
        """Render the help overlay."""
        help_text = """
╭──────── KEYBOARD SHORTCUTS ────────╮
│  q - Quit                          │
│  p - Pause/Resume                  │
│  ? - Toggle this help              │
│  m - Toggle peak hold              │
│  + - Increase sensitivity          │
│  - - Decrease sensitivity          │
│                                    │
│  Press '?' to close this help      │
╰────────────────────────────────────╯
"""
        return Text(help_text, style="bold reverse")


class SpectrumAnalyzerApp(App):
    """Textual application for the spectrum analyzer."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #spectrum {
        height: auto;
        max-height: 10;
    }

    #waterfall {
        height: 1fr;
    }

    #status {
        height: 1;
        dock: bottom;
    }

    #help {
        align: center middle;
        width: 40;
        height: 12;
        layer: overlay;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(self, frequency_power_generator, stop_event, config):
        super().__init__()
        self.frequency_power_generator = frequency_power_generator
        self.stop_event = stop_event
        self.config = config

        # State
        self.paused = False
        self.peak_hold = False
        self.peak_data = {}
        self.show_help = False
        self.time_series = []
        self.last_update_time = time.time()
        self.frame_interval = 1 / config['fps']
        self.min_power = config['min_power']
        self.max_power = config['max_power']
        self.data_thread = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        self.spectrum = SpectrumWidget(id="spectrum")
        self.spectrum.spectrum_height = self.config['spectrum_height']
        self.spectrum.min_power = self.min_power
        self.spectrum.max_power = self.max_power

        self.waterfall = WaterfallWidget(id="waterfall")
        self.waterfall.min_power = self.min_power
        self.waterfall.max_power = self.max_power

        self.status = StatusLine(id="status")
        self.status.min_power = self.min_power
        self.status.max_power = self.max_power
        self.status.fps = self.config['fps']

        self.help_overlay = HelpOverlay(id="help")
        self.help_overlay.add_class("hidden")

        yield self.spectrum
        yield self.waterfall
        yield self.status
        yield self.help_overlay

    def on_mount(self) -> None:
        """Start the data worker thread after the app is mounted."""
        self.data_thread = threading.Thread(target=self._data_worker, daemon=True)
        self.data_thread.start()

    def _data_worker(self):
        """Background thread to consume data from the generator."""
        try:
            for timestamp, frequency_power_map in self.frequency_power_generator:
                if self.stop_event.is_set():
                    break

                if not self.paused:
                    # Update peak hold data
                    if self.peak_hold:
                        for freq, power in frequency_power_map.items():
                            self.peak_data[freq] = max(
                                self.peak_data.get(freq, float('-inf')),
                                power
                            )

                    # Add to time series
                    self.time_series.insert(0, frequency_power_map)

                    # Update display at frame rate
                    current_time = time.time()
                    if current_time - self.last_update_time >= self.frame_interval:
                        self.last_update_time = current_time
                        try:
                            self.call_from_thread(self._update_display, frequency_power_map)
                        except Exception as e:
                            logging.error(f"Error updating display: {e}")
                            if self.stop_event.is_set():
                                break
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            self.stop_event.set()
        except Exception as e:
            logging.error(f"Error in data worker: {e}", exc_info=True)
            self.stop_event.set()
        finally:
            # Signal the app to exit
            try:
                self.call_from_thread(self.exit)
            except:
                pass

    def _update_display(self, data):
        """Update the display widgets (called from data thread)."""
        # Trim time series to available height
        if hasattr(self.waterfall, 'size') and self.waterfall.size.height > 2:
            max_rows = self.waterfall.size.height - 2
            self.time_series = self.time_series[:max_rows]

        # Update widgets
        self.spectrum.data = data
        if self.peak_hold:
            self.spectrum.peak_data = self.peak_data
        self.spectrum.min_power = self.min_power
        self.spectrum.max_power = self.max_power
        self.spectrum.peak_hold = self.peak_hold
        self.spectrum.paused = self.paused

        self.waterfall.time_series = self.time_series
        self.waterfall.min_power = self.min_power
        self.waterfall.max_power = self.max_power

        self.status.min_power = self.min_power
        self.status.max_power = self.max_power

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard input."""
        if event.key == "q":
            self.stop_event.set()
            self.exit()
        elif event.key == "p":
            self.paused = not self.paused
        elif event.key == "question_mark":
            self.show_help = not self.show_help
            if self.show_help:
                self.help_overlay.remove_class("hidden")
            else:
                self.help_overlay.add_class("hidden")
        elif event.key == "m":
            self.peak_hold = not self.peak_hold
            if not self.peak_hold:
                self.peak_data = {}
        elif event.key == "plus" or event.key == "equals":
            # Increase sensitivity (narrow range)
            range_size = self.max_power - self.min_power
            if range_size > 10:
                self.min_power += 2
                self.max_power -= 2
        elif event.key == "minus" or event.key == "underscore":
            # Decrease sensitivity (widen range)
            self.min_power -= 2
            self.max_power += 2


def run_spectrum_analyzer(frequency_power_generator, stop_event, config):
    """Run the spectrum analyzer app."""
    app = SpectrumAnalyzerApp(frequency_power_generator, stop_event, config)
    try:
        app.run()
    except KeyboardInterrupt:
        stop_event.set()
    except Exception as e:
        logging.error(f"Error running app: {e}", exc_info=True)
        stop_event.set()
        raise


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

    # Verify we can access a TTY for the UI
    import os
    if not sys.stdin.isatty():
        # stdin is piped, which is expected for hackrf_sweep data
        # Textual will automatically use /dev/tty for terminal I/O
        logging.info("stdin is not a TTY (piped input detected)")
        # Verify /dev/tty is accessible
        try:
            with open('/dev/tty', 'r'):
                pass
        except Exception as e:
            print("Error: Cannot access /dev/tty for terminal I/O", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Please ensure you're running in an interactive terminal.", file=sys.stderr)
            sys.exit(1)

    # Build configuration dictionary
    config = {
        'fps': args.fps,
        'min_power': args.min_power,
        'max_power': args.max_power,
        'spectrum_height': args.height
    }

    stop_event = threading.Event()

    try:
        run_spectrum_analyzer(
            hackrf_sweep.frequency_power_generator(),
            stop_event,
            config
        )
    except KeyboardInterrupt:
        # User pressed Ctrl+C
        stop_event.set()
    finally:
        stop_event.set()
