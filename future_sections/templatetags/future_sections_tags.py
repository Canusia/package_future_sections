from django import template

register = template.Library()


@register.simple_tag
def get_form_field(form, field_name):
    """
    Get a form field by name for dynamic rendering in templates.

    Usage:
        {% load future_sections_tags %}
        {% get_form_field form "field_name" as field %}
        {% if field %}
            {{ field|as_crispy_field }}
        {% endif %}
    """
    if field_name in form.fields:
        return form[field_name]
    return None
