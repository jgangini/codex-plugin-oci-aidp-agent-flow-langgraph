"""Project preparation and protected local artifact handling."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib


class FlowError(Exception):
    """An actionable message safe to show without a provider exception body."""


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise FlowError("Path must stay inside the selected project")
    return path


def private_json(path, value, *, overwrite=False):
    path = Path(path)
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)():
            raise FlowError("Protected artifacts cannot use linked ancestors")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise FlowError("Protected artifacts cannot use a symlink")
    if not overwrite:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        return
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_project(root):
    root = Path(root).resolve()
    path = root / "aidp-agent.toml"
    if not path.is_file():
        raise FlowError("Missing aidp-agent.toml; initialize or adopt this project first")
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    agent = config.get("agent", {})
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", agent.get("factory", "")):
        raise FlowError("Agent factory must be module:function")
    for key in ("python_path", "entry", "dependencies"):
        if key not in agent:
            raise FlowError("Agent configuration is incomplete")
        contained(root, agent[key])
    return root, config


def python_path(root):
    path = Path(root) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not path.is_file():
        raise FlowError("Project environment is missing; run project sync")
    return path


def sync_project(root):
    root, _ = load_project(root)
    executable = shutil.which("uv")
    if not executable:
        raise FlowError("uv is unavailable; install it through the approved local toolchain")
    command = [executable, "sync"]
    if (root / "uv.lock").is_file():
        command.append("--locked")
    result = subprocess.run(command, cwd=root, capture_output=True, timeout=180)
    if result.returncode:
        raise FlowError("uv sync failed; inspect dependency availability and the project's lockfile")
    return {"environment_ready": True, "lockfile": (root / "uv.lock").is_file()}


def initialize(root, name, *, sync=True, langgraph_version=None, runtime_profile=None):
    root = Path(root).resolve()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,79}", name):
        raise FlowError("Use a short project name containing letters, digits, spaces, hyphens or underscores")
    from .compatibility import select_profile
    selected = select_profile(runtime_profile, langgraph_version, new_project=True)
    langgraph_version = selected["langgraph"]
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise FlowError("Initialization requires a new or empty directory; existing files were preserved")
    root.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("templates")
    for source in template.rglob("*.tmpl"):
        relative = source.relative_to(template).as_posix().removesuffix(".tmpl")
        target = contained(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8").replace("@@NAME_JSON@@", json.dumps(name))
        text = text.replace("@@LANGGRAPH_VERSION@@", langgraph_version)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text)
    with (root / "aidp-agent.toml").open("a", encoding="utf-8") as stream:
        stream.write("\n[runtime]\nprofile = " + json.dumps(selected["id"]) + "\nlanggraph_version = " + json.dumps(langgraph_version) + "\n")
    extra = {key: value for key, value in selected["packages"].items() if key != "langgraph"}
    if extra:
        constraints = [key + "==" + value for key, value in extra.items()]
        with (root / "pyproject.toml").open("a", encoding="utf-8") as stream:
            stream.write("\nconstraint-dependencies = " + json.dumps(constraints) + "\n")
        with (root / "agent/requirements.txt").open("a", encoding="utf-8") as stream:
            stream.write("\n" + "\n".join(constraints) + "\n")
    boundary = Path(__file__).with_name("model_boundary.py")
    shutil.copyfile(boundary, root / "agent/core/model_boundary.py")
    from .compatibility import documented_status
    result = {"project_created": True, "native_binding_ready": False,
              "model_test_performed": False, "langgraph_version": langgraph_version,
              "runtime_profile_status": documented_status(langgraph_version), "selected_profile": selected["id"], "oracle_certified": False}
    if sync:
        result.update(sync_project(root))
    return result


def adopt(root, factory, entry, dependencies, python_dir="."):
    root = Path(root).resolve()
    if not root.is_dir():
        raise FlowError("Adoption requires an existing project directory")
    target = root / "aidp-agent.toml"
    if target.exists():
        raise FlowError("Existing project configuration was preserved")
    for relative in (entry, dependencies, python_dir):
        if not contained(root, relative).exists():
            raise FlowError("Declared project path does not exist")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", factory):
        raise FlowError("Factory must be module:function")
    fields = {"factory": factory, "python_path": python_dir, "entry": entry, "dependencies": dependencies}
    text = "[agent]\n" + "".join(key + " = " + json.dumps(value) + "\n" for key, value in fields.items())
    text += '\n[oci]\nconfig_file = ".oci/config"\nprofile = "DEFAULT"\n'
    text += '\n[model]\nregion = ""\nmodel_id = ""\ncompartment_id = ""\nmax_tokens = 512\nmax_calls = 3\n'
    with target.open("x", encoding="utf-8") as stream:
        stream.write(text)
    ignore = root / ".gitignore"
    if ignore.is_symlink():
        raise FlowError("Local ignore file cannot use a symlink; configuration was created, code was preserved")
    current = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    entries = [entry for entry in (".aidp-local/", ".oci/", ".venv/") if entry not in current.splitlines()]
    if entries:
        with ignore.open("a", encoding="utf-8") as stream:
            stream.write(("\n" if current and not current.endswith("\n") else "") + "\n".join(entries) + "\n")
    return {"project_adopted": True, "code_modified": False, "ignore_rules_added": entries,
            "environment_modified": False}


def doctor(root):
    from .compatibility import assess_runtime, observe_local, observe_capabilities
    root, config = load_project(root)
    environment = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    observation = observe_local(environment)
    versions = {name: value for name, value in observation["packages"].items() if value is not None}
    path = Path(config.get("oci", {}).get("config_file", ".oci/config")).expanduser()
    if not path.is_absolute():
        path = root / path
    capabilities = observe_capabilities(environment)
    return {"runtime_capabilities": capabilities, "local_ready": all(name in versions for name in ("langgraph", "oci")),
            "versions": versions, "runtime_compatibility": assess_runtime(observation, runtime_profile=config.get("runtime", {}).get("profile"), langgraph_version=config.get("runtime", {}).get("langgraph_version")),
            "uv_available": bool(shutil.which("uv")),
            "oci_config_present": path.is_file(), "auth_checked": False, "native_test_accepted": False,
            "model_selected": bool(config.get("model", {}).get("model_id"))}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def redact(value):
    if isinstance(value, dict):
        sensitive = {"private_key", "privateKey", "secretValue", "token", "password", "authorization", "cookie", "pass_phrase", "key_content"}
        return {key: "[REDACTED]" if key in sensitive else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----.*?-----END (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----",
                       "[REDACTED PRIVATE KEY]", value, flags=re.S)
        return re.sub(r"apify_api_[A-Za-z0-9]{20,}", "[REDACTED TOKEN]", value)
    return value
