"""Campus helpers for a multi-campus cis (FS-01, #6), optional by design.

A tenant with an in-repo cis has no ``cis.campus_context`` (or an older one
without ``campus_url``); every helper here then behaves exactly as the
package did before campus scoping. A single-campus deployment on a newer cis
also keeps its old behaviour: links still come from ``settings.SITE_URL`` and
nothing is filtered by campus. Only ``MULTI_CAMPUS`` changes anything.
"""
import importlib.util

from django.conf import settings


def _campus_context():
    """The ``cis.campus_context`` module when it has what we need, else None."""
    if not importlib.util.find_spec('cis.campus_context'):
        return None
    import cis.campus_context as cc
    if not all(hasattr(cc, name) for name in (
            'campus_url', 'current_campus', 'is_multi_campus')):
        return None
    return cc


def is_multi_campus():
    cc = _campus_context()
    return bool(cc and cc.is_multi_campus())


def serving_campus():
    """The campus the running code serves; None when not multi-campus.

    Raises cis's ``NoCampusContext`` in multi-campus mode with no campus
    set -- callers fail closed rather than guess a college.
    """
    if not is_multi_campus():
        return None
    return _campus_context().current_campus()


def record_campus(academic_year):
    """The campus a record belongs to, via its academic year (None if unset)."""
    return getattr(academic_year, 'campus', None) if academic_year else None


def site_link(path, academic_year=None):
    """Absolute link for an email.

    Multi-campus: the host of the record's campus (``academic_year.campus``),
    else of the serving campus, through cis ``campus_url`` -- which raises
    rather than borrow another college's host when the campus has no Site.
    Otherwise ``SITE_URL + path``, unchanged.
    """
    if not is_multi_campus():
        return f"{getattr(settings, 'SITE_URL', '')}{path}"
    campus = record_campus(academic_year) or serving_campus()
    return _campus_context().campus_url(campus, path)


def other_campus(academic_year):
    """True in multi-campus mode when the year belongs to another campus."""
    if not is_multi_campus():
        return False
    campus = record_campus(academic_year)
    return campus is not None and campus != serving_campus()


def command_base():
    """``CampusCommand`` when cis has it (``--campus``, runs in a campus
    context), else Django's ``BaseCommand``."""
    if importlib.util.find_spec('cis.management.campus_command'):
        from cis.management.campus_command import CampusCommand
        return CampusCommand
    from django.core.management.base import BaseCommand
    return BaseCommand
