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


@register.simple_tag
def dependent_fields(form, parent_field_name):
    """
    Return the bound fields that are conditional on *parent_field_name*.

    Driven by the schema's ``depends_on`` metadata, so a new conditional
    field needs no template change.

    Usage:
        {% dependent_fields form "teacher_changed" as dependents %}
        {% for dep in dependents %}{{ dep|as_crispy_field }}{% endfor %}
    """
    from ..schemas import TeachingSectionFieldSchema

    return [
        form[name]
        for name in TeachingSectionFieldSchema.get_dependents_of(
            parent_field_name)
        if name in form.fields
    ]


@register.simple_tag
def is_dependent_field(field_name):
    """True when *field_name* is rendered under a parent, not in the main list."""
    from ..schemas import TeachingSectionFieldSchema

    return field_name in TeachingSectionFieldSchema.get_dependent_fields()


@register.simple_tag
def get_existing_file_field(form, field_name):
    """Return the hidden companion field holding *field_name*'s stored URL."""
    # NOTE: this companion is only rendered by the main-loop branch of
    # teaching_course.html. A file field that ever declares `depends_on`
    # would be rendered by the dependent-field branch instead, which does
    # not call this tag — so it would render with no companion, and its
    # stored URL would be lost on save (the dependent hide-path also clears
    # its inputs). Unreachable today since assessment_upload (the only file
    # field) has no depends_on.
    companion = f'{field_name}_existing'
    if companion in form.fields:
        return form[companion]
    return None
