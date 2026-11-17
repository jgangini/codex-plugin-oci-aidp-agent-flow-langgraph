"""Inspect the actual entry folder without flattening or importing agent code."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re

from .project import FlowError, canonical_hash, contained, load_project


def inspect_package(root):
    root, config = load_project(root)
    entry = contained(root, config["agent"]["entry"])
    dependencies = contained(root, config["agent"]["dependencies"])
    if not entry.is_file() or not dependencies.is_file():
        raise FlowError("Declared entry and dependencies must exist")
    package = entry.parent
    if not dependencies.is_relative_to(package):
        raise FlowError("Dependency file must be in the packaged entry folder")
    tree = ast.parse(entry.read_text(encoding="utf-8"))
    classes = [item for item in tree.body if isinstance(item, ast.ClassDef)]
    if not any({"setup", "invoke"}.issubset({node.name for node in item.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}) for item in classes):
        raise FlowError("Entry needs an agent class with setup and invoke")
    files = {}
    total_bytes = 0
    skipped = {"__pycache__", ".venv", ".git", ".pytest_cache", ".aidp-local", "tests"}
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        if any(part in skipped for part in relative.parts):
            continue
        if path.is_symlink():
            raise FlowError("Deployment package cannot contain symlinks")
        if not path.is_file():
            continue
        if any(part in {".oci", ".az"} for part in relative.parts) or path.suffix.lower() in {".pem", ".key"}:
            raise FlowError("Deployment package contains a credential file")
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            raise FlowError("Local environment secrets cannot be packaged")
        if path.stat().st_size > 500_000_000 or len(files) >= 500:
            raise FlowError("Package exceeds the documented AIDP file limits")
        total_bytes += path.stat().st_size
        if total_bytes > 5_000_000_000:
            raise FlowError("Package exceeds the documented total upload size")
        checksum = hashlib.sha256()
        previous = b""
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sample = previous + chunk
                if re.search(rb"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----|apify_api_[A-Za-z0-9]{20,}", sample):
                    raise FlowError("Deployment package contains apparent secret material")
                checksum.update(chunk)
                previous = sample[-128:]
        files[relative.as_posix()] = checksum.hexdigest()
    return {"files": files, "package_sha256": canonical_hash(files), "file_count": len(files), "total_bytes": total_bytes,
            "entry": entry.name, "packaging_checked": True, "native_imports_verified": False,
            "native_test_accepted": False}
