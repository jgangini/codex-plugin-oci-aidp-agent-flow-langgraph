"""Executable and declared environment identity without importing agent code."""
import hashlib
from pathlib import Path

from . import __version__
from .compatibility import observe_local
from .project import FlowError, canonical_hash, contained, load_project, python_path


def engine_identity():
    folder = Path(__file__).resolve().parent
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(folder.glob("*.py"))}
    return {"version": __version__, "sha256": canonical_hash(files)}


def environment_identity(root, executable=None):
    root, config = load_project(root)
    files = {}
    for relative in dict.fromkeys(("pyproject.toml", "uv.lock", config["agent"]["dependencies"])):
        path = contained(root, relative)
        if path.is_file():
            with path.open("rb") as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise FlowError("Environment declaration exceeds 8 MiB")
            files[relative] = hashlib.sha256(data).hexdigest()
    if executable is None:
        try:
            executable = python_path(root)
        except FlowError:
            executable = None
    observed = observe_local(executable)
    return {"declarations": files, "runtime": observed,
            "native_parity_verified": False,
            "coverage": "declared_files_and_supported_runtime_packages_not_all_transitive_dependencies"}


def execution_identity(root, executable=None):
    environment = environment_identity(root, executable)
    return {"engine_sha256": engine_identity()["sha256"],
            "environment_sha256": canonical_hash(environment),
            "environment_observed": environment["runtime"]["status"] == "observed"}
