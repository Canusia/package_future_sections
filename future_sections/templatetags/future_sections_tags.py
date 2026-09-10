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


@register.simple_tag
def add_teacher_only_fields(form):
    """Bound fields that are only ever *asked* on the Add Teacher form.

    They are excluded from ``teaching_form_config['fields']`` by design, so
    the teaching template's main render loop never emits them. Rendering
    them as hidden inputs is what carries their stored value back on a
    teaching save: without it nothing posts them, and
    ``build_section_info_from_formset`` stores '' over whatever the Add
    Teacher form collected — an uploaded syllabus silently disappears the
    first time anyone edits the teaching form.

    The hidden value is client-editable, but for file fields
    ``build_section_info_from_formset`` accepts a posted URL only when it
    already appears on the record, so a spoofed one resolves to ''.

    Usage:
        {% add_teacher_only_fields teaching_form as carried %}
        {% for field in carried %}{{ field }}{% endfor %}
    """
    from ..forms import TeacherCourseSectionForm

    return [
        form[name]
        for name in TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS
        if name in form.fields
    ]
