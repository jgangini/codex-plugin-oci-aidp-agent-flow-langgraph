"""Validate the public distribution and run its existing offline regression suite."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "langchain-skills-codex"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_manifest():
    manifest = load_json(PLUGIN / ".codex-plugin" / "plugin.json")
    with (PLUGIN / "pyproject.toml").open("rb") as stream:
        package = tomllib.load(stream)
    if manifest["version"] != package["project"]["version"]:
        raise ValueError("Manifest and Python versions differ")
    marketplace = load_json(ROOT / ".agents" / "plugins" / "marketplace.json")
    entry = marketplace["plugins"][0]
    if entry["name"] != manifest["name"] or (ROOT / entry["source"]["path"]).resolve() != PLUGIN:
        raise ValueError("Marketplace does not resolve to this plugin")
    for skill in manifest["skills"]:
        if not (PLUGIN / skill / "SKILL.md").is_file():
            raise ValueError(f"Missing skill: {skill}")
    for asset in ("composerIcon", "logo"):
        if not (PLUGIN / manifest["interface"][asset]).is_file():
            raise ValueError(f"Missing asset: {asset}")
    return manifest["version"]


def check_upstream():
    for item in load_json(PLUGIN / "upstream-files.json"):
        if hashlib.sha256((PLUGIN / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Upstream file changed: {item['path']}")


def check_examples():
    sys.path.insert(0, str(PLUGIN / "scripts"))
    from aidp_agent_flow.cases import validate_case

    for path in (ROOT / "examples").glob("corpus-*.json"):
        for case in load_json(path):
            validate_case(case)


def check_documentation():
    pages = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    for page in pages:
        for target in re.findall(r"\]\(([^\s)]+)\)", page.read_text(encoding="utf-8")):
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            local = unquote(target.split("#", 1)[0])
            if not (page.parent / local).exists():
                raise ValueError(f"Broken link in {page.relative_to(ROOT)}: {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-only", action="store_true", help="Skip the engine regression suite")
    args = parser.parse_args()
    version = check_manifest()
    check_upstream()
    check_examples()
    check_documentation()
    print(f"Distribution {version}: marketplace, skills, assets, upstream, corpus and local links OK", flush=True)
    if not args.package_only:
        (ROOT / "plugins" / "validation-work").mkdir(exist_ok=True)
        env = dict(os.environ, PYTHONPATH=str(PLUGIN / "scripts"))
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-q"],
            cwd=PLUGIN, env=env, check=True,
        )


if __name__ == "__main__":
    main()
