"""Page headings and page text for the portal pages future_sections adds (#12).

A heading follows the menu item's label when staff renamed it (Settings →
Menu Layout); page text is the ``<menu item>_blurb`` staff saved in the role's
portal settings. cis v0.2.10a has the shared copy
(``cis.portal_text.page_heading`` / ``page_blurb``); older cis get the
fallbacks below. cis is optional for this package, so nothing here may fail.
"""
import importlib
import logging

log = logging.getLogger(__name__)

#: Labels an item has had without staff renaming it: the registry labels
#: (menu.py) and the settings-driven menu's (cis before the registry).
STOCK_LABELS = {'Future Sections', 'Section Requests', 'Course Projections'}

#: role → (portal name for cis.portal_text.portal_text, cis setting module/class)
_PORTALS = {
    'highschool_admin': (None, 'highschool_admin_portal'),
    'instructor': ('instructor_portal', 'instructor_portal'),
    'faculty': ('faculty_portal', 'faculty_portal'),
}

_PLACEHOLDER_PREFIX = 'Change this in Settings'


def _cis_helper(name):
    try:
        return getattr(importlib.import_module('cis.portal_text'), name, None)
    except Exception:
        return None


def _find_item(items, name):
    stack = list(items or ())
    while stack:
        item = stack.pop(0)
        if not isinstance(item, dict):
            continue
        if item.get('name') == name:
            return item
        stack.extend(item.get('sub_menu') or ())
    return None


def page_heading(role, name, default):
    """The renamed label of ``role``'s menu item ``name``, else ``default``."""
    cis_heading = _cis_helper('page_heading')
    if cis_heading is not None:
        # A menu converted from the settings-driven layout keeps its old
        # label as an override ("Course Projections"); that is not a rename.
        heading = cis_heading(role, name, default)
        return default if heading in STOCK_LABELS else heading
    try:
        from cis.menu import get_role_menu
    except ImportError:   # cis without get_role_menu (< v0.0.34) or no cis
        return default
    try:
        item = _find_item(get_role_menu(role, visible_only=False), name)
    except Exception:
        log.exception('future_sections: could not read the %s menu', role)
        return default
    label = item.get('label') if item else None
    if not isinstance(label, str) or not label.strip() or label.strip() in STOCK_LABELS:
        return default
    return label.strip()


def _stored_text(role):
    owner, setting = _PORTALS[role]
    portal_text = _cis_helper('portal_text')
    if owner and portal_text is not None:
        return portal_text(owner)
    module = importlib.import_module(f'cis.settings.{setting}')
    return getattr(module, setting).from_db()


def page_blurb(role, name, legacy_keys=(), default=''):
    """The page text staff saved for ``role``'s menu item ``name``, else ``default``.

    Tries ``<name>_blurb`` then ``legacy_keys``; blank text and untouched
    placeholders fall through.
    """
    if role not in _PORTALS:
        return default
    cis_blurb = _cis_helper('page_blurb')
    if cis_blurb is not None:
        return cis_blurb(role, name, legacy_keys=legacy_keys, default=default)
    try:
        stored = _stored_text(role)
    except Exception:
        log.exception('future_sections: could not read the %s portal text', role)
        return default
    if not isinstance(stored, dict):
        return default
    for key in (f'{name}_blurb',) + tuple(legacy_keys):
        value = stored.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text != 'Change me' and not text.startswith(_PLACEHOLDER_PREFIX):
            return value
    return default
