#!/usr/bin/env python

import logging
import os
from pathlib import Path

import hydra
from omegaconf import DictConfig

from . import (
    DEFAULT_TABLE_PREPROCESSORS_CFG,
    ETL_CFG,
    EVENT_CFG,
    HAS_PRE_MEDS,
    MAIN_CFG,
    RUNNER_CFG,
)
from . import __version__ as PKG_VERSION
from . import dataset_info
from .commands import run_command
from .download import download_data

if HAS_PRE_MEDS:
    from .pre_MEDS import main as pre_MEDS_transform

logger = logging.getLogger(__name__)


@hydra.main(version_base=None, config_path=str(MAIN_CFG.parent), config_name=MAIN_CFG.stem)
def main(cfg: DictConfig):
    """Runs the end-to-end MEDS Extraction pipeline."""
    if cfg.input_dir:
        raw_input_dir = Path(cfg.input_dir)
    pre_MEDS_dir = Path(cfg.pre_MEDS_dir)
    MEDS_cohort_dir = Path(cfg.MEDS_cohort_dir)
    stage_runner_fp = cfg.get("stage_runner_fp", None)
    output_dir = Path(cfg.output_dir)

    # Step 0: Data downloading
    if cfg.do_download:  # pragma: no cover
        if cfg.input_dir:
            if raw_input_dir.exists() and any(raw_input_dir.iterdir()):
                raise ValueError(
                    f"Input directory {cfg.input_dir} is not empty. "
                    f"Please specify an empty directory to download AUMCdb. "
                    f"Alternatively, if no input directory is specified, "
                    f"the data will be downloaded to the output directory. "
                )
        else:
            raw_input_dir = output_dir / "raw_input"
        raw_input_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading data into {raw_input_dir}.")
        download_data(raw_input_dir, dataset_info)
    elif not cfg.input_dir:
        raise ValueError("No input directory specified and download is disabled.")
    else:
        # pragma: no cover
        logger.info("Skipping data download.")

    # Step 1: Pre-MEDS Data Wrangling
    if HAS_PRE_MEDS:
        if (table_preprocessors_config_fp := cfg.table_preprocessors_config_fp) is None:
            table_preprocessors_config_fp = DEFAULT_TABLE_PREPROCESSORS_CFG
        pre_MEDS_transform(
            raw_input_dir,
            pre_MEDS_dir,
            table_preprocessors_config_fp,
            cfg.get("do_overwrite", None),
        )
    else:
        pre_MEDS_dir = raw_input_dir

    # Step 2: MEDS Cohort Creation
    # First we need to set some environment variables
    command_parts = [
        f"DATASET_NAME={dataset_info.dataset_name}",
        f"DATASET_VERSION={dataset_info.raw_dataset_version}:{PKG_VERSION}",
        f"EVENT_CONVERSION_CONFIG_FP={str(EVENT_CFG.resolve())}",
        f"PRE_MEDS_DIR={str(pre_MEDS_dir.resolve())}",
        f"MEDS_COHORT_DIR={str(MEDS_cohort_dir.resolve())}",
    ]

    # Then we construct the rest of the command
    command_parts.extend(
        [
            "MEDS_transform-runner",
            f"--config-path={str(RUNNER_CFG.parent.resolve())}",
            f"--config-name={RUNNER_CFG.stem}",
            f"pipeline_config_fp={str(ETL_CFG.resolve())}",
        ]
    )
    if int(os.getenv("N_WORKERS", 1)) <= 1:
        logger.info("Running in serial mode as N_WORKERS is not set.")
        command_parts.append("~parallelize")

    if stage_runner_fp:
        command_parts.append(f"stage_runner_fp={stage_runner_fp}")

    command_parts.append("'hydra.searchpath=[pkg://MEDS_transforms.configs]'")
    run_command(command_parts, cfg)


if __name__ == "__main__":
    main()
