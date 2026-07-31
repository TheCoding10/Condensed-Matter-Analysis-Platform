"""Browser-based front end for the NHMFL analysis platform.

Run with: streamlit run app.py

A thin Streamlit UI over the existing CLI modules. It does not reimplement
any analysis logic — every action here calls the same functions main.py
wires up for the command line, and the sidebar shows the equivalent CLI
command for whatever is currently configured.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import main as cli
from dataset_analyzer import DatasetAnalyzer
from experiment_loader import Experiment
from search_engine import (
    SearchResult,
    find_by_magnetic_field_range,
    find_by_temperature_range,
    find_containing_oscillations,
    find_with_more_than_n_peaks,
    rank_by_signal_to_noise_ratio,
    top_n,
)
from visualization import detect_columns, make_line_plot


COMMAND_REFERENCE = """
| Flag | Meaning |
|---|---|
| `--dataset PATH` | Extracted dataset folder or `.zip` archive |
| `--summary` | Dataset-wide summary report |
| `--plot` | Standard plots: field vs counter, field vs temperature, timestamp vs field |
| `--auto-analyze` | Auto-detect x-axis, constants, measurements; plot every measurement vs x-axis |
| `--temperature MIN MAX` | Find experiments overlapping a temperature range |
| `--field MIN MAX` | Find experiments overlapping a magnetic-field range |
| `--oscillations` | Find experiments with oscillatory signal structure |
| `--peaks MIN` | Find experiments with more than MIN detected peaks |
| `--snr` | Rank experiments by signal-to-noise ratio |
| `--top N` | Limit displayed/exported results (default 10) |
| `--experiment FILE` | Restrict to one filename |
| `--export` | Export results/summary to CSV in `output/results/` |
| `--verbose` | Enable verbose logging |
"""

cli.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
cli.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
cli.AUTO_PLOTS_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="NHMFL Analysis Platform", layout="wide")

if "experiments" not in st.session_state:
    st.session_state.experiments = None
if "load_result" not in st.session_state:
    st.session_state.load_result = None


def find_experiment(experiments: list[Experiment], filename: str) -> Experiment:
    return next(e for e in experiments if Path(e.filename).name == filename)


def render_standard_plots(experiment: Experiment) -> None:
    columns = detect_columns(experiment)
    specs = [
        (columns.counter or columns.primary_measurement, columns.magnetic_field,
         "Magnetic Field vs Counter"),
        (columns.temperature, columns.magnetic_field, "Magnetic Field vs Temperature"),
        (columns.timestamp, columns.magnetic_field, "Timestamp vs Magnetic Field"),
    ]
    display_columns = st.columns(3)
    for panel, (x_column, y_column, title) in zip(display_columns, specs):
        if x_column is None or y_column is None:
            panel.info("Not available for this experiment.")
            continue
        figure, _axis = make_line_plot(
            experiment, x_column=x_column, y_column=y_column, title=title
        )
        panel.pyplot(figure)
        plt.close(figure)


def render_auto_analysis(experiment: Experiment) -> None:
    name = Path(experiment.filename).stem
    analyzer = DatasetAnalyzer(experiment.dataframe, name=name)
    analysis = analyzer.analyze()

    x_label = analysis.independent_variable_category or analysis.independent_variable
    st.metric("Detected X-axis", x_label or "none")

    if analysis.constant_parameters:
        st.write("**Constant parameters** (averaged)")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "parameter": parameter.column,
                        "average": parameter.average,
                        "min": parameter.minimum,
                        "max": parameter.maximum,
                        "unit": parameter.unit or "",
                    }
                    for parameter in analysis.constant_parameters
                ]
            ),
            width="stretch",
        )
    else:
        st.write("**Constant parameters:** none")

    if not analysis.measurements:
        st.warning("No measurement columns detected.")
        return

    st.write(f"**Measurements** ({len(analysis.measurements)}): "
             + ", ".join(analysis.measurements))

    plots = analyzer.generate_plots(output_dir=cli.AUTO_PLOTS_DIR)
    display_columns = st.columns(2)
    for index, plot in enumerate(plots):
        display_columns[index % 2].image(
            str(plot.path), caption=f"{plot.measurement} vs {plot.independent_variable}"
        )


def search_results_table(results: list[SearchResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        stats = result.signal_statistics
        rows.append(
            {
                "filename": Path(result.filename).name,
                "score": round(result.matching_score, 4),
                "reason": result.reason,
                "signal": stats.signal_column or "",
                "temperature range": _format_range(
                    stats.min_temperature, stats.max_temperature
                ),
                "field range": _format_range(
                    stats.min_magnetic_field, stats.max_magnetic_field
                ),
            }
        )
    return pd.DataFrame(rows)


def _format_range(minimum: float | None, maximum: float | None) -> str:
    if minimum is None or maximum is None:
        return ""
    return f"{minimum:.3g} to {maximum:.3g}"


st.title("NHMFL Condensed Matter Analysis Platform")

st.sidebar.header("Dataset")
dataset_path_input = st.sidebar.text_input(
    "Dataset folder or ZIP path",
    value="",
    placeholder=str(cli.DEFAULT_DATASET_PATH),
    help="Folder containing experiment .txt files (or a subfolder named 'data'), "
    "or a .zip archive.",
)

if st.sidebar.button("Load dataset", type="primary"):
    try:
        requested_path = (
            Path(dataset_path_input).expanduser()
            if dataset_path_input
            else cli.resolve_dataset_path(None)
        )
        with st.spinner(f"Loading dataset from {requested_path}..."):
            load_result = cli.load_dataset(requested_path)
        st.session_state.experiments = load_result.experiments
        st.session_state.load_result = load_result
        st.sidebar.success(
            f"Loaded {len(load_result.experiments)} experiment(s), "
            f"skipped {load_result.skipped_count}."
        )
    except (FileNotFoundError, ValueError) as error:
        st.sidebar.error(f"Failed to load dataset: {error}")

experiments = st.session_state.experiments

st.sidebar.divider()
st.sidebar.header("Action")
action = st.sidebar.radio(
    "Choose an action", ["Summary", "Standard Plots", "Auto-Analyze", "Search"]
)

filenames = [Path(e.filename).name for e in experiments] if experiments else []
selected_filename = None
if action in ("Standard Plots", "Auto-Analyze") and filenames:
    selected_filename = st.sidebar.selectbox("Experiment", filenames)

use_field = use_temperature = use_oscillations = use_peaks = use_snr = False
field_min = field_max = temperature_min = temperature_max = 0.0
peaks_min = 0
top_n_value = 10
if action == "Search":
    st.sidebar.subheader("Filters")
    use_field = st.sidebar.checkbox("Magnetic field range")
    if use_field:
        field_min, field_max = st.sidebar.columns(2)
        field_min = field_min.number_input("Field min (T)", value=0.0)
        field_max = field_max.number_input("Field max (T)", value=16.0)
    use_temperature = st.sidebar.checkbox("Temperature range")
    if use_temperature:
        temperature_min, temperature_max = st.sidebar.columns(2)
        temperature_min = temperature_min.number_input("Temp min (K)", value=0.0)
        temperature_max = temperature_max.number_input("Temp max (K)", value=2.0)
    use_oscillations = st.sidebar.checkbox("Oscillatory signals only")
    use_peaks = st.sidebar.checkbox("Minimum peak count")
    if use_peaks:
        peaks_min = st.sidebar.number_input("Min peaks", min_value=0, value=100)
    use_snr = st.sidebar.checkbox("Rank by signal-to-noise ratio")
    top_n_value = st.sidebar.number_input("Top N results", min_value=1, value=10)

cli_parts = ["python main.py"]
if dataset_path_input:
    cli_parts.append(f'--dataset "{dataset_path_input}"')
if action == "Summary":
    cli_parts.append("--summary")
elif action == "Standard Plots":
    cli_parts.append("--plot")
    if selected_filename:
        cli_parts.append(f"--experiment {selected_filename}")
elif action == "Auto-Analyze":
    cli_parts.append("--auto-analyze")
    if selected_filename:
        cli_parts.append(f"--experiment {selected_filename}")
elif action == "Search":
    if use_field:
        cli_parts.append(f"--field {field_min} {field_max}")
    if use_temperature:
        cli_parts.append(f"--temperature {temperature_min} {temperature_max}")
    if use_oscillations:
        cli_parts.append("--oscillations")
    if use_peaks:
        cli_parts.append(f"--peaks {peaks_min}")
    if use_snr:
        cli_parts.append("--snr")
    cli_parts.append(f"--top {top_n_value}")

st.sidebar.divider()
st.sidebar.subheader("Equivalent CLI command")
st.sidebar.code(" ".join(cli_parts), language="bash")

with st.sidebar.expander("Command reference"):
    st.markdown(COMMAND_REFERENCE)

if experiments is None:
    st.info("Enter a dataset path in the sidebar and click **Load dataset** to begin.")
else:
    if action == "Summary":
        report = cli.generate_summary_report(
            experiments, skipped_count=st.session_state.load_result.skipped_count
        )
        metric_columns = st.columns(3)
        metric_columns[0].metric("Total experiments", report["total_experiments"])
        metric_columns[1].metric("Skipped files", report["skipped_files"])
        metric_columns[2].metric(
            "Detected oscillations", report["detected_oscillation_count"]
        )

        range_columns = st.columns(2)
        range_columns[0].write("**Temperature range (K)**")
        range_columns[0].json(report["temperature"])
        range_columns[1].write("**Magnetic field range (T)**")
        range_columns[1].json(report["magnetic_field"])

        st.write("**Highest signal-to-noise experiments**")
        st.dataframe(search_results_table(report["highest_snr"]), width="stretch")

        st.write("**Largest peak counts**")
        st.dataframe(
            pd.DataFrame(
                report["largest_peak_counts"], columns=["filename", "peak_count"]
            ),
            width="stretch",
        )

        if st.button("Export summary to CSV"):
            path = cli.export_summary_report(report)
            st.success(f"Exported to {path}")

    elif action == "Standard Plots":
        if not selected_filename:
            st.warning("No experiments loaded.")
        else:
            experiment = find_experiment(experiments, selected_filename)
            st.subheader(selected_filename)
            render_standard_plots(experiment)

    elif action == "Auto-Analyze":
        if not selected_filename:
            st.warning("No experiments loaded.")
        else:
            experiment = find_experiment(experiments, selected_filename)
            st.subheader(selected_filename)
            render_auto_analysis(experiment)

    elif action == "Search":
        result_sets = []
        if use_field:
            result_sets.append(
                find_by_magnetic_field_range(experiments, field_min, field_max)
            )
        if use_temperature:
            result_sets.append(
                find_by_temperature_range(
                    experiments, temperature_min, temperature_max
                )
            )
        if use_oscillations:
            result_sets.append(find_containing_oscillations(experiments))
        if use_peaks:
            result_sets.append(find_with_more_than_n_peaks(experiments, peaks_min))
        if use_snr:
            result_sets.append(rank_by_signal_to_noise_ratio(experiments))

        if not result_sets:
            st.info("Enable at least one filter in the sidebar.")
        else:
            merged = cli.merge_result_sets(result_sets)
            results = top_n(merged, top_n_value)
            if not results:
                st.warning("No matching experiments found.")
            else:
                st.dataframe(search_results_table(results), width="stretch")

                if st.button("Export results to CSV"):
                    path = cli.export_search_results(results)
                    st.success(f"Exported to {path}")

                result_filenames = [Path(result.filename).name for result in results]
                inspect_filename = st.selectbox(
                    "Inspect an experiment from the results", result_filenames
                )
                inspect_experiment = find_experiment(experiments, inspect_filename)

                tab_standard, tab_auto = st.tabs(["Standard Plots", "Auto-Analyze"])
                with tab_standard:
                    render_standard_plots(inspect_experiment)
                with tab_auto:
                    render_auto_analysis(inspect_experiment)
