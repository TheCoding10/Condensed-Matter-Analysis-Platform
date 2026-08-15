"""FastAPI backend exposing the NHMFL analysis CLI as a REST API.

A thin HTTP front end over the existing CLI modules. It does not reimplement
any analysis logic -- every endpoint calls the same functions main.py wires
up for the command line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
from visualization import detect_columns, make_line_plot, save_figure


OUTPUT_DIR = Path("output")
cli.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
cli.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
cli.AUTO_PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Short names researchers can type or click instead of a full filesystem path.
DATASET_ALIASES: dict[str, dict[str, str]] = {
    "nhmfl2020": {
        "label": "NHMFL March 2020",
        "path": "~/Downloads/NHMFLMarch2020Data",
    },
    "tallahassee2022": {
        "label": "Tallahassee June 2022",
        "path": "~/Downloads/Tallahassee2022June",
    },
}

app = FastAPI(title="NHMFL Condensed Matter Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

_state: dict[str, object] = {"experiments": None, "load_result": None, "last_search_results": None}


class LoadDatasetRequest(BaseModel):
    path: Optional[str] = None


class SearchRequest(BaseModel):
    field_min: Optional[float] = None
    field_max: Optional[float] = None
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    oscillations: bool = False
    peaks_min: Optional[int] = None
    snr: bool = False
    top: int = 10


def _get_experiments() -> list[Experiment]:
    experiments = _state["experiments"]
    if experiments is None:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    return experiments


def _find_experiment(filename: str) -> Experiment:
    for experiment in _get_experiments():
        if Path(experiment.filename).name == filename:
            return experiment
    raise HTTPException(status_code=404, detail=f"Experiment not found: {filename}")


def _detect_columns(experiment: Experiment):
    try:
        return detect_columns(experiment)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def _plot_url(path: Path) -> str:
    return f"/output/{path.relative_to(OUTPUT_DIR).as_posix()}"


def _format_range(minimum: float | None, maximum: float | None) -> list[float] | None:
    if minimum is None or maximum is None:
        return None
    return [round(minimum, 6), round(maximum, 6)]


def _result_to_dict(result: SearchResult) -> dict:
    stats = result.signal_statistics
    return {
        "filename": Path(result.filename).name,
        "score": round(result.matching_score, 4),
        "reason": result.reason,
        "signal": stats.signal_column or "",
        "temperature_range": _format_range(stats.min_temperature, stats.max_temperature),
        "field_range": _format_range(stats.min_magnetic_field, stats.max_magnetic_field),
        "signal_to_noise_ratio": stats.signal_to_noise_ratio,
        "peak_count": stats.peak_count,
    }


def _records(frame: pd.DataFrame) -> list[dict]:
    sanitized = frame.astype(object).where(pd.notnull(frame), None)
    return sanitized.to_dict(orient="records")


@app.get("/api/dataset/default-path")
def default_path():
    return {"path": str(cli.DEFAULT_DATASET_PATH)}


@app.get("/api/dataset/aliases")
def dataset_aliases():
    return {
        "aliases": [
            {"name": name, "label": info["label"], "path": info["path"]}
            for name, info in DATASET_ALIASES.items()
        ]
    }


def _resolve_requested_path(raw_path: str) -> Path:
    alias = DATASET_ALIASES.get(raw_path.strip().lower())
    resolved = alias["path"] if alias else raw_path
    return Path(resolved).expanduser()


@app.post("/api/dataset/load")
def load_dataset(request: LoadDatasetRequest):
    try:
        requested_path = (
            _resolve_requested_path(request.path) if request.path else cli.resolve_dataset_path(None)
        )
        load_result = cli.load_dataset(requested_path)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))

    _state["experiments"] = load_result.experiments
    _state["load_result"] = load_result
    _state["last_search_results"] = None
    return {
        "count": len(load_result.experiments),
        "skipped": load_result.skipped_count,
        "filenames": [Path(e.filename).name for e in load_result.experiments],
    }


@app.get("/api/experiments")
def list_experiments():
    return {"filenames": [Path(e.filename).name for e in _get_experiments()]}


@app.get("/api/experiments/{filename}/guide")
def experiment_guide(filename: str):
    experiment = _find_experiment(filename)
    columns = _detect_columns(experiment)
    analyzer = DatasetAnalyzer(experiment.dataframe, name=Path(experiment.filename).stem)
    analysis = analyzer.analyze()
    preview = experiment.dataframe.head(20)
    return {
        "standard_plot_columns": {
            "magnetic_field": columns.magnetic_field,
            "timestamp": columns.timestamp,
            "temperature": columns.temperature,
            "angle": columns.angle,
            "counter": columns.counter,
            "primary_measurement": columns.primary_measurement,
        },
        "auto_analyze_structure": {
            "independent_variable": analysis.independent_variable,
            "category": analysis.independent_variable_category,
            "constant_parameters": [p.column for p in analysis.constant_parameters],
            "measurements": list(analysis.measurements),
        },
        "preview_columns": [str(c) for c in preview.columns],
        "preview_rows": _records(preview),
    }


@app.get("/api/experiments/{filename}/standard-plots")
def standard_plots(filename: str):
    experiment = _find_experiment(filename)
    columns = _detect_columns(experiment)
    specs = [
        (
            columns.counter or columns.primary_measurement,
            columns.magnetic_field,
            "Magnetic Field vs Counter",
        ),
        (columns.temperature, columns.magnetic_field, "Magnetic Field vs Temperature"),
        (columns.timestamp, columns.magnetic_field, "Timestamp vs Magnetic Field"),
    ]

    stem = Path(experiment.filename).stem
    plots = []
    for x_column, y_column, title in specs:
        if x_column is None or y_column is None:
            plots.append({"title": title, "url": None})
            continue
        figure, _axis = make_line_plot(experiment, x_column=x_column, y_column=y_column, title=title)
        suffix = title.lower().replace(" ", "_")
        path = cli.PLOTS_DIR / f"{stem}_{suffix}.png"
        save_figure(figure, path)
        plt.close(figure)
        plots.append({"title": title, "url": _plot_url(path)})

    return {"plots": plots}


@app.get("/api/experiments/{filename}/auto-analyze")
def auto_analyze(filename: str):
    experiment = _find_experiment(filename)
    name = Path(experiment.filename).stem
    analyzer = DatasetAnalyzer(experiment.dataframe, name=name)
    analysis = analyzer.analyze()
    plots = analyzer.generate_plots(output_dir=cli.AUTO_PLOTS_DIR)

    return {
        "x_label": analysis.independent_variable_category or analysis.independent_variable,
        "constant_parameters": [
            {
                "parameter": parameter.column,
                "average": parameter.average,
                "min": parameter.minimum,
                "max": parameter.maximum,
                "unit": parameter.unit or "",
            }
            for parameter in analysis.constant_parameters
        ],
        "measurements": list(analysis.measurements),
        "plots": [
            {
                "measurement": plot.measurement,
                "independent_variable": plot.independent_variable,
                "url": _plot_url(plot.path),
            }
            for plot in plots
        ],
    }


@app.get("/api/summary")
def summary():
    experiments = _get_experiments()
    load_result = _state["load_result"]
    report = cli.generate_summary_report(experiments, skipped_count=load_result.skipped_count)
    return {
        "total_experiments": report["total_experiments"],
        "skipped_files": report["skipped_files"],
        "temperature": report["temperature"],
        "magnetic_field": report["magnetic_field"],
        "detected_oscillation_count": report["detected_oscillation_count"],
        "highest_snr": [_result_to_dict(result) for result in report["highest_snr"]],
        "largest_peak_counts": [
            {"filename": Path(name).name, "peak_count": count}
            for name, count in report["largest_peak_counts"]
        ],
    }


@app.post("/api/summary/export")
def export_summary():
    experiments = _get_experiments()
    load_result = _state["load_result"]
    report = cli.generate_summary_report(experiments, skipped_count=load_result.skipped_count)
    path = cli.export_summary_report(report)
    return {"path": str(path)}


@app.post("/api/search")
def search(request: SearchRequest):
    experiments = _get_experiments()
    result_sets = []

    if request.field_min is not None and request.field_max is not None:
        result_sets.append(
            find_by_magnetic_field_range(experiments, request.field_min, request.field_max)
        )
    if request.temperature_min is not None and request.temperature_max is not None:
        result_sets.append(
            find_by_temperature_range(
                experiments, request.temperature_min, request.temperature_max
            )
        )
    if request.oscillations:
        result_sets.append(find_containing_oscillations(experiments))
    if request.peaks_min is not None:
        result_sets.append(find_with_more_than_n_peaks(experiments, request.peaks_min))
    if request.snr:
        result_sets.append(rank_by_signal_to_noise_ratio(experiments))

    if not result_sets:
        _state["last_search_results"] = None
        return {"results": []}

    merged = cli.merge_result_sets(result_sets)
    results = top_n(merged, request.top)
    _state["last_search_results"] = results
    return {"results": [_result_to_dict(result) for result in results]}


@app.post("/api/search/export")
def export_search():
    results = _state.get("last_search_results")
    if not results:
        raise HTTPException(status_code=400, detail="No search results to export. Run a search first.")
    path = cli.export_search_results(results)
    return {"path": str(path)}
