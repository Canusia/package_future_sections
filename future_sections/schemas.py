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
import re
from typing import Optional

from pydantic import BaseModel, Field

from django import forms
from django.utils.safestring import mark_safe


class TeachingSectionFieldSchema(BaseModel):
    """Defines all configurable fields for the TeacherCourseSectionForm.

    Each field carries metadata in json_schema_extra:
    - default_label: label shown in the form
    - default_help_text: optional help text
    - widget_type: text | textarea | checkbox
    - field_type: string | boolean | integer
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
    instruction_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Instruction Mode",
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
    teacher_changed: Optional[bool] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Did the teacher change?",
            "widget_type": "checkbox",
            "field_type": "boolean",
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
    def make_django_form_field(
        cls,
        name: str,
        *,
        visible: bool = False,
        required: bool = False,
        label_override: str | None = None,
        help_text_override: str | None = None,
    ) -> forms.Field:
        """Build a Django form field from schema metadata.

        When *visible* is False the field is rendered as a HiddenInput.
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
    ) -> str:
        """Render a single section dict through *template*.

        Handles placeholder replacement, syllabus link, and cleanup — identical
        to the logic previously in ``FutureCourse.section_display``.
        """
        display = template

        for key, value in section.items():
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "Yes" if value else ""
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

        return display.strip()

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
