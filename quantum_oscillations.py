"""Quantum oscillation (SdH / dHvA) detection in magnetic-field sweeps.

Quantum oscillations are periodic in inverse field (1/B), so they only show
up when the magnetic field is the swept variable. This module follows the
group's Igor `FFThan` procedure (see ETNH4Mar2020SdH.pxp):

1. Keep one sweep direction inside a high-field window.
2. Convert field to 1/B, sort, and interpolate onto a uniform 1/B grid.
3. Subtract a polynomial background (order 5) to leave the oscillatory part.
4. Zero-pad and FFT; the power spectrum's x-axis is the oscillation
   frequency in tesla.

The field window is chosen automatically (top third of the sweep, matching
the hand-picked cursor ranges in the Igor analysis) unless `min_field` is
given.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)

DEFAULT_INTERPOLATION_POINTS = 8192
DEFAULT_ZERO_PAD_FACTOR = 4
DEFAULT_BACKGROUND_ORDER = 5
# Fraction of the peak field where the analysis window starts by default.
DEFAULT_WINDOW_START_FRACTION = 2.0 / 3.0
# Field window must start at or above this, since 1/B diverges at zero.
MIN_WINDOW_FIELD_TESLA = 1.0
MIN_WINDOW_POINTS = 200
# Frequencies with fewer periods than this inside the window are
# indistinguishable from leftover background curvature.
MIN_PERIODS_IN_WINDOW = 4.0
# An oscillation is reported when the strongest peak is both
#  - sharp: far above the spectrum a few resolution widths to either side
#    (a real 1/B-periodic signal is a narrow line; noise, glitches, and
#    leftover background give broad humps), and
#  - significant: it and its harmonics hold a meaningful share of the
#    residual's power (samples often have several frequencies, so this is
#    not required to be a majority).
# Calibrated by eye on the March 2020 and June 2022 field sweeps.
DEFAULT_MIN_PEAK_SHARPNESS = 30.0
DEFAULT_MIN_PEAK_CONCENTRATION = 0.2
# Peak half-width and the "nearby" comparison band, in units of the
# window's frequency resolution (1 / span of 1/B).
PEAK_HALF_WIDTH_RESOLUTIONS = 1.5
SHARPNESS_BAND_RESOLUTIONS = (3.0, 8.0)
HARMONICS_CREDITED = 3
PEAK_DIP_RESOLUTIONS = 2.5
PEAK_DIP_FRACTION = 0.5
# Isolated instrument spikes (rolling-median outliers) are removed first;
# a single glitch otherwise spreads power across the whole spectrum.
SPIKE_WINDOW_POINTS = 11
SPIKE_THRESHOLD_MADS = 8.0

PUBLICATION_DPI = 300
FIGURE_SIZE = (7.0, 4.8)


@dataclass(frozen=True)
class QuantumOscillationResult:
    """Oscillatory part of one signal vs 1/B and its FFT spectrum."""

    signal_column: str
    field_column: str
    field_window: tuple[float, float]
    sweep_direction: str
    inverse_field: np.ndarray
    residual: np.ndarray
    frequencies_tesla: np.ndarray
    power: np.ndarray
    dominant_frequency_tesla: float | None
    peak_sharpness: float
    peak_concentration: float
    detected: bool


def analyze_quantum_oscillations(
    dataframe: pd.DataFrame,
    field_column: str,
    signal_column: str,
    *,
    min_field: float | None = None,
    max_field: float | None = None,
    interpolation_points: int = DEFAULT_INTERPOLATION_POINTS,
    zero_pad_factor: int = DEFAULT_ZERO_PAD_FACTOR,
    background_order: int = DEFAULT_BACKGROUND_ORDER,
    min_peak_sharpness: float = DEFAULT_MIN_PEAK_SHARPNESS,
    min_peak_concentration: float = DEFAULT_MIN_PEAK_CONCENTRATION,
) -> QuantumOscillationResult | None:
    """Look for 1/B-periodic oscillations in `signal_column`.

    Returns None when the sweep has too few points in the field window to
    analyze.
    """

    field = dataframe[field_column].to_numpy(dtype=float)
    values = dataframe[signal_column].to_numpy(dtype=float)
    finite = np.isfinite(field) & np.isfinite(values)
    field, values = field[finite], values[finite]
    if field.size < MIN_WINDOW_POINTS:
        return None

    # Work with |B| so negative-field sweeps are handled the same way.
    field = np.abs(field)
    peak_field = float(field.max())
    low = min_field
    if low is None:
        low = max(MIN_WINDOW_FIELD_TESLA, DEFAULT_WINDOW_START_FRACTION * peak_field)
    high = peak_field if max_field is None else max_field
    if high <= low:
        return None

    segment, direction = _longest_sweep_in_window(field, low, high)
    if segment is None or segment.size < MIN_WINDOW_POINTS:
        return None
    window_field = field[segment]
    window_values = _remove_spikes(values[segment])

    inverse = 1.0 / window_field
    order = np.argsort(inverse)
    inverse, window_values = inverse[order], window_values[order]
    span = float(inverse[-1] - inverse[0])
    if span <= 0:
        return None

    uniform_inverse = np.linspace(inverse[0], inverse[-1], interpolation_points)
    uniform_values = np.interp(uniform_inverse, inverse, window_values)
    centered = uniform_inverse - uniform_inverse.mean()
    background = np.polyval(
        np.polyfit(centered, uniform_values, background_order),
        centered,
    )
    residual = uniform_values - background

    fft_length = interpolation_points * zero_pad_factor
    spacing = span / (interpolation_points - 1)
    power = np.abs(np.fft.rfft(residual * np.hanning(residual.size), n=fft_length)) ** 2
    frequencies = np.fft.rfftfreq(fft_length, d=spacing)

    # Search between "enough periods to not be background" and the raw
    # data's own resolution limit (interpolation cannot add information).
    lowest = MIN_PERIODS_IN_WINDOW / span
    highest = 0.5 * segment.size / span
    band = (frequencies >= lowest) & (frequencies <= highest)

    resolution = 1.0 / span
    dominant: float | None = None
    sharpness = 0.0
    concentration = 0.0
    # Everything except the DC/first-resolution bins counts toward the total,
    # so leftover background below the search band dilutes the peak.
    total_power = float(power[frequencies >= resolution].sum())
    if band.any() and total_power > 0:
        dominant = float(frequencies[band][int(np.argmax(power[band]))])
        peak_power = float(power[band].max())
        half_width = PEAK_HALF_WIDTH_RESOLUTIONS * resolution
        # Quantum oscillations are not pure sines: credit the peak with its
        # harmonics so a strong 2F component does not count against it.
        in_peak = np.zeros_like(band)
        for harmonic in range(1, HARMONICS_CREDITED + 1):
            in_peak |= np.abs(frequencies - harmonic * dominant) <= half_width
        concentration = float(power[in_peak].sum() / total_power)

        near, far = (edge * resolution for edge in SHARPNESS_BAND_RESOLUTIONS)
        distance = np.abs(frequencies - dominant)
        nearby = (distance >= near) & (distance <= far) & (frequencies >= resolution)
        nearby_power = float(power[nearby].mean()) if nearby.any() else 0.0
        sharpness = peak_power / nearby_power if nearby_power > 0 else float("inf")

        # A "peak" at the low-frequency cutoff may just be the rising tail of
        # the background: require the spectrum to dip below it first.
        below = (frequencies >= dominant - PEAK_DIP_RESOLUTIONS * resolution) & (
            frequencies <= dominant
        )
        if power[below].min() > PEAK_DIP_FRACTION * peak_power:
            sharpness = concentration = 0.0

    return QuantumOscillationResult(
        signal_column=signal_column,
        field_column=field_column,
        field_window=(float(window_field.min()), float(window_field.max())),
        sweep_direction=direction,
        inverse_field=uniform_inverse,
        residual=residual,
        frequencies_tesla=frequencies,
        power=power,
        dominant_frequency_tesla=dominant,
        peak_sharpness=sharpness,
        peak_concentration=concentration,
        detected=(
            dominant is not None
            and sharpness >= min_peak_sharpness
            and concentration >= min_peak_concentration
        ),
    )


def plot_quantum_oscillations(
    result: QuantumOscillationResult,
    *,
    name: str,
    signal_label: str,
    output_dir: str | Path,
) -> Path:
    """Save a two-panel figure: residual vs 1/B and its FFT spectrum."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    figure, (residual_axis, spectrum_axis) = plt.subplots(
        2, 1, figsize=(FIGURE_SIZE[0], FIGURE_SIZE[1] * 1.6), constrained_layout=True
    )
    residual_axis.plot(result.inverse_field, result.residual, linewidth=0.8)
    residual_axis.axhline(0.0, color="0.5", linewidth=0.6)
    residual_axis.set_xlabel("1/B (1/T)")
    residual_axis.set_ylabel(f"Δ {signal_label}")
    low, high = result.field_window
    residual_axis.set_title(
        f"{signal_label} oscillations, {low:.2f}–{high:.2f} T ({result.sweep_direction})"
    )
    residual_axis.grid(True, alpha=0.3)

    span = float(result.inverse_field[-1] - result.inverse_field[0])
    shown_limit = 50.0 / span
    if result.dominant_frequency_tesla is not None:
        shown_limit = max(shown_limit, 4.0 * result.dominant_frequency_tesla)
    shown = result.frequencies_tesla <= shown_limit
    spectrum_axis.plot(
        result.frequencies_tesla[shown], result.power[shown], linewidth=0.8
    )
    if result.dominant_frequency_tesla is not None:
        status = "detected" if result.detected else "not significant"
        spectrum_axis.axvline(
            result.dominant_frequency_tesla, color="tab:red", linewidth=0.8, alpha=0.7
        )
        spectrum_axis.set_title(
            f"FFT: strongest peak {result.dominant_frequency_tesla:.1f} T "
            f"(sharpness {result.peak_sharpness:.3g}, "
            f"{result.peak_concentration:.0%} of power, {status})"
        )
    spectrum_axis.set_xlabel("Oscillation frequency (T)")
    spectrum_axis.set_ylabel("Power")
    spectrum_axis.grid(True, alpha=0.3)

    stem = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in name)
    signal_stem = "".join(
        ch if ch.isalnum() or ch in "_.-" else "_" for ch in result.signal_column
    )
    path = output_path / f"{stem}_{signal_stem}_oscillation_fft.png"
    figure.savefig(path, dpi=PUBLICATION_DPI, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    LOGGER.info("Saved oscillation plot: %s", path)
    return path


def _remove_spikes(values: np.ndarray) -> np.ndarray:
    """Replace isolated outliers with the local rolling median."""

    series = pd.Series(values)
    median = series.rolling(SPIKE_WINDOW_POINTS, center=True, min_periods=1).median()
    deviation = (series - median).abs()
    mad = float(deviation.median())
    if mad <= 0:
        return values
    spikes = deviation > SPIKE_THRESHOLD_MADS * 1.4826 * mad
    return series.where(~spikes, median).to_numpy(dtype=float)


def _longest_sweep_in_window(
    field: np.ndarray,
    low: float,
    high: float,
) -> tuple[np.ndarray | None, str]:
    """Indices of the longest single-direction pass through [low, high]."""

    inside = (field >= low) & (field <= high)
    if not inside.any():
        return None, ""

    # Contiguous runs of in-window samples.
    edges = np.flatnonzero(np.diff(np.concatenate(([0], inside.astype(int), [0]))))
    runs = [np.arange(start, stop) for start, stop in zip(edges[::2], edges[1::2])]

    best: np.ndarray | None = None
    best_direction = ""
    for run in runs:
        # A run that goes up and comes back down is split at its peak so
        # up- and down-sweeps (which can differ by hysteresis) are not mixed.
        turn = int(np.argmax(field[run]))
        for part, direction in ((run[: turn + 1], "up-sweep"), (run[turn:], "down-sweep")):
            if best is None or part.size > best.size:
                best, best_direction = part, direction
    return best, best_direction
