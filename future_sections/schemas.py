"""
Pydantic schema for configurable teaching section form fields.

Single source of truth for:
- Available configurable field names
- Default labels, help texts, and widget types
- Django form field generation
- Export label resolution
- Section display formatting
- Settings help text generation
"""
import datetime
import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from django import forms
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe


def _display_date(value: str) -> str:
    """Render an ISO date string as ``m/d/Y``; pass anything else through."""
    try:
        return datetime.date.fromisoformat(str(value)).strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return str(value)


class TeachingSectionFieldSchema(BaseModel):
    """Defines all configurable fields for the TeacherCourseSectionForm.

    Each field carries metadata in json_schema_extra:
    - default_label: label shown in the form
    - default_help_text: optional help text
    - widget_type: text | textarea | checkbox | select | file | date | email
    - field_type: string | boolean | integer | date
    """

    estimated_enrollment: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Estimated Enrollment",
            "widget_type": "text",
            "field_type": "string",
        },
    )
    class_period: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Class Period",
            "default_help_text": "e.g., 1st period, 2nd hour",
            "widget_type": "text",
            "field_type": "string",
        },
    )
    location: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Location",
            "widget_type": "select",
            "field_type": "string",
        },
    )
    instruction_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Instruction Mode",
            "widget_type": "select",
            "field_type": "string",
        },
    )
    course_type: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Type of course",
            "widget_type": "select",
            "field_type": "string",
        },
    )
    course_request_type: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "This is a:",
            "widget_type": "select",
            "field_type": "string",
        },
    )
    section_number: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Section Number",
            "default_help_text": (
                "Pre-filled from last year's section when available"),
            "widget_type": "text",
            "field_type": "string",
        },
    )
    highschool_course_name: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "High School Class Title",
            "widget_type": "text",
            "field_type": "string",
        },
    )
    number_of_sections: Optional[int] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Number of Section",
            "widget_type": "text",
            "field_type": "integer",
        },
    )
    full_year: Optional[bool] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Full Year",
            "widget_type": "checkbox",
            "field_type": "boolean",
        },
    )
    trimester: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Trimester",
            "widget_type": "text",
            "field_type": "string",
        },
    )
    fall_only: Optional[bool] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Fall Only",
            "widget_type": "checkbox",
            "field_type": "boolean",
        },
    )
    spring_only: Optional[bool] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Spring Only",
            "widget_type": "checkbox",
            "field_type": "boolean",
        },
    )
    notes: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Notes",
            "widget_type": "textarea",
            "field_type": "string",
        },
    )
    teacher_changed: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Did the teacher change?",
            "widget_type": "select",
            "field_type": "string",
            "choices": [("yes", "Yes"), ("no", "No")],
        },
    )
    new_teacher_name: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "New Teacher Name",
            "default_help_text": "Enter the name of the new teacher",
            "widget_type": "text",
            "field_type": "string",
            "depends_on": "teacher_changed",
        },
    )
    highschool_title_changed: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Did the high school title change?",
            "widget_type": "select",
            "field_type": "string",
            "choices": [("yes", "Yes"), ("no", "No")],
        },
    )
    new_highschool_title: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "New High School Title",
            "default_help_text": "Enter the new high school course title",
            "widget_type": "text",
            "field_type": "string",
            "depends_on": "highschool_title_changed",
        },
    )
    start_date: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Start Date",
            "widget_type": "date",
            "field_type": "date",
        },
    )
    end_date: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "End Date",
            "widget_type": "date",
            "field_type": "date",
        },
    )
    assessment_upload: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Assessment Upload",
            "widget_type": "file",
            "field_type": "string",
        },
    )
    new_teacher_email: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "New Teacher Email",
            "default_help_text": "Enter the email address of the new teacher",
            "widget_type": "email",
            "field_type": "string",
            "depends_on": "teacher_changed",
        },
    )

    # ------------------------------------------------------------------
    # Utility class methods
    # ------------------------------------------------------------------

    @classmethod
    def get_available_field_names(cls) -> list[str]:
        """Return ordered list of all configurable field names."""
        return list(cls.model_fields.keys())

    @classmethod
    def get_field_meta(cls, name: str) -> dict:
        """Return the json_schema_extra metadata dict for *name*."""
        info = cls.model_fields.get(name)
        if info is None:
            return {}
        return info.json_schema_extra or {}

    @classmethod
    def get_dependent_fields(cls) -> dict[str, str]:
        """Return ``{field_name: parent_field_name}`` for conditional fields.

        A field is conditional when its metadata declares ``depends_on``; the
        field is only shown once the named parent field is answered "yes".
        """
        deps: dict[str, str] = {}
        for name in cls.get_available_field_names():
            parent = cls.get_field_meta(name).get("depends_on")
            if parent:
                deps[name] = parent
        return deps

    @classmethod
    def get_dependents_of(cls, parent: str) -> list[str]:
        """Return field names depending on *parent*, in declaration order."""
        return [
            name
            for name, dep_parent in cls.get_dependent_fields().items()
            if dep_parent == parent
        ]

    @classmethod
    def get_file_field_names(cls) -> list[str]:
        """Return field names rendered as file uploads."""
        return [
            name
            for name in cls.get_available_field_names()
            if cls.get_field_meta(name).get("widget_type") == "file"
        ]

    @classmethod
    def get_date_field_names(cls) -> list[str]:
        """Return field names rendered as date pickers."""
        return [
            name
            for name in cls.get_available_field_names()
            if cls.get_field_meta(name).get("widget_type") == "date"
        ]

    @classmethod
    def make_django_form_field(
        cls,
        name: str,
        *,
        visible: bool = False,
        required: bool = False,
        label_override: str | None = None,
        help_text_override: str | None = None,
        choices: list[tuple[str, str]] | None = None,
    ) -> forms.Field:
        """Build a Django form field from schema metadata.

        When *visible* is False the field is rendered as a HiddenInput.
        *choices* is used for ``select`` widget_type fields.
        """
        meta = cls.get_field_meta(name)
        label = label_override or meta.get("default_label", name)
        help_text = help_text_override or meta.get("default_help_text", "")
        field_type = meta.get("field_type", "string")
        widget_type = meta.get("widget_type", "text")

        if not visible:
            # Hidden field — always use HiddenInput
            if field_type == "boolean":
                return forms.BooleanField(
                    required=False,
                    label=label,
                    help_text=help_text,
                    widget=forms.HiddenInput(),
                )
            if field_type == "integer":
                return forms.IntegerField(
                    required=False,
                    label=label,
                    help_text=help_text,
                    widget=forms.HiddenInput(),
                )
            return forms.CharField(
                required=False,
                label=label,
                help_text=help_text,
                widget=forms.HiddenInput(),
            )

        # Visible field — pick widget from schema metadata
        if field_type == "boolean":
            return forms.BooleanField(
                required=required,
                label=label,
                help_text=help_text,
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
            )

        if field_type == "integer":
            widget = forms.TextInput(attrs={"class": "form-control"})
            return forms.IntegerField(
                required=required,
                label=label,
                help_text=help_text,
                widget=widget,
            )

        if widget_type == "file":
            return forms.FileField(
                required=required,
                label=label,
                help_text=help_text,
                widget=forms.ClearableFileInput(
                    attrs={"class": "form-control-file"}),
            )

        if widget_type == "date":
            return forms.DateField(
                required=required,
                label=label,
                help_text=help_text,
                input_formats=["%Y-%m-%d", "%m/%d/%Y"],
                widget=forms.DateInput(
                    attrs={"type": "date", "class": "form-control"},
                    format="%Y-%m-%d",
                ),
            )

        if widget_type == "email":
            return forms.EmailField(
                required=required,
                label=label,
                help_text=help_text,
                widget=forms.EmailInput(attrs={"class": "form-control"}),
            )

        # Select fields — use ChoiceField with provided choices
        if widget_type == "select":
            schema_choices = meta.get("choices")
            select_choices = [("", "---------")] + (choices or schema_choices or [])
            return forms.ChoiceField(
                required=required,
                label=label,
                help_text=help_text,
                choices=select_choices,
                widget=forms.Select(attrs={"class": "form-control"}),
            )

        # String fields — widget depends on widget_type
        if widget_type == "textarea":
            widget = forms.Textarea(attrs={"class": "form-control", "rows": 3})
        else:
            widget = forms.TextInput(attrs={"class": "form-control"})

        return forms.CharField(
            required=required,
            label=label,
            help_text=help_text,
            widget=widget,
        )

    @classmethod
    def get_export_labels(
        cls,
        active_fields: list[str] | None = None,
        label_overrides: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return ``{field_name: label}`` suitable for CSV/export headers.

        *label_overrides* (from settings JSON ``labels``) take precedence over
        the schema defaults.
        """
        if active_fields is None:
            active_fields = cls.get_available_field_names()
        label_overrides = label_overrides or {}

        labels: dict[str, str] = {}
        for name in active_fields:
            if name in label_overrides:
                labels[name] = label_overrides[name]
            else:
                meta = cls.get_field_meta(name)
                labels[name] = meta.get("default_label", name)
        return labels

    @classmethod
    def format_section_display(
        cls,
        section: dict,
        template: str,
        show_syllabus: bool = True,
        choice_labels: dict | None = None,
    ) -> str:
        """Render a single section dict through *template*.

        Handles placeholder replacement, syllabus link, and cleanup — identical
        to the logic previously in ``FutureCourse.section_display``.

        *choice_labels* maps ``{field_name: {stored_value: label}}`` for the
        fields whose options are tenant-configured ``value:Label`` pairs, so
        the display shows the label rather than the opaque stored code. A
        value with no entry (a retired option) renders as itself.
        """
        display = template
        choice_labels = choice_labels or {}

        file_fields = set(cls.get_file_field_names())
        date_fields = set(cls.get_date_field_names())

        for key, value in section.items():
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "Yes" if value else ""
            elif value and key in file_fields:
                link_label = cls.get_field_meta(key).get("default_label", key)
                if urlparse(str(value)).scheme.lower() in ("http", "https"):
                    value = format_html(
                        "<a href='{}' target='_blank'>{}</a>",
                        value, link_label,
                    )
                else:
                    # Unsupported scheme (e.g. javascript:) — render no
                    # anchor rather than a bare, unvalidated URL.
                    value = ""
            elif value and key in date_fields:
                value = _display_date(value)
            else:
                if key in choice_labels:
                    value = choice_labels[key].get(value, value)
                # Ordinary section values (notes, class_period,
                # highschool_course_name, etc.) come from instructor input
                # and are substituted into a template that is rendered as
                # raw HTML (mark_safe below) — escape them so instructor
                # input can't execute as HTML/JS in the CE admin's browser.
                value = escape(value)
            display = display.replace("{" + key + "}", str(value))

        # Syllabus link placeholder
        if show_syllabus and section.get("file"):
            syllabus_link = f"<a href='{section.get('file')}' target='_blank'>Syllabus</a>"
        else:
            syllabus_link = ""
        display = display.replace("{syllabus_link}", syllabus_link)

        # Cleanup
        display = re.sub(r"\{[^}]+\}", "", display)        # unused placeholders
        display = re.sub(r"\s*\|\s*\|\s*", " | ", display)  # double pipes
        display = re.sub(r"^\s*\|\s*|\s*\|\s*$", "", display)  # leading/trailing pipes
        display = re.sub(r"\s+", " ", display)               # whitespace

        # Result intentionally contains HTML (syllabus link). Marking it safe
        # so callers rendering through Django templates don't have to remember
        # the |safe filter on every accessor.
        return mark_safe(display.strip())

    @classmethod
    def settings_help_text(cls) -> str:
        """Auto-generated field reference for the settings page."""
        names = cls.get_available_field_names()
        field_list = ", ".join(names)
        placeholder_list = ", ".join(f"{{{n}}}" for n in names)
        return (
            f"Available fields: {field_list}\n"
            f"Display placeholders: {{term_name}}, {placeholder_list}, {{syllabus_link}}"
        )
