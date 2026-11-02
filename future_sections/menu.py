"""Future sections sidebar items (cis.menu_registry).

ce `future_sections` is the 20 of `classes`; the faculty, instructor and
highschool_admin items were added by tenants after Home / the first items.
On a cis without the registry nothing registers.
"""
try:
    from cis.menu_registry import menu
except ImportError:   # cis without the registry: the menu migrations still apply
    menu = None

if menu is not None:
    menu.register('ce', 'future_sections', 'Future Sections',
                  url='future_sections_ce:future_sections', parent='classes',
                  order=20)
    menu.register('faculty', 'section_requests', 'Section Requests',
                  url='future_sections_faculty:section_request_list',
                  icon='fas fa-fw fa-clipboard-list', order=25)
    menu.register('instructor', 'future_sections', 'Section Requests',
                  url='future_sections_instructor:section_requests',
                  icon='fas fa-fw fa-calendar-alt', order=15)
    menu.register('highschool_admin', 'future_sections', 'Future Sections',
                  url='future_sections_highschool_admin:section_requests',
                  icon='fas fa-fw fa-file-alt', order=17)
