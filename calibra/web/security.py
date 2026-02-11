"""Path validation for web routes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request

SEGMENT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def validate_segment(value: str, name: str = "segment") -> str:
    if not SEGMENT_PATTERN.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {name}: {value!r}")
    return value


def validate_path(results_dir: Path, *segments: str) -> Path:
    resolved_root = results_dir.resolve()
    target = results_dir.joinpath(*segments).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return target


def get_results_dir(request: Request) -> Path:
    return request.app.state.results_dir


ResultsDir = Annotated[Path, Depends(get_results_dir)]
