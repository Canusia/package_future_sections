import os
from django.apps import AppConfig


class FutureSectionsConfig(AppConfig):
    """Production config - pip installed."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'future_sections'
    verbose_name = 'Future Sections'
    path = os.path.dirname(os.path.abspath(__file__))

    CONFIGURATORS = [
        {
            'app': 'future_sections',
            'name': 'future_sections',
            'title': 'Section Requests',
            'description': '-',
            'categories': ['3']
        },
    ]

    REPORTS = [
        {
            'app': 'future_sections',
            'name': 'future_classes',
            'title': 'Section Requests Export',
            'description': 'Export section requests with dynamic fields from settings',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
        {
            'app': 'future_sections',
            'name': 'pending_future_classes_courses',
            'title': 'Pending Section Requests - Course(s) Export',
            'description': 'Export courses pending section request responses',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
        {
            'app': 'future_sections',
            'name': 'pending_future_classes',
            'title': 'Pending Section Requests - High School Admin Export',
            'description': 'Export high school admins for schools with pending requests',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
    ]

    def ready(self):
        import future_sections.signals  # noqa: F401


class DevFutureSectionsConfig(AppConfig):
    """Development config - submodule."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'future_sections.future_sections'
    verbose_name = 'Dev - Future Sections'

    CONFIGURATORS = [
        {
            'app': 'future_sections.future_sections',
            'name': 'future_sections',
            'title': 'Section Requests',
            'description': '-',
            'categories': ['3']
        },
    ]

    REPORTS = [
        {
            'app': 'future_sections.future_sections',
            'name': 'future_classes',
            'title': 'Section Requests Export',
            'description': 'Export section requests with dynamic fields from settings',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
        {
            'app': 'future_sections.future_sections',
            'name': 'pending_future_classes_courses',
            'title': 'Pending Section Requests - Course(s) Export',
            'description': 'Export courses pending section request responses',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
        {
            'app': 'future_sections.future_sections',
            'name': 'pending_future_classes',
            'title': 'Pending Section Requests - High School Admin Export',
            'description': 'Export high school admins for schools with pending requests',
            'categories': ['Classes'],
            'available_for': ['ce']
        },
    ]

    def ready(self):
        import future_sections.future_sections.signals  # noqa: F401
