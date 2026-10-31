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


def record_context(academic_year):
    """Context manager serving the record's campus, so a campus setting is
    read for the college the record belongs to (multi-campus only; a no-op
    otherwise or when the year has no campus)."""
    import contextlib
    campus = record_campus(academic_year)
    if campus is None or not is_multi_campus():
        return contextlib.nullcontext()
    from cis.campus_context import campus_context
    return campus_context(campus)


def exclude_other_campuses(queryset, path):
    """Drop rows whose academic year belongs to another campus.

    ``path`` is the lookup to the year's campus (``academic_year__campus``).
    Years with no campus stay visible, matching ``other_campus()``. A no-op
    unless multi-campus.
    """
    if not is_multi_campus():
        return queryset
    from django.db.models import Q
    return queryset.filter(
        Q(**{path: serving_campus()}) | Q(**{f'{path}__isnull': True}))


def command_base():
    """``CampusCommand`` when cis has it (``--campus``, runs in a campus
    context), else Django's ``BaseCommand``."""
    if importlib.util.find_spec('cis.management.campus_command'):
        from cis.management.campus_command import CampusCommand
        return CampusCommand
    from django.core.management.base import BaseCommand
    return BaseCommand


def scope_highschools(queryset):
    """Narrow a HighSchool queryset to the schools linked to the serving
    campus (cis ``highschool_scope.scope_highschools``).

    A no-op unless multi-campus, and on a cis without ``highschool_scope``,
    so single-campus tenants see every school exactly as before.
    """
    if not is_multi_campus() or not importlib.util.find_spec('cis.highschool_scope'):
        return queryset
    from cis.highschool_scope import scope_highschools as _scope
    return _scope(queryset, campus=serving_campus())
