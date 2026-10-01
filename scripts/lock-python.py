"""Refresh hash locks for the deliberately selected environment; run only after dependency review."""
from importlib.metadata import distributions
from pathlib import Path
import json
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1] / "apps" / "engine"
excluded = {"pip", "setuptools", "bestar-work-hours-engine", "pytest", "iniconfig",
            "packaging", "pluggy", "pygments", "httpx", "httpcore", "certifi"}
packages = {d.metadata["Name"].lower().replace("_", "-"): d.version for d in distributions()}
runtime = {name: version for name, version in packages.items() if name not in excluded}
def locked(name, version):
    with urlopen("https://pypi.org/pypi/" + name + "/" + version + "/json", timeout=30) as response:
        payload = json.load(response)
    hashes = sorted({item["digests"]["sha256"] for item in payload["urls"]
                     if item["packagetype"] == "bdist_wheel" and not item["yanked"]})
    if not hashes:
        raise RuntimeError("No unyanked wheels: " + name)
    return name + "==" + version + " " + " ".join("--hash=sha256:" + h for h in hashes)
lines = [locked(name, version) for name, version in sorted(runtime.items())]
(root / "requirements-api.lock").write_text("# Reviewed runtime versions; PyPI wheel hashes for supported platforms.\n" + "\n".join(lines) + "\n", encoding="utf-8")
test_names = ("pytest", "iniconfig", "packaging", "pluggy", "pygments", "httpx", "httpcore", "certifi")
test_lines = [locked(name, packages[name]) for name in test_names]
(root / "requirements-test.lock").write_text("-r requirements-api.lock\n" + "\n".join(test_lines) + "\n", encoding="utf-8")
path = root / "pyproject.toml"
content = path.read_text(encoding="utf-8")
start = content.index("dependencies = [")
end = content.index("]", start) + 1
dependencies = json.dumps([name + "==" + version for name, version in sorted(runtime.items())], indent=2)
content = content[:start] + "dependencies = " + dependencies + content[end:]
content = content.replace('requires-python = ">=3.11"', 'requires-python = ">=3.14,<3.15"')
path.write_text(content, encoding="utf-8")
print("Locked", len(runtime), "runtime packages and", len(test_names), "test packages.")
