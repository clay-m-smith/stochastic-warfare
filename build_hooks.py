"""Deterministic setuptools hooks for distributable application artifacts.

The repository keeps one authoritative catalog under ``data/``.  Wheel builds
copy that catalog into the package resource namespace; no generated copy is
tracked in the checkout.  Source distributions use an explicit file allowlist
and carry the resolved source revision so a wheel can be rebuilt without Git.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

PROJECT_ROOT = Path(os.path.abspath(__file__)).parent
if os.fspath(PROJECT_ROOT) not in sys.path:
    # Setuptools loads configured command classes by file location, so an
    # isolated backend does not necessarily expose the project root on
    # sys.path while importing this hook.
    sys.path.insert(0, os.fspath(PROJECT_ROOT))

from stochastic_warfare.application_paths import catalog_resource_manifest
from stochastic_warfare.build_identity import (
    PYTHON_DISTRIBUTION_LAYOUT,
    write_build_identity,
)
from stochastic_warfare.build_source import (
    SDIST_GENERATED_INPUT_FILES,
    SOURCE_REVISION_FILENAME,
    has_sdist_source_receipt_markers,
    prepare_clean_wheel_build_root,
    resolve_source_revision,
    validated_checkout_build_inputs,
    write_sdist_input_manifest,
)


def _source_revision() -> str:
    return resolve_source_revision(PROJECT_ROOT)


def _sdist_allowlist() -> list[str]:
    return list(validated_checkout_build_inputs(PROJECT_ROOT))


class CatalogBuildPy(build_py):
    """Stage the authoritative catalog and artifact identity into a wheel."""

    def run(self) -> None:
        if getattr(self, "editable_mode", False):
            # Editable installs execute directly from the checkout, where
            # ApplicationPaths and runtime Git provenance own resources and
            # identity.  Setuptools supplies an external temporary build_lib
            # for PEP 660 and no distributable artifact is produced here.
            super().run()
            return
        revision = _source_revision()
        build_root = prepare_clean_wheel_build_root(PROJECT_ROOT, Path(self.build_lib))
        super().run()
        destination = build_root / "stochastic_warfare/resources/data"
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        for entry in catalog_resource_manifest(PROJECT_ROOT / "data"):
            source = PROJECT_ROOT / "data" / entry.relative_path
            target = destination / entry.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if (
            not has_sdist_source_receipt_markers(PROJECT_ROOT)
            and _source_revision() != revision
        ):
            raise RuntimeError("source revision changed during wheel staging")
        write_build_identity(
            build_root,
            revision,
            artifact_layout=PYTHON_DISTRIBUTION_LAYOUT,
        )


class AllowlistedSdist(sdist):
    """Build an sdist containing only Python source and required catalog data."""

    def make_distribution(self) -> None:
        # Modern setuptools obtains its sdist file list from egg_info and does
        # not call sdist.get_file_list().  Replace it at the last stable seam,
        # immediately before the release tree is created.
        self.filelist.files[:] = _sdist_allowlist()
        self.filelist.sort()
        self.filelist.remove_duplicates()
        super().make_distribution()

    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        super().make_release_tree(base_dir, files)
        revision_path = Path(base_dir) / SOURCE_REVISION_FILENAME
        revision_path.write_text(_source_revision() + "\n", encoding="utf-8")
        manifest_inputs = list(files)
        manifest_inputs.extend(
            name
            for name in SDIST_GENERATED_INPUT_FILES
            if (Path(base_dir) / name).is_file()
        )
        write_sdist_input_manifest(
            Path(base_dir),
            _source_revision(),
            manifest_inputs,
        )
