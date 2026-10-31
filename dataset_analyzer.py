"""Automatic detection of experiment structure and measurement plotting.

Given a tabular experiment dataset, this module decides what to plot the way
the group reads its data:

* **Y-axis: the frequency signal.** Changes in the material are measured
  through a resonant frequency. In pulsed-field runs the column is the
  frequency itself (`FQ1`, `FQ2`); in DC-field runs it is the frequency
  `Counter`. These are plotted; control parameters and thermometry are not.
* **X-axis: the swept control parameter.** Magnetic field first, then angle
  (`Angle`, or rotator `Steps`), and only rarely temperature. A control
  parameter counts as swept only if it moves over a physically meaningful
  range *and* fills that range continuously (a one-off jump is not a sweep).
  Control parameters that were not swept are reported as fixed values.
* **Oscillations.** Quantum oscillations only appear when the field is
  swept, so field sweeps are also run through `quantum_oscillations`.

Column roles are inferred from naming conventions plus statistics, so this
works across NHMFL-style prefixed columns (`Field_...`, `RuO_T_...`) as well
as plainly named columns (`Magnetic Field`, `Frequency`). Other analysis
modules are expected to build on `DatasetAnalysis` rather than re-deriving
column roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import re
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quantum_oscillations import (
    QuantumOscillationResult,
    analyze_quantum_oscillations,
    plot_quantum_oscillations,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("output") / "auto_plots"
PUBLICATION_DPI = int(os.environ.get("PLOT_DPI", "300"))
FIGURE_SIZE = (7.0, 4.8)

# A column is treated as constant when its coefficient of variation
# (std / |mean|) falls at or below this fraction, or its absolute range is
# negligible (guards against a near-zero mean, e.g. an angle held at 0).
DEFAULT_CONSTANT_RELATIVE_TOLERANCE = 0.01
CONSTANT_ABSOLUTE_TOLERANCE = 1e-9

# Control-parameter name groups, in x-axis priority order. Column names are
# split into word tokens (camelCase and separator boundaries, numeric
# suffixes dropped) before being compared against these aliases, so
# "Field(T)", "Field_1732487951", "MagneticField", and compound instrument
# names like "RuO_T_1732487951" or "DR_Temp_1732487951" all resolve.
FIELD_CATEGORY = "Magnetic Field"
ANGLE_CATEGORY = "Angle"
STEPS_CATEGORY = "Angle (rotator steps)"
TEMPERATURE_CATEGORY = "Temperature"
TIME_CATEGORY = "Time"
CONTROL_NAME_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (FIELD_CATEGORY, ("field", "b")),
    (ANGLE_CATEGORY, ("angle", "theta", "rotation")),
    (STEPS_CATEGORY, ("steps",)),
    (TEMPERATURE_CATEGORY, ("temperature", "temp", "t")),
)
AXIS_UNITS = {
    FIELD_CATEGORY: "T",
    ANGLE_CATEGORY: "°",
    TEMPERATURE_CATEGORY: "K",
    TIME_CATEGORY: "s",
}

# Thermometer sensor names. Alone (e.g. "Cernox") the column is a
# temperature; with an "R" token (e.g. "Cernox_R") it is the sensor's raw
# resistance, which is housekeeping rather than a sample measurement.
THERMOMETER_TOKENS = ("cernox", "crnx", "ruo", "ru", "cx")
RESISTANCE_TOKENS = ("r",)

# The frequency signal: `Counter` in DC-field runs, `FQ1`/`FQ2` (or a plain
# "Frequency") in pulsed-field runs.
RESPONSE_TOKENS = ("counter", "frequency", "freq")
RESPONSE_TOKEN_PATTERN = re.compile(r"^fq\d*$")

# Minimum robust (1st-99th percentile) range for a control parameter to
# count as swept. Temperature uses a relative range instead.
MIN_SWEEP_RANGE: dict[str, float] = {
    FIELD_CATEGORY: 0.5,  # tesla
    ANGLE_CATEGORY: 2.0,  # degrees
    STEPS_CATEGORY: 20.0,  # rotator motor steps
}
MIN_TEMPERATURE_SWEEP_FRACTION = 0.05
# A sweep must fill its range: split the range into bins and require this
# fraction to contain samples. A one-off jump fills only the two end bins.
SWEEP_COVERAGE_BINS = 40
MIN_SWEEP_COVERAGE = 0.5

# Instruments write ~9.91e37 as an overflow / no-reading marker.
SENTINEL_MAGNITUDE = 1e30

# Column-name fragments that identify acquisition bookkeeping (e.g. a
# wall-clock timestamp column) rather than an intentionally swept or
# measured physical quantity. These are never plotted as measurements.
BOOKKEEPING_NAME_FRAGMENTS = ("time", "timestamp", "date", "index")


class ColumnRole(str, Enum):
    """The detected role of one dataframe column."""

    INDEPENDENT_VARIABLE = "independent_variable"
    SECONDARY_SWEEP = "secondary_sweep"
    CONSTANT_PARAMETER = "constant_parameter"
    MEASUREMENT = "measurement"
    HOUSEKEEPING = "housekeeping"


@dataclass(frozen=True)
class ConstantParameter:
    """A column whose value did not meaningfully change during the run."""

    column: str
    average: float
    minimum: float
    maximum: float
    standard_deviation: float
    unit: str | None = None


@dataclass(frozen=True)
class DatasetAnalysis:
    """The detected structure of one experiment dataset."""

    independent_variable: str | None
    independent_variable_category: str | None
    constant_parameters: tuple[ConstantParameter, ...]
    measurements: tuple[str, ...]
    column_roles: dict[str, ColumnRole]
    # Other control parameters that also moved during the run (e.g. a
    # temperature drift during a field sweep). Reported, never plotted.
    secondary_sweeps: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedPlot:
    """One saved measurement-vs-independent-variable plot."""

    measurement: str
    independent_variable: str
    path: Path
    kind: str = "measurement"


class DatasetAnalyzer:
    """Detects experiment structure and plots measurements automatically.

    This is the reusable entry point future analysis modules are expected to
    build on: call `analyze()` once and reuse the resulting `DatasetAnalysis`
    instead of re-deriving column roles.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        *,
        name: str = "dataset",
        constant_relative_tolerance: float = DEFAULT_CONSTANT_RELATIVE_TOLERANCE,
    ) -> None:
        self.dataframe = _clean_dataframe(dataframe)
        self.name = name
        self.constant_relative_tolerance = constant_relative_tolerance
        self._analysis: DatasetAnalysis | None = None

    def analyze(self) -> DatasetAnalysis:
        """Detect the x-axis, fixed parameters, and frequency signals."""

        if self._analysis is not None:
            return self._analysis

        numeric_columns = [
            column
            for column in self.dataframe.columns
            if pd.api.types.is_numeric_dtype(self.dataframe[column])
            and not self.dataframe[column].dropna().empty
        ]

        controls: dict[str, str] = {}
        responses: list[str] = []
        housekeeping: list[str] = []
        others: list[str] = []
        for column in numeric_columns:
            category = _control_category(column)
            if category is not None:
                controls[column] = category
            elif _is_response(column):
                responses.append(column)
            elif _is_thermometer_resistance(column) or _matches_any_fragment(
                column, BOOKKEEPING_NAME_FRAGMENTS
            ):
                housekeeping.append(column)
            else:
                others.append(column)

        swept = [column for column, category in controls.items() if self._is_swept(column, category)]
        independent_variable, category = self._choose_x_axis(swept, controls, housekeeping)

        column_roles: dict[str, ColumnRole] = {}
        constant_parameters: list[ConstantParameter] = []
        secondary_sweeps: list[str] = []
        for column in controls:
            if column == independent_variable:
                continue
            if column in swept:
                secondary_sweeps.append(column)
                column_roles[column] = ColumnRole.SECONDARY_SWEEP
            else:
                constant_parameters.append(self._describe_constant(column))
                column_roles[column] = ColumnRole.CONSTANT_PARAMETER

        # Frequency shifts are often parts-per-million, so a frequency
        # signal is plotted whenever it moves at all; the relative-variation
        # constant test only applies to other columns.
        measurements = [column for column in responses if self.dataframe[column].nunique() > 1]
        for column in others:
            if self._is_constant(self.dataframe[column].dropna()):
                constant_parameters.append(self._describe_constant(column))
                column_roles[column] = ColumnRole.CONSTANT_PARAMETER
            elif not measurements:
                # Only fall back to non-frequency signals when the run has
                # no frequency column to plot.
                measurements.append(column)
        for column in housekeeping:
            if column != independent_variable:
                column_roles[column] = ColumnRole.HOUSEKEEPING

        if independent_variable is not None:
            column_roles[independent_variable] = ColumnRole.INDEPENDENT_VARIABLE
        for column in measurements:
            column_roles[column] = ColumnRole.MEASUREMENT

        self._analysis = DatasetAnalysis(
            independent_variable=independent_variable,
            independent_variable_category=category,
            constant_parameters=tuple(constant_parameters),
            measurements=tuple(measurements),
            column_roles=column_roles,
            secondary_sweeps=tuple(secondary_sweeps),
        )
        return self._analysis

    def analyze_oscillations(self) -> list[QuantumOscillationResult]:
        """Run quantum-oscillation detection when the field was swept."""

        analysis = self.analyze()
        if analysis.independent_variable_category != FIELD_CATEGORY:
            return []
        results = []
        for measurement in analysis.measurements:
            result = analyze_quantum_oscillations(
                self.dataframe,
                analysis.independent_variable,
                measurement,
            )
            if result is not None:
                results.append(result)
        return results

    def generate_plots(
        self,
        *,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        show: bool = False,
        include_oscillations: bool = True,
    ) -> list[GeneratedPlot]:
        """Plot each frequency signal vs the x-axis, plus oscillation FFTs."""

        analysis = self.analyze()
        if analysis.independent_variable is None:
            LOGGER.warning(
                "Skipping plots for %s: no independent variable was detected",
                self.name,
            )
            return []

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        x_column = analysis.independent_variable
        x_label = self._axis_label(x_column, analysis.independent_variable_category)
        unit = AXIS_UNITS.get(analysis.independent_variable_category or "")
        x_axis_label = f"{x_label} ({unit})" if unit else x_label
        generated: list[GeneratedPlot] = []

        for measurement in analysis.measurements:
            y_label = self._axis_label(measurement)
            figure, axis = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
            axis.plot(
                self.dataframe[x_column],
                self.dataframe[measurement],
                linewidth=0.9,
            )
            axis.set_xlabel(x_axis_label)
            axis.set_ylabel(y_label)
            axis.set_title(f"{y_label} vs {x_label}")
            axis.grid(True, alpha=0.3)
            fixed = self._fixed_parameters_caption(analysis)
            if fixed:
                axis.text(
                    0.01, 0.01, fixed, transform=axis.transAxes,
                    fontsize=7, color="0.35", va="bottom",
                )

            plot_path = output_path / (
                f"{_safe_stem(self.name)}_{_safe_stem(measurement)}"
                f"_vs_{_safe_stem(x_column)}.png"
            )
            figure.savefig(
                plot_path,
                dpi=PUBLICATION_DPI,
                bbox_inches="tight",
                facecolor="white",
            )
            LOGGER.info("Saved plot: %s", plot_path)

            if show:
                plt.show()
            else:
                plt.close(figure)

            generated.append(
                GeneratedPlot(
                    measurement=measurement,
                    independent_variable=x_column,
                    path=plot_path,
                )
            )

        if include_oscillations:
            for result in self.analyze_oscillations():
                path = plot_quantum_oscillations(
                    result,
                    name=self.name,
                    signal_label=self._axis_label(result.signal_column),
                    output_dir=output_path,
                )
                generated.append(
                    GeneratedPlot(
                        measurement=result.signal_column,
                        independent_variable="1/B",
                        path=path,
                        kind="oscillation_fft",
                    )
                )

        return generated

    def print_summary(self, plots: Iterable[GeneratedPlot] = ()) -> None:
        """Print a human-readable summary of the detected dataset structure."""

        analysis = self.analyze()
        plot_list = list(plots)

        print("-" * 32)
        print("Detected X-axis:")
        if analysis.independent_variable:
            print(
                self._axis_label(
                    analysis.independent_variable,
                    analysis.independent_variable_category,
                )
            )
        else:
            print("none")

        if analysis.secondary_sweeps:
            print("\nAlso changed during the run (not plotted):")
            for column in analysis.secondary_sweeps:
                print(_display_name(column))

        print("\nFixed Parameters:")
        if analysis.constant_parameters:
            for parameter in analysis.constant_parameters:
                unit = f" {parameter.unit}" if parameter.unit else ""
                print(
                    f"{_display_name(parameter.column)} = "
                    f"{parameter.average:.6g}{unit}"
                )
        else:
            print("none")

        print("\nY-axis signals:")
        if analysis.measurements:
            for measurement in analysis.measurements:
                print(self._axis_label(measurement))
        else:
            print("none")

        oscillations = self.analyze_oscillations()
        if oscillations:
            print("\nQuantum oscillations (FFT in 1/B):")
            for result in oscillations:
                low, high = result.field_window
                verdict = "DETECTED" if result.detected else "none found"
                frequency = (
                    f"{result.dominant_frequency_tesla:.1f} T"
                    if result.dominant_frequency_tesla is not None
                    else "-"
                )
                print(
                    f"{self._axis_label(result.signal_column)}: {verdict}, "
                    f"strongest peak {frequency} "
                    f"({low:.2f}-{high:.2f} T, {result.sweep_direction})"
                )

        print("\nGenerated:")
        if plot_list:
            for plot in plot_list:
                if plot.kind == "oscillation_fft":
                    print(f"{_display_name(plot.measurement)} oscillation FFT")
                    continue
                x_label = self._axis_label(
                    plot.independent_variable,
                    analysis.independent_variable_category,
                )
                print(f"{self._axis_label(plot.measurement)} vs {x_label}")
        else:
            print("none")
        print("-" * 32)

    def _is_swept(self, column: str, category: str) -> bool:
        values = self.dataframe[column].dropna().to_numpy(dtype=float)
        if values.size < 2:
            return False
        low, high = np.percentile(values, [1, 99])
        data_range = float(high - low)
        if category == TEMPERATURE_CATEGORY:
            scale = float(np.median(np.abs(values)))
            if scale <= CONSTANT_ABSOLUTE_TOLERANCE:
                return False
            if data_range / scale < MIN_TEMPERATURE_SWEEP_FRACTION:
                return False
        elif data_range < MIN_SWEEP_RANGE[category]:
            return False

        inside = values[(values >= low) & (values <= high)]
        counts, _edges = np.histogram(inside, bins=SWEEP_COVERAGE_BINS, range=(low, high))
        return float(np.mean(counts > 0)) >= MIN_SWEEP_COVERAGE

    def _choose_x_axis(
        self,
        swept: list[str],
        controls: dict[str, str],
        housekeeping: list[str],
    ) -> tuple[str | None, str | None]:
        # Field, then angle (degrees before rotator steps), then temperature.
        for category, _aliases in CONTROL_NAME_GROUPS:
            for column in swept:
                if controls[column] == category:
                    return column, category

        # Nothing was swept: show the signal against time so drifts and
        # relaxation are still visible.
        for column in housekeeping:
            if _matches_name_group(column, ("timestamp", "time")):
                return column, TIME_CATEGORY
        return None, None

    def _fixed_parameters_caption(self, analysis: DatasetAnalysis) -> str:
        parts = []
        for parameter in analysis.constant_parameters:
            category = _control_category(parameter.column)
            if category is None:
                continue
            parts.append(f"{_display_name(parameter.column)} ≈ {parameter.average:.4g}")
        return "Fixed: " + ", ".join(parts) if parts else ""

    def _is_constant(self, series: pd.Series) -> bool:
        data_range = float(series.max() - series.min())
        if data_range <= CONSTANT_ABSOLUTE_TOLERANCE:
            return True

        mean = float(series.mean())
        std = float(series.std(ddof=0))
        if abs(mean) > CONSTANT_ABSOLUTE_TOLERANCE:
            return (std / abs(mean)) <= self.constant_relative_tolerance
        return std <= CONSTANT_ABSOLUTE_TOLERANCE

    def _describe_constant(self, column: str) -> ConstantParameter:
        series = self.dataframe[column].dropna()
        return ConstantParameter(
            column=column,
            average=float(series.mean()),
            minimum=float(series.min()),
            maximum=float(series.max()),
            standard_deviation=float(series.std(ddof=0)),
            unit=_extract_unit(column),
        )

    def _axis_label(self, column: str, category: str | None = None) -> str:
        if category:
            return category
        if _is_response(column):
            return f"Frequency ({_display_name(column)})"
        return _display_name(column)


def _clean_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Blank out instrument no-reading markers before any statistics."""

    cleaned = dataframe.copy()
    for column in cleaned.columns:
        if not pd.api.types.is_numeric_dtype(cleaned[column]):
            continue
        series = cleaned[column]
        invalid = series.abs() >= SENTINEL_MAGNITUDE
        if _is_response(column):
            # A frequency of exactly zero means the counter had no lock.
            invalid |= series == 0
        if invalid.any():
            cleaned[column] = series.mask(invalid)
    return cleaned


def _control_category(column: str) -> str | None:
    tokens = _tokenize_column_name(column)
    if _is_thermometer_resistance(column):
        return None
    for category, aliases in CONTROL_NAME_GROUPS:
        if any(token in aliases for token in tokens):
            return category
    if any(token in THERMOMETER_TOKENS for token in tokens):
        return TEMPERATURE_CATEGORY
    return None


def _is_thermometer_resistance(column: str) -> bool:
    tokens = _tokenize_column_name(column)
    return any(token in THERMOMETER_TOKENS for token in tokens) and any(
        token in RESISTANCE_TOKENS for token in tokens
    )


def _is_response(column: str) -> bool:
    return any(
        token in RESPONSE_TOKENS or RESPONSE_TOKEN_PATTERN.match(token)
        for token in _tokenize_column_name(column)
    )


def _normalize_column_name(column: str) -> str:
    """Strip units, punctuation, and trailing numeric suffixes for matching."""

    without_units = re.sub(r"[\(\[].*?[\)\]]", "", column)
    alnum_only = re.sub(r"[^A-Za-z0-9]", "", without_units)
    without_trailing_digits = re.sub(r"\d+$", "", alnum_only)
    return without_trailing_digits.lower()


def _tokenize_column_name(column: str) -> list[str]:
    """Split a column name into lowercase word tokens, dropping numeric ids."""

    without_units = re.sub(r"[\(\[].*?[\)\]]", "", column)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", without_units)
    spaced = re.sub(r"[^A-Za-z0-9]+", " ", spaced)
    return [token.lower() for token in spaced.split() if not token.isdigit()]


def _matches_name_group(column: str, aliases: tuple[str, ...]) -> bool:
    return any(token in aliases for token in _tokenize_column_name(column))


def _matches_any_fragment(column: str, fragments: tuple[str, ...]) -> bool:
    normalized = _normalize_column_name(column)
    return any(fragment in normalized for fragment in fragments)


def _extract_unit(column: str) -> str | None:
    match = re.search(r"[\(\[]([^\)\]]+)[\)\]]", column)
    return match.group(1).strip() if match else None


def _display_name(column: str) -> str:
    without_units = re.sub(r"[\(\[].*?[\)\]]", "", column).strip()
    without_trailing_id = re.sub(r"[_\s]+\d+$", "", without_units)
    spaced = without_trailing_id.replace("_", " ").strip()
    return spaced if spaced else column


def _safe_stem(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def analyze_dataframe(
    dataframe: pd.DataFrame,
    *,
    name: str = "dataset",
    constant_relative_tolerance: float = DEFAULT_CONSTANT_RELATIVE_TOLERANCE,
) -> DatasetAnalysis:
    """Convenience wrapper: analyze a DataFrame without holding an analyzer."""

    return DatasetAnalyzer(
        dataframe,
        name=name,
        constant_relative_tolerance=constant_relative_tolerance,
    ).analyze()
