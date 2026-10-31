"""FastAPI backend exposing the NHMFL analysis CLI as a REST API.

A thin HTTP front end over the existing CLI modules. It does not reimplement
any analysis logic -- every endpoint calls the same functions main.py wires
up for the command line.
"""

from __future__ import annotations

import base64
import math
import os
import secrets
import threading
from pathlib import Path
from typing import Optional

# On Vercel the project directory is read-only and every request may run on a
# fresh instance: write scratch files to /tmp, send plots inline, and use a
# lighter DPI so responses stay under the 4.5 MB limit.
ON_VERCEL = bool(os.environ.get("VERCEL"))
if ON_VERCEL:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    os.environ.setdefault("PLOT_DPI", "150")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import main as cli
import remote_data
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


OUTPUT_DIR = Path("/tmp/output") if ON_VERCEL else Path("output")
INLINE_PLOTS = ON_VERCEL
cli.RESULTS_DIR = OUTPUT_DIR / "results"
cli.PLOTS_DIR = OUTPUT_DIR / "plots"
cli.AUTO_PLOTS_DIR = OUTPUT_DIR / "auto_plots"
cli.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
cli.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
cli.AUTO_PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Folder holding the dataset folders when running locally.
DATA_ROOT = os.environ.get("NHMFL_DATA_ROOT", "~/Downloads")

# Short names researchers can type or click instead of a full filesystem path.
# `remote_prefix` is the folder inside the Hugging Face dataset used by the
# hosted deployment (see remote_data.py).
DATASET_ALIASES: dict[str, dict[str, str]] = {
    "nhmfl2020": {
        "label": "NHMFL March 2020",
        "path": f"{DATA_ROOT}/NHMFLMarch2020Data",
        "remote_prefix": "NHMFLMarch2020Data/data",
    },
    "tallahassee2022": {
        "label": "Tallahassee June 2022",
        "path": f"{DATA_ROOT}/Tallahassee2022June",
        "remote_prefix": "Tallahassee2022June",
    },
}

# When set (the hosted deployment), every API call and plot image must carry
# this password, as an X-App-Password header or a ?key= query parameter.
APP_PASSWORD = os.environ.get("APP_PASSWORD") or None
AUTH_EXEMPT_PATHS = {"/api/auth/check"}

app = FastAPI(title="NHMFL Condensed Matter Analysis API")


def _password_ok(request: Request) -> bool:
    if APP_PASSWORD is None:
        return True
    supplied = request.headers.get("x-app-password") or request.query_params.get("key") or ""
    return secrets.compare_digest(supplied.encode(), APP_PASSWORD.encode())


@app.middleware("http")
async def require_password(request: Request, call_next):
    protected = request.url.path.startswith(("/api/", "/output/"))
    if (
        protected
        and request.method != "OPTIONS"
        and request.url.path not in AUTH_EXEMPT_PATHS
        and not _password_ok(request)
    ):
        return JSONResponse(status_code=401, content={"detail": "Password required."})
    return await call_next(request)


# Added after the password check so it wraps it: 401s still get CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# Loaded datasets, keyed by the name or path the user loaded. The frontend
# repeats that key in an X-Dataset header on every request, because on Vercel
# consecutive requests may land on different instances; an instance that
# hasn't seen the dataset yet loads it on demand.
_datasets: dict[str, cli.DatasetLoadResult] = {}
_single_files: dict[tuple[str, str], Experiment] = {}
_load_lock = threading.Lock()
_state: dict[str, object] = {"current": None, "last_search_results": None}


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


def _dataset_key(request: Request) -> str:
    key = request.headers.get("x-dataset") or _state["current"]
    if not key:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    return str(key)


def _remote_prefix(key: str) -> str:
    alias = DATASET_ALIASES.get(key.strip().lower())
    if alias is None:
        names = ", ".join(DATASET_ALIASES)
        raise HTTPException(status_code=400, detail=f"Unknown dataset '{key}'. Choose one of: {names}.")
    return alias["remote_prefix"]


def _load_dataset(key: str) -> cli.DatasetLoadResult:
    with _load_lock:
        if key not in _datasets:
            try:
                if remote_data.enabled():
                    _datasets[key] = remote_data.load_dataset(_remote_prefix(key))
                else:
                    _datasets[key] = cli.load_dataset(_resolve_requested_path(key))
            except (FileNotFoundError, ValueError) as error:
                raise HTTPException(status_code=400, detail=str(error))
        return _datasets[key]


def _get_experiments(request: Request) -> list[Experiment]:
    return _load_dataset(_dataset_key(request)).experiments


def _find_experiment(request: Request, filename: str) -> Experiment:
    key = _dataset_key(request)
    if key not in _datasets and remote_data.enabled():
        # Analyzing one file shouldn't wait for the whole dataset to download.
        cache_key = (key, filename)
        if cache_key not in _single_files:
            try:
                _single_files[cache_key] = remote_data.load_file(_remote_prefix(key), filename)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"Experiment not found: {filename}")
            except ValueError as error:
                raise HTTPException(status_code=400, detail=f"Could not read {filename}: {error}")
        return _single_files[cache_key]

    for experiment in _get_experiments(request):
        if Path(experiment.filename).name == filename:
            return experiment
    raise HTTPException(status_code=404, detail=f"Experiment not found: {filename}")


def _detect_columns(experiment: Experiment):
    try:
        return detect_columns(experiment)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def _plot_url(path: Path) -> str:
    if INLINE_PLOTS:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        path.unlink(missing_ok=True)
        return f"data:image/png;base64,{encoded}"
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


@app.get("/api/auth/check")
def auth_check(request: Request):
    return {"required": APP_PASSWORD is not None, "ok": _password_ok(request)}


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
    if remote_data.enabled():
        # Listing is enough here; files download when they're first used.
        key = (request.path or "nhmfl2020").strip().lower()
        filenames = [Path(path).name for path in remote_data.list_files(_remote_prefix(key))]
        _state["current"] = key
        return {"dataset": key, "count": len(filenames), "skipped": 0, "filenames": filenames}

    key = request.path or str(cli.resolve_dataset_path(None))
    _datasets.pop(key, None)  # an explicit load always re-reads the files
    load_result = _load_dataset(key)
    _state["current"] = key
    _state["last_search_results"] = None
    return {
        "dataset": key,
        "count": len(load_result.experiments),
        "skipped": load_result.skipped_count,
        "filenames": [Path(e.filename).name for e in load_result.experiments],
    }


@app.get("/api/experiments")
def list_experiments(request: Request):
    key = _dataset_key(request)
    if remote_data.enabled() and key not in _datasets:
        return {"filenames": [Path(p).name for p in remote_data.list_files(_remote_prefix(key))]}
    return {"filenames": [Path(e.filename).name for e in _get_experiments(request)]}


@app.get("/api/experiments/{filename}/guide")
def experiment_guide(filename: str, request: Request):
    experiment = _find_experiment(request, filename)
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
            "secondary_sweeps": list(analysis.secondary_sweeps),
        },
        "preview_columns": [str(c) for c in preview.columns],
        "preview_rows": _records(preview),
    }


@app.get("/api/experiments/{filename}/standard-plots")
def standard_plots(filename: str, request: Request):
    experiment = _find_experiment(request, filename)
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
def auto_analyze(filename: str, request: Request):
    experiment = _find_experiment(request, filename)
    name = Path(experiment.filename).stem
    analyzer = DatasetAnalyzer(experiment.dataframe, name=name)
    analysis = analyzer.analyze()
    plots = analyzer.generate_plots(output_dir=cli.AUTO_PLOTS_DIR)
    oscillations = analyzer.analyze_oscillations()

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
        "secondary_sweeps": list(analysis.secondary_sweeps),
        "oscillations": [
            {
                "signal": result.signal_column,
                "detected": result.detected,
                "dominant_frequency_tesla": result.dominant_frequency_tesla,
                # inf (a perfectly isolated peak) is not valid JSON.
                "peak_sharpness": result.peak_sharpness if math.isfinite(result.peak_sharpness) else None,
                "peak_concentration": result.peak_concentration,
                "field_window": list(result.field_window),
                "sweep_direction": result.sweep_direction,
            }
            for result in oscillations
        ],
        "plots": [
            {
                "measurement": plot.measurement,
                "independent_variable": plot.independent_variable,
                "kind": plot.kind,
                "url": _plot_url(plot.path),
            }
            for plot in plots
        ],
    }


@app.get("/api/summary")
def summary(request: Request):
    load_result = _load_dataset(_dataset_key(request))
    experiments = load_result.experiments
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


def _export_response(path: Path) -> dict:
    # The file lives on the server; send its contents so the browser can
    # save it (on Vercel the server copy disappears with the instance).
    return {"path": str(path), "filename": path.name, "content": path.read_text(encoding="utf-8")}


@app.post("/api/summary/export")
def export_summary(request: Request):
    load_result = _load_dataset(_dataset_key(request))
    report = cli.generate_summary_report(load_result.experiments, skipped_count=load_result.skipped_count)
    return _export_response(cli.export_summary_report(report))


@app.post("/api/search")
def search(request: SearchRequest, http_request: Request):
    results = _run_search(request, _get_experiments(http_request))
    _state["last_search_results"] = results
    return {"results": [_result_to_dict(result) for result in results]}


def _run_search(request: SearchRequest, experiments: list[Experiment]) -> list[SearchResult]:
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
        return []
    return top_n(cli.merge_result_sets(result_sets), request.top)


@app.post("/api/search/export")
def export_search(http_request: Request, request: Optional[SearchRequest] = None):
    # The frontend re-sends the search, since the instance that ran it may
    # be gone; without a body, fall back to this instance's last search.
    if request is not None:
        results = _run_search(request, _get_experiments(http_request))
    else:
        results = _state.get("last_search_results")
    if not results:
        raise HTTPException(status_code=400, detail="No search results to export. Run a search first.")
    return _export_response(cli.export_search_results(results))
