"""
Instructor-specific views for future sections.

This module provides a thin wrapper that delegates to FutureSectionsPageView.
Kept for backward compatibility with existing URL configurations.
"""

from .pages import FutureSectionsPageView


def future_sections_view(request):
    """
    Main future sections page for instructors.

    This is a wrapper around FutureSectionsPageView for backward compatibility.
    The shared view handles role detection automatically.
    """
    view = FutureSectionsPageView.as_view()
    return view(request)
