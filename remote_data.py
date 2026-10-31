"""Fetch experiment files from the private Hugging Face dataset.

The hosted deployment (Vercel) has no local copy of the data. When
NHMFL_DATA_REPO is set, the API reads experiments from that Hugging Face
dataset instead, authenticating with HF_TOKEN. Files are read straight into
memory; nothing is written to disk.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import logging
import os
from pathlib import PurePosixPath

import pandas as pd

from experiment_loader import Experiment, read_experiment_file
from main import DatasetLoadResult


LOGGER = logging.getLogger(__name__)

DATA_REPO = os.environ.get("NHMFL_DATA_REPO") or None
DOWNLOAD_THREADS = 16


def enabled() -> bool:
    return DATA_REPO is not None


def list_files(prefix: str) -> list[str]:
    """Repo paths of the experiment files directly under `prefix`."""

    from huggingface_hub import HfApi

    paths = HfApi(token=_token()).list_repo_files(DATA_REPO, repo_type="dataset")
    folder = PurePosixPath(prefix)
    return sorted(
        path
        for path in paths
        if PurePosixPath(path).parent == folder and path.endswith(".txt")
    )


def load_file(prefix: str, filename: str) -> Experiment:
    """Download and parse one experiment file."""

    path = str(PurePosixPath(prefix) / filename)
    return read_experiment_file(filename, BytesIO(_fetch(path)))


def load_dataset(prefix: str) -> DatasetLoadResult:
    """Download and parse every experiment file under `prefix`."""

    paths = list_files(prefix)
    with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
        outcomes = list(pool.map(_try_load, paths))

    experiments = [outcome for outcome in outcomes if isinstance(outcome, Experiment)]
    return DatasetLoadResult(
        experiments=experiments,
        source_count=len(paths),
        skipped_empty=sum(1 for outcome in outcomes if outcome == "empty"),
        skipped_corrupted=sum(1 for outcome in outcomes if outcome == "corrupted"),
    )


def _try_load(path: str) -> Experiment | str:
    # Mirrors main._load_folder_dataset's skip rules.
    name = PurePosixPath(path).name
    try:
        return read_experiment_file(name, BytesIO(_fetch(path)))
    except ValueError as error:
        if "empty file" in str(error):
            return "empty"
        LOGGER.warning("Skipping corrupted file %s: %s", path, error)
        return "corrupted"
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
        LOGGER.warning("Skipping unreadable file %s: %s", path, error)
        return "corrupted"


def _fetch(path: str) -> bytes:
    from huggingface_hub import HfFileSystem

    return HfFileSystem(token=_token()).cat_file(f"datasets/{DATA_REPO}/{path}")


def _token() -> str | None:
    return os.environ.get("HF_TOKEN") or None
