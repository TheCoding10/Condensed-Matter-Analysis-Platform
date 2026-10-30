# NHMFL Condensed Matter Analysis Platform

Tools for loading, plotting, analyzing, and searching condensed matter
experiment data from NHMFL/Tallahassee measurement campaigns: a command-line
interface, a FastAPI backend, and a React web dashboard.

## What This Project Does

- Loads experiment text files into pandas DataFrames.
- Extracts metadata and experiment ranges.
- Generates publication-quality scientific plots.
- Runs signal-processing analyses including peaks, oscillations, FFT, and noise
  statistics.
- Searches experiments by temperature, magnetic field, peak count,
  oscillations, and signal-to-noise ratio.
- Exports search results to CSV.

## How Automatic Dataset Analysis Works

`dataset_analyzer.py` decides what to plot the way the group reads the data:
changes in the material show up in a resonant **frequency**, measured
against a **swept control parameter**.

1. **Y-axis: the frequency signal.** In pulsed-field runs this is the
   frequency itself (`FQ1`, `FQ2`); in DC-field runs it is called `Counter`.
   These are always plotted, even when the shift is only parts per million.
   Control parameters (field, angle, temperature) and thermometer readings
   (`Cernox_R`, `SmpCrnx_R`) are never put on the y-axis. Only when a run
   has no frequency column does it fall back to other measured columns.

2. **X-axis: what was swept.** Candidates are checked in this order:
   1. Magnetic field (`Field`)
   2. Angle (`Angle`, or rotator `Steps`)
   3. Temperature (rarely; `RuO_T`, `Cx_T`, `Cernox_T`, `DR_Temp`, ...)

   A control parameter counts as *swept* only if it moves over a real range
   (≥ 0.5 T, ≥ 2°, ≥ 20 rotator steps, or ≥ 5% of the temperature) **and**
   fills that range continuously. A one-off jump (e.g. the rotator moved
   once at the end of a run) is not a sweep. If nothing was swept, the
   signal is plotted against time.

3. **Fixed parameters.** Control parameters that were not swept are
   reported with their average value and printed on each plot. Ones that
   drifted during the run (typically the thermometer during a field sweep)
   are listed as "also changed" but not plotted.

4. **Quantum oscillations.** Oscillations only appear when the field is
   swept, so for field sweeps `quantum_oscillations.py` repeats the group's
   Igor `FFThan` analysis (from `ETNH4Mar2020SdH.pxp`) automatically:
   take one sweep direction in the top third of the field range, convert to
   1/B, interpolate onto a uniform grid, subtract a 5th-order polynomial
   background, and FFT. The x-axis of the spectrum is the oscillation
   frequency in tesla. A peak is reported as an oscillation when it is
   sharp (≥ 30× the spectrum a few resolution widths away) and holds ≥ 20%
   of the residual power together with its harmonics. These thresholds were
   calibrated by eye on the March 2020 and June 2022 sweeps; for example,
   the ETNH4 runs Agosta.332–371 give ~576 T.

Instrument "no reading" values (~9.91e37) and zero-frequency dropouts are
removed before any of this runs. Plots go to `output/auto_plots/`.

## Project Files

- `experiment_loader.py` loads raw experiment files.
- `visualization.py` generates plots in `output/plots/`.
- `dataset_analyzer.py` automatically detects the independent variable,
  constant parameters, and measurements for a dataset, then generates plots
  in `output/auto_plots/`.
- `signal_processing.py` provides reusable analysis functions.
- `quantum_oscillations.py` finds 1/B-periodic (SdH/dHvA) oscillations in
  field sweeps and plots the residual and its FFT.
- `search_engine.py` searches and ranks experiments.
- `main.py` provides the command-line interface.
- `api.py` provides a FastAPI backend (REST API) over the same modules.
- `frontend/` is a React + Vite web dashboard that talks to `api.py`. See
  `frontend/README.md` for setup.

## Web Dashboard

Run the backend and frontend in two terminals:

```bash
# Terminal 1: API (from the repo root)
python3 -m pip install -r requirements.txt
uvicorn api:app --reload

# Terminal 2: frontend
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`. The dashboard lets you load a dataset,
view the summary, search experiments, and browse per-experiment plots.

## Setup

```bash
python3 -m pip install -r requirements.txt
```

For the NHMFL March 2020 dataset, place the dataset ZIP at:

```text
~/Downloads/NHMFLMarch2020Data-20260630T191837Z-3-001.zip
```

or pass a dataset path explicitly:

```bash
python3 main.py --dataset /path/to/NHMFLMarch2020Data --summary
```

For the Tallahassee June 2022 dataset, pass the flat folder path:

```bash
python3 main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --summary
```

On this machine, the Anaconda Python already has the scientific dependencies
installed. If plain `python3` cannot import pandas, use:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --summary
```

The loader supports both the 2020 schema (`RuO_T`, `Counter`, `Angle`) and the
2022 schema (`FQ1`, `FQ2`, `Cernox_T`, `DR_Temp`, optional angle).

## All Command-Line Options

| Flag | Argument(s) | Description |
| --- | --- | --- |
| `--dataset` | `PATH` | Path to an extracted dataset folder or ZIP archive. Defaults to `NHMFLMarch2020Data/` or the default ZIP in `~/Downloads/` if omitted. |
| `--summary` | | Generate a dataset-level summary report (temperature/field ranges, oscillation count, top SNR, top peak counts). |
| `--plot` | | Generate the standard field/temperature/counter plots for matching experiments. |
| `--auto-analyze` | | Automatically detect the independent variable, constant parameters, and measurements for matching experiments, then plot every measurement against the detected independent variable. |
| `--temperature` | `MIN MAX` | Find experiments overlapping a temperature range. |
| `--field` | `MIN MAX` | Find experiments overlapping a magnetic-field range. |
| `--oscillations` | | Find experiments containing oscillatory signal structure. |
| `--peaks` | `MIN` | Find experiments with more than `MIN` detected peaks. |
| `--snr` | | Rank experiments by signal-to-noise ratio. |
| `--top` | `N` (default `10`) | Limit displayed and exported search results. |
| `--experiment` | `FILE` | Restrict analysis or plotting to one filename, e.g. `Agosta.001.txt`. |
| `--export` | | Export search results or the summary report to CSV in `output/results/`. |
| `--verbose` | | Enable verbose (debug-level) logging. |

Search flags (`--temperature`, `--field`, `--oscillations`, `--peaks`,
`--snr`) can be combined; matching experiments are merged and ranked by
combined score. `--plot` and `--auto-analyze` apply to whatever experiments
were selected by `--experiment` or a search; with no selection, they apply
to the whole loaded dataset.

## Example Commands

```bash
python3 main.py --summary
python3 main.py --temperature 0.5 2.0
python3 main.py --field 0 16 --top 20
python3 main.py --oscillations --top 10
python3 main.py --snr --top 10 --export
python3 main.py --experiment Agosta.001.txt --plot
python3 main.py --experiment Agosta.001.txt --auto-analyze
python3 main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --field 20 28
python3 main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --experiment Clark_SCM4.007.txt --plot
```

## NHMFL March 2020 Commands

Use this pattern when the dataset ZIP is in the default Downloads location:

```bash
cd /Users/prayasthapa/nhmfl-analysis-platform
/opt/anaconda3/bin/python main.py [COMMAND]
```

Or pass the ZIP path explicitly:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/NHMFLMarch2020Data-20260630T191837Z-3-001.zip [COMMAND]
```

Generate a dataset summary:

```bash
/opt/anaconda3/bin/python main.py --summary
```

Search by temperature range:

```bash
/opt/anaconda3/bin/python main.py --temperature 0.5 2.0 --top 10
```

Search high magnetic-field experiments:

```bash
/opt/anaconda3/bin/python main.py --field 0 16 --top 10
```

Find oscillatory experiments:

```bash
/opt/anaconda3/bin/python main.py --oscillations --top 10
```

Rank experiments by signal-to-noise ratio:

```bash
/opt/anaconda3/bin/python main.py --snr --top 10
```

Find experiments with many detected peaks:

```bash
/opt/anaconda3/bin/python main.py --peaks 1000 --top 10
```

Generate plots for one experiment:

```bash
/opt/anaconda3/bin/python main.py --experiment Agosta.001.txt --plot
```

Search high-field experiments and plot the top 5:

```bash
/opt/anaconda3/bin/python main.py --field 0 16 --top 5 --plot
```

Export search results to CSV:

```bash
/opt/anaconda3/bin/python main.py --field 0 16 --top 20 --export
```

Automatically detect structure and plot every measurement for one experiment:

```bash
/opt/anaconda3/bin/python main.py --experiment Agosta.001.txt --auto-analyze
```

Search high-field experiments and auto-analyze the top 5:

```bash
/opt/anaconda3/bin/python main.py --field 0 16 --top 5 --auto-analyze
```

## Tallahassee June 2022 Commands

Use this pattern:

```bash
cd /Users/prayasthapa/nhmfl-analysis-platform
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June [COMMAND]
```

Generate a dataset summary:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --summary
```

Search high magnetic-field experiments:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --field 20 28 --top 10
```

Search by temperature range:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --temperature 0.03 0.3 --top 10
```

Find oscillatory experiments:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --oscillations --top 10
```

Rank experiments by signal-to-noise ratio:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --snr --top 10
```

Find experiments with many detected peaks:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --peaks 100 --top 10
```

Generate plots for one experiment:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --experiment Clark_SCM4.007.txt --plot
```

Search high-field experiments and plot the top 5:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --field 20 28 --top 5 --plot
```

Export search results to CSV:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --field 20 28 --top 20 --export
```

Automatically detect structure and plot every measurement for one experiment:

```bash
/opt/anaconda3/bin/python main.py --dataset /Users/prayasthapa/Downloads/Tallahassee2022June --experiment Clark_SCM4.007.txt --auto-analyze
```

## Outputs

Generated files are written to:

```text
output/plots/
output/auto_plots/
output/results/
```

The raw dataset and generated outputs are intentionally ignored by Git.
