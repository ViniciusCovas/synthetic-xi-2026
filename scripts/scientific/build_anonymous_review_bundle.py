#!/usr/bin/env python3
"""Build a double-blind reviewer package and fail closed on identity leakage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".csv", ".yml", ".yaml", ".toml"}
DENY_PATTERNS = {
    "author_first_name": re.compile(r"\bvinicius\b", re.IGNORECASE),
    "author_last_name": re.compile(r"\bcovas\b", re.IGNORECASE),
    "github_owner": re.compile(r"ViniciusCovas", re.IGNORECASE),
    "institution": re.compile(r"an[aá]huac", re.IGNORECASE),
    "personal_domain": re.compile(r"viniciuscovas\.com", re.IGNORECASE),
    "orcid": re.compile(r"0000-0001-9948-2940"),
}
COPY_PATHS = (
    "requirements.txt",
    "METHODS_OFFICIAL_V1.md",
    "PROTOCOL_AMENDMENT_OFFICIAL_V1.md",
    "SCIENTIFIC_RELEASE_OFFICIAL_V1.md",
    "config",
    "simulator",
    "scripts",
    "tests",
    "protocol",
    "data/model_readiness",
    "data/experiments/official_v1/official",
    "data/experiments/official_v1/robustness",
    "data/experiments/official_v1_precision_replication_50000/official",
    "paper/figures",
    "paper/FIGURE_CAPTIONS.md",
    "paper/PROVENANCE_MATRIX.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize_text(text: str) -> str:
    text = re.sub(
        r"https?://github\.com/ViniciusCovas/synthetic-xi-2026(?:/[^\s)\]]*)?",
        "[permanent repository withheld during double-blind review]",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("ViniciusCovas/synthetic-xi-2026", "[repository withheld during review]")
    text = re.sub(
        r"## Data and Code Availability\n.*?(?=\n## Ethics Statement)",
        "## Data and Code Availability\n\nAn anonymized reproducibility package containing code, frozen inputs, preregistration materials, validation evidence, manifests, outputs, figures, and provenance documentation accompanies this submission. The permanent public repository and archival DOI are withheld from the blinded manuscript and will be disclosed to the editor confidentially and added to the accepted version.",
        text,
        flags=re.DOTALL,
    )
    return text


def copy_selected(root: Path, output: Path) -> None:
    for relative in COPY_PATHS:
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(source)
        destination = output / relative
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
            )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def write_manuscript_files(root: Path, output: Path) -> None:
    manuscript = sanitize_text((root / "paper/MANUSCRIPT_JASSS_V1.md").read_text(encoding="utf-8"))
    supplement = sanitize_text((root / "paper/SUPPLEMENT_ODD_OFFICIAL_V1.md").read_text(encoding="utf-8"))
    (output / "MANUSCRIPT_ANONYMIZED.md").write_text(manuscript, encoding="utf-8")
    (output / "SUPPLEMENT_ODD_ANONYMIZED.md").write_text(supplement, encoding="utf-8")
    reviewer_readme = """# Double-blind reproducibility package

This package accompanies a manuscript under double-blind review. It contains the anonymized manuscript, ODD supplement, frozen code and inputs, preregistration and authorization evidence, confirmatory and precision-replication outputs, robustness analyses, figures, and a provenance matrix.

The package intentionally excludes author names, affiliations, the public repository URL, cover letter, title page, Git history, GitHub Actions metadata, and any archival record that directly identifies the authors.

## Reproduction

Create a Python 3.12 environment, install `requirements.txt`, then run:

```bash
PYTHONPATH=. pytest -q tests/test_official_experiment.py tests/test_official_orientation.py
PYTHONPATH=. python scripts/scientific/validate_official_release.py --mode structural --status-output /tmp/structural.json
PYTHONPATH=. python scripts/run_official_experiment_v1_1.py --mode official --simulations 10000 --seed 2026073001 --output /tmp/official-v1-reproduction
```

The official confirmatory result is the 10,000-run experiment. The 50,000-run experiment is an independent precision replication.
"""
    (output / "README_REVIEWERS.md").write_text(reviewer_readme, encoding="utf-8")


def sanitize_and_scan(output: Path) -> list[dict[str, str]]:
    leaks: list[dict[str, str]] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        sanitized = sanitize_text(text)
        if sanitized != text:
            path.write_text(sanitized, encoding="utf-8")
        for name, pattern in DENY_PATTERNS.items():
            match = pattern.search(sanitized)
            if match:
                leaks.append({"file": str(path.relative_to(output)), "pattern": name, "match": match.group(0)})
    return leaks


def build_archive(output: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(str(path.relative_to(output)))
                info.date_time = (2026, 7, 31, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                handle.writestr(info, path.read_bytes())


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copy_selected(root, output)
    write_manuscript_files(root, output)
    leaks = sanitize_and_scan(output)
    if leaks:
        raise RuntimeError(f"Identity leakage detected: {json.dumps(leaks, ensure_ascii=False)}")

    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files.append({
                "path": str(path.relative_to(output)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    package_manifest = {
        "status": "anonymous_double_blind_package_built",
        "identity_scan_passed": True,
        "excluded_identity_surfaces": [
            "Git history",
            "repository owner and URL",
            "title page",
            "cover letter",
            "author names and affiliations",
            "workflow metadata",
        ],
        "files": files,
    }
    (output / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    build_archive(output, args.archive)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    report = {
        **package_manifest,
        "archive": args.archive.name,
        "archive_bytes": args.archive.stat().st_size,
        "archive_sha256": sha256(args.archive),
        "file_count": len(files),
    }
    args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "file_count": len(files), "archive_sha256": report["archive_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
