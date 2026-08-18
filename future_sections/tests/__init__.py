"""Test package for future_sections.

`PKG` is this package's importable dotted path. It differs by deployment
shape: a tenant that checks the repo out as an in-tree editable submodule
imports it as `future_sections.future_sections`, while a tenant that pip
installs it gets the flat `future_sections`. The test suite ships inside the
wheel, so it runs in both — hardcoding either prefix makes every module using
it fail to import in the other layout.

Prefer a relative import (`from ..forms import X`) where one works; `PKG` is
for the places a string is required, such as `mock.patch` targets.
"""
import importlib.util

PKG = (
    'future_sections.future_sections'
    if importlib.util.find_spec('future_sections.future_sections')
    else 'future_sections'
)
