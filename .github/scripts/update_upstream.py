#!/usr/bin/env python3
"""Update PyCharm and its separately packaged plugins from stable releases."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://api.github.com/repos/JetBrains/intellij-community/releases/latest"
PLUGIN_API_URL = "https://plugins.jetbrains.com/api/search/compatibleUpdates"
PLUGIN_BASE = "https://plugins.jetbrains.com/files"
PLUGINS = {
    "repmapper": {
        "xml_id": "uk.co.ben-gibson.remote.repository.mapper",
        "plugin_id": 8183,
        "name": "GitLink",
    },
    "ideavim": {
        "xml_id": "IdeaVIM",
        "plugin_id": 164,
        "name": "IdeaVIM",
    },
}


def request(url: str, data: bytes | None = None):
    headers = {"User-Agent": "pycharm-copr-release-check"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    return urlopen(Request(url, data=data, headers=headers), timeout=240)


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one {label}; found {count}")
    return result


def stable_version(release: dict) -> str:
    tag = release.get("tag_name", "")
    match = re.fullmatch(r"pycharm/(\d+(?:\.\d+)+)", tag)
    if release.get("draft") or release.get("prerelease") or not match:
        raise ValueError(f"Latest GitHub release is not a stable PyCharm release: {tag}")
    return match.group(1)


def asset_map(release: dict) -> dict[str, dict]:
    return {asset.get("name"): asset for asset in release.get("assets", [])}


def asset_sha256(asset: dict) -> str:
    digest = asset.get("digest", "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return digest.removeprefix("sha256:")
    sha = hashlib.sha256()
    with request(asset["browser_download_url"]) as response:
        while chunk := response.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def read_product_metadata(asset: dict) -> tuple[dict, str]:
    product_info = None
    jbr_version = None
    with request(asset["browser_download_url"]) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                if member.name.endswith("/product-info.json"):
                    stream = archive.extractfile(member)
                    if stream is not None:
                        product_info = json.load(stream)
                elif member.name.endswith("/jbr/release"):
                    stream = archive.extractfile(member)
                    if stream is not None:
                        text = stream.read().decode("utf-8")
                        match = re.search(r'^IMPLEMENTOR_VERSION="([^"]+)"$', text, re.MULTILINE)
                        if match:
                            jbr_version = match.group(1)
                if product_info and jbr_version:
                    break
    if not product_info or not jbr_version:
        raise ValueError("Could not read PyCharm product-info.json and bundled JBR release metadata")
    return product_info, jbr_version


def compatible_plugins(build: str) -> dict[str, dict]:
    payload = json.dumps({"build": build, "pluginXMLIds": [p["xml_id"] for p in PLUGINS.values()]}).encode()
    with request(PLUGIN_API_URL, payload) as response:
        results = json.load(response)
    by_xml_id = {item.get("pluginXmlId"): item for item in results}
    selected = {}
    for key, plugin in PLUGINS.items():
        item = by_xml_id.get(plugin["xml_id"])
        if not item or item.get("pluginId") != plugin["plugin_id"]:
            raise ValueError(f"No compatible stable {plugin['name']} release for PyCharm build {build}")
        selected[key] = item
    return selected


def main() -> None:
    with request(API_URL) as response:
        release = json.load(response)
    version = stable_version(release)

    core_spec_path = ROOT / "pycharm-community.spec"
    plugin_spec_path = ROOT / "pycharm-community-plugins.spec"
    makefile_path = ROOT / ".copr/Makefile"
    core_spec = core_spec_path.read_text()
    plugin_spec = plugin_spec_path.read_text()
    makefile = makefile_path.read_text()

    core_match = re.search(r"^Version:\s+(\S+)$", core_spec, re.MULTILINE)
    plugin_match = re.search(r"^Version:\s+(\S+)$", plugin_spec, re.MULTILINE)
    if not core_match or not plugin_match:
        raise ValueError("Could not read current PyCharm package versions")
    current = core_match.group(1)
    if plugin_match.group(1) != current:
        raise ValueError("PyCharm and plugin package versions differ; refusing to update")
    current_key = tuple(int(part) for part in current.split("."))
    new_key = tuple(int(part) for part in version.split("."))
    if new_key <= current_key:
        print("updated=false")
        print(f"version={current}")
        print(f"release_url={release.get('html_url', '')}")
        return

    assets = asset_map(release)
    x64_name = f"pycharm-{version}.tar.gz"
    arm_name = f"pycharm-{version}-aarch64.tar.gz"
    if x64_name not in assets or arm_name not in assets:
        raise ValueError("PyCharm release is missing an expected x86_64 or aarch64 source archive")

    product_info, jbr_version = read_product_metadata(assets[x64_name])
    if product_info.get("version") != version or product_info.get("productCode") != "PC":
        raise ValueError("PyCharm source archive metadata does not match the release")
    build = product_info.get("buildNumber")
    if not build:
        raise ValueError("PyCharm product-info.json has no buildNumber")
    plugin_build = f"{product_info['productCode']}-{build}"
    plugins = compatible_plugins(plugin_build)

    core_hashes = {"SOURCE0": asset_sha256(assets[x64_name]), "SOURCE1": asset_sha256(assets[arm_name])}
    plugin_hashes = {}
    for key, plugin in PLUGINS.items():
        item = plugins[key]
        filename = f"{plugin['name']}-{item['version']}.zip"
        url = f"{PLUGIN_BASE}/{plugin['plugin_id']}/{item['id']}/{filename}"
        digest = hashlib.sha256()
        with request(url) as response:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
        plugin_hashes[key] = {"version": item["version"], "id": str(item["id"]), "sha256": digest.hexdigest()}

    core_spec = replace_once(core_spec, r"^(Version:\s+)\S+$", rf"\g<1>{version}", "PyCharm Version")
    core_spec = replace_once(core_spec, r"^(Release:\s+)\S+$", r"\g<1>1%{?dist}", "PyCharm Release")
    for source, digest in core_hashes.items():
        pattern = rf"^echo '([0-9a-f]{{64}})  %\{{{source}\}}' \| sha256sum --check$"
        core_spec = replace_once(core_spec, pattern, rf"echo '{digest}  %{{{source}}}' | sha256sum --check", f"{source} checksum")
    core_spec = replace_once(
        core_spec,
        r'''^grep -Fx 'IMPLEMENTOR_VERSION="[^"]+"' (.*)$''',
        rf'''grep -Fx 'IMPLEMENTOR_VERSION="{jbr_version}"' \g<1>''',
        "bundled JBR version check",
    )

    plugin_spec = replace_once(plugin_spec, r"^(Version:\s+)\S+$", rf"\g<1>{version}", "plugin package Version")
    plugin_spec = replace_once(plugin_spec, r"^(Release:\s+)\S+$", r"\g<1>1%{?dist}", "plugin package Release")
    for key, plugin in PLUGINS.items():
        entry = plugin_hashes[key]
        macro = "repmapper" if key == "repmapper" else "ideavim"
        plugin_spec = replace_once(plugin_spec, rf"^(%global {macro}_version )\S+$", rf"\g<1>{entry['version']}", f"{plugin['name']} version")
        plugin_spec = replace_once(plugin_spec, rf"^(%global {macro}_id )\S+$", rf"\g<1>{entry['id']}", f"{plugin['name']} update ID")
        source = "SOURCE0" if key == "repmapper" else "SOURCE1"
        pattern = rf"^echo '([0-9a-f]{{64}})  %\{{{source}\}}' \| sha256sum --check$"
        plugin_spec = replace_once(plugin_spec, pattern, rf"echo '{entry['sha256']}  %{{{source}}}' | sha256sum --check", f"{plugin['name']} checksum")

    makefile = replace_once(makefile, r"^(version := )\S+$", rf"\g<1>{version}", "COPR Makefile version")
    date = datetime.now(timezone.utc).strftime("%a %b %d %Y")
    core_entry = f"* {date} OK <4374115+kappa8219@users.noreply.github.com> - {version}-1\n- Update PyCharm to {version} with bundled JBR {jbr_version}\n\n"
    plugin_entry = f"* {date} OK <4374115+kappa8219@users.noreply.github.com> - {version}-1\n- Update compatible GitLink {plugin_hashes['repmapper']['version']} and IdeaVIM {plugin_hashes['ideavim']['version']} for PyCharm {version}\n\n"
    core_spec = replace_once(core_spec, r"^%changelog[ \t]*\n", "%changelog\n" + core_entry, "PyCharm changelog")
    plugin_spec = replace_once(plugin_spec, r"^%changelog[ \t]*\n", "%changelog\n" + plugin_entry, "plugin changelog")

    core_spec_path.write_text(core_spec)
    plugin_spec_path.write_text(plugin_spec)
    makefile_path.write_text(makefile)
    print("updated=true")
    print(f"version={version}")
    print(f"release_url={release.get('html_url', '')}")
    print(f"jbr_version={jbr_version}")
    print(f"plugins=GitLink-{plugin_hashes['repmapper']['version']},IdeaVIM-{plugin_hashes['ideavim']['version']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Release update failed: {error}", file=sys.stderr)
        sys.exit(1)
