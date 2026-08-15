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

Every experiment file is a table of columns, and `dataset_analyzer.py`
figures out what each column represents without being told:

1. **What is the x-axis (independent variable)?** This is whatever was
   intentionally swept during the run. Column names are checked in priority
   order:
   1. Magnetic Field
   2. Angle
   3. Temperature

   If none of those names are present, it falls back to statistics: whichever
   column changes the most smoothly and monotonically, has a large numeric
   range, and has many unique values is treated as the x-axis.

2. **What is constant?** Some columns barely move during a run — temperature
   is a common example, since it is usually held steady during a field
   sweep. If a column's values do not vary much relative to their average,
   it is classified as a constant parameter instead of something to plot,
   and its average (plus min/max/standard deviation) is recorded as
   metadata rather than plotted.

3. **What are the measurements?** Everything left over — not the x-axis,
   not constant, not acquisition bookkeeping like a timestamp — is a
   measured quantity. Typical examples are Frequency, Counter, and
   Resistance, but detection is not hardcoded to those names; any
   remaining numeric column qualifies.

4. **Generate the plots.** Once the x-axis and measurements are identified,
   one plot is generated for each: measurement vs. the independent
   variable, saved as a publication-quality PNG in `output/auto_plots/`.

## Project Files

- `experiment_loader.py` loads raw experiment files.
- `visualization.py` generates plots in `output/plots/`.
- `dataset_analyzer.py` automatically detects the independent variable,
  constant parameters, and measurements for a dataset, then generates plots
  in `output/auto_plots/`.
- `signal_processing.py` provides reusable analysis functions.
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
