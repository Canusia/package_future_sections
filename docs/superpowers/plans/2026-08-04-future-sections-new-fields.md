# Future Sections New Fields & Drag-and-Drop Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four configurable per-section fields (`start_date`, `end_date`, `assessment_upload`, `new_teacher_email`) to the future-sections teaching form, and replace numeric weight entry in the CE settings field tables with drag-and-drop row reordering.

**Architecture:** `TeachingSectionFieldSchema` in `schemas.py` is the single source of truth for configurable fields — the Django form, the settings UI table, export headers, and display placeholders all derive from it. This change teaches the schema three new widget types (`file`, `date`, `email`), declares four fields using them, and generalises the two places that currently hardcode field names (the dependent-field map in `forms.py` and the dependent-field blocks in `teaching_course.html`). The settings tables keep their existing `weights` JSON format; drag-and-drop simply renumbers the (now readonly) weight inputs and fires the `input` event the existing serializer already listens for.

**Tech Stack:** Django 5.2, Pydantic (schema metadata only), crispy-forms/Bootstrap 4, jQuery + native HTML5 drag-and-drop, Django `SimpleTestCase`/`TestCase`.

## Global Constraints

- **Package:** all work happens inside `/repos/ewu/webapp/future_sections` — this is the `Canusia/package_future_sections` submodule, a separate git repo. Commit inside it, not in the host repo.
- **Import path:** tests import from `future_sections.future_sections.<module>` (the editable nested-submodule layout). Application code inside the package uses relative imports (`from .schemas import …`, `from ..schemas import …`).
- **Design spec:** `docs/superpowers/specs/2026-08-04-future-sections-new-fields-design.md`. Read it before starting.
- **Stored JSON formats are frozen.** `teaching_form_config` keeps exactly its current keys (`fields`, `required`, `labels`, `help_texts`, `weights`, `show_syllabus`, `display_template`); `add_teacher_form_config` keeps `fields`, `required`, `labels`, `help_texts`, `weights`. No migration of existing tenant settings, and no migration of existing `FutureCourse.section_info` rows.
- **`syllabus` is out of scope.** Do not convert it to a schema field, do not change its `file` storage key, do not change `show_syllabus`, and do not change the `{syllabus_link}` placeholder. Its code paths must keep working untouched.
- **No model migrations.** All state lives in the settings JSON and in `FutureCourse.section_info` (a `JSONField`). If you find yourself running `makemigrations`, you have gone off-plan.
- **Everything written into `section_info` must be JSON-serializable.** `datetime.date` objects are not. Date values are stored as ISO `YYYY-MM-DD` strings.
- **Test command** (run from the host repo, targets the running container):
  ```bash
  docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.<module> --keepdb
  ```
  `--keepdb` is required — without it the runner prompts to destroy the existing test database and dies on `EOFError`.
- **Full package suite** (run before the final commit):
  ```bash
  docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
  ```
- **Do not run `git push`, do not tag, and do not touch `webapp/requirements.txt`.** Shipping is a separate step handled after review.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `future_sections/schemas.py` | Field metadata, Django field construction, display formatting | Modify — 3 widget types, 4 fields, 4 introspection classmethods, display formatting |
| `future_sections/forms.py` | `TeacherCourseSectionForm` field generation and validation | Modify — schema-derived dependents, file companions, date validation/serialization |
| `future_sections/utils.py` | Formset → `section_info` payload conversion | Modify — generic file-field upload loop |
| `future_sections/templatetags/future_sections_tags.py` | Template helpers for dynamic field rendering | Modify — 3 new tags |
| `future_sections/templates/future_sections/teaching_course.html` | Instructor-facing teaching form | Modify — generic dependent rendering, file companion rendering, DOM-derived toggle JS |
| `future_sections/settings/future_sections.py` | CE settings form + config table markup | Modify — grip column, readonly weights, new `Media` entry |
| `future_sections/staticfiles/future_sections/js/field_reorder.js` | Generic drag-and-drop row reordering | **Create** |
| `future_sections/staticfiles/future_sections/js/settings.js` | Settings config table serialization | Modify — apply saved order, wire up reorder |
| `future_sections/tests/test_new_section_fields.py` | Schema declarations + widget types | **Create** |
| `future_sections/tests/test_form_field_wiring.py` | Form generation: dependents, file companions, labels | **Create** |
| `future_sections/tests/test_date_validation.py` | Date ordering + ISO serialization | **Create** |
| `future_sections/tests/test_file_field_payload.py` | Upload / carry-forward behaviour | **Create** |
| `future_sections/tests/test_section_display.py` | File and date rendering in display templates | **Create** |
| `future_sections/tests/test_template_tags.py` | The three new template tags | **Create** |

`MANIFEST.in` already has `recursive-include future_sections/staticfiles *`, so the new JS file ships without packaging changes. No `MANIFEST.in` or `setup.py` edits are needed.

---

### Task 1: Schema — new widget types, new fields, introspection helpers

**Files:**
- Modify: `future_sections/schemas.py`
- Test: `future_sections/tests/test_new_section_fields.py` (create)

**Interfaces:**
- Consumes: nothing (first task).
- Produces, all on `TeachingSectionFieldSchema`:
  - `get_dependent_fields() -> dict[str, str]` — `{field_name: parent_field_name}` for every field declaring `depends_on`.
  - `get_dependents_of(parent: str) -> list[str]` — field names depending on `parent`, in schema declaration order.
  - `get_file_field_names() -> list[str]` — field names whose `widget_type` is `file`.
  - `get_date_field_names() -> list[str]` — field names whose `widget_type` is `date`.
  - Four new schema fields: `start_date`, `end_date`, `assessment_upload`, `new_teacher_email`.
  - `make_django_form_field` handles `widget_type` values `file`, `date`, `email` when `visible=True`.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_new_section_fields.py`:

```python
from django import forms
from django.test import SimpleTestCase

from future_sections.future_sections.schemas import TeachingSectionFieldSchema


class NewFieldDeclarationTests(SimpleTestCase):
    def test_all_four_new_fields_are_available(self):
        names = TeachingSectionFieldSchema.get_available_field_names()
        for name in ('start_date', 'end_date', 'assessment_upload',
                     'new_teacher_email'):
            self.assertIn(name, names)

    def test_start_date_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('start_date')
        self.assertEqual(meta.get('widget_type'), 'date')
        self.assertEqual(meta.get('field_type'), 'date')
        self.assertEqual(meta.get('default_label'), 'Start Date')

    def test_end_date_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('end_date')
        self.assertEqual(meta.get('widget_type'), 'date')
        self.assertEqual(meta.get('default_label'), 'End Date')

    def test_end_date_does_not_depend_on_start_date(self):
        meta = TeachingSectionFieldSchema.get_field_meta('end_date')
        self.assertIsNone(meta.get('depends_on'))

    def test_assessment_upload_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('assessment_upload')
        self.assertEqual(meta.get('widget_type'), 'file')
        self.assertEqual(meta.get('default_label'), 'Assessment Upload')

    def test_new_teacher_email_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('new_teacher_email')
        self.assertEqual(meta.get('widget_type'), 'email')
        self.assertEqual(meta.get('default_label'), 'New Teacher Email')
        self.assertEqual(meta.get('depends_on'), 'teacher_changed')


class IntrospectionHelperTests(SimpleTestCase):
    def test_get_dependent_fields_maps_child_to_parent(self):
        deps = TeachingSectionFieldSchema.get_dependent_fields()
        self.assertEqual(deps.get('new_teacher_name'), 'teacher_changed')
        self.assertEqual(deps.get('new_teacher_email'), 'teacher_changed')
        self.assertEqual(deps.get('new_highschool_title'),
                         'highschool_title_changed')
        self.assertNotIn('estimated_enrollment', deps)

    def test_get_dependents_of_returns_declaration_order(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_dependents_of('teacher_changed'),
            ['new_teacher_name', 'new_teacher_email'])

    def test_get_dependents_of_unknown_parent_is_empty(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_dependents_of('notes'), [])

    def test_get_file_field_names(self):
        self.assertEqual(TeachingSectionFieldSchema.get_file_field_names(),
                         ['assessment_upload'])

    def test_get_date_field_names(self):
        self.assertEqual(TeachingSectionFieldSchema.get_date_field_names(),
                         ['start_date', 'end_date'])


class WidgetTypeTests(SimpleTestCase):
    def test_visible_file_field_is_a_filefield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=True)
        self.assertIsInstance(field, forms.FileField)
        self.assertIsInstance(field.widget, forms.ClearableFileInput)
        self.assertEqual(field.label, 'Assessment Upload')

    def test_hidden_file_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=False)
        self.assertIsInstance(field, forms.CharField)
        self.assertNotIsInstance(field, forms.FileField)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_visible_date_field_is_a_datefield_with_date_input(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=True)
        self.assertIsInstance(field, forms.DateField)
        self.assertEqual(field.widget.attrs.get('type'), 'date')

    def test_date_field_accepts_iso_and_us_formats(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=True)
        self.assertIn('%Y-%m-%d', field.input_formats)
        self.assertIn('%m/%d/%Y', field.input_formats)

    def test_hidden_date_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=False)
        self.assertIsInstance(field, forms.CharField)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_visible_email_field_is_an_emailfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'new_teacher_email', visible=True)
        self.assertIsInstance(field, forms.EmailField)

    def test_hidden_email_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'new_teacher_email', visible=False)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_required_flag_is_honoured_for_new_widget_types(self):
        for name in ('assessment_upload', 'start_date', 'new_teacher_email'):
            field = TeachingSectionFieldSchema.make_django_form_field(
                name, visible=True, required=True)
            self.assertTrue(field.required, name)

    def test_label_and_help_text_overrides_apply(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=True,
            label_override='Rubric', help_text_override='PDF only')
        self.assertEqual(field.label, 'Rubric')
        self.assertEqual(field.help_text, 'PDF only')
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_new_section_fields --keepdb
```

Expected: FAIL — `AttributeError: type object 'TeachingSectionFieldSchema' has no attribute 'get_dependent_fields'` and assertion failures on the missing fields.

- [ ] **Step 3: Declare the four new schema fields**

In `future_sections/schemas.py`, insert these four declarations immediately after the existing `new_highschool_title` field and before the `# Utility class methods` comment block. Declaration order matters — it is the default order of the settings table rows and of `get_dependents_of`, and `new_teacher_email` must come after `new_teacher_name`.

```python
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
```

**`new_teacher_email` must be declared after `new_teacher_name`.** `get_dependents_of('teacher_changed')` returns declaration order, and the template renders the dependents in that order — name before email.

- [ ] **Step 4: Add the introspection classmethods**

In `schemas.py`, add these four classmethods immediately after `get_field_meta`:

```python
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
```

`get_dependent_fields` iterates `get_available_field_names()`, which returns Pydantic's `model_fields` in declaration order, so `get_dependents_of` is order-stable.

- [ ] **Step 5: Handle the three new widget types in `make_django_form_field`**

In `make_django_form_field`, the `visible=False` branch needs **no change** — `date`, `email`, and `file` all fall through to the existing `CharField` + `HiddenInput` default, which is exactly what a hidden field should be. (A hidden `file` must not be a `FileField`: nothing is posted for it, so a required `FileField` would fail validation and a saved URL would be lost.)

In the visible branch, insert these three blocks after the `field_type == "integer"` block and before the `if widget_type == "select":` block:

```python
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
```

The `format="%Y-%m-%d"` on the widget matters: an `<input type="date">` only pre-fills from an ISO-formatted value, so without it a saved date renders as an empty picker.

- [ ] **Step 6: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_new_section_fields --keepdb
```

Expected: PASS, all tests.

- [ ] **Step 7: Run the existing schema-adjacent tests to check for regressions**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field future_sections.future_sections.tests.test_course_display future_sections.future_sections.tests.test_settings_review_fields --keepdb
```

Expected: PASS. If `test_course_display` fails on a placeholder or label list, the new fields have changed auto-generated help text — read the assertion and update the *test* only if it hardcodes the old field list; do not remove the new fields.

- [ ] **Step 8: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/schemas.py future_sections/tests/test_new_section_fields.py
git commit -m "feat(schemas): add file/date/email widget types and four new section fields"
```

---

### Task 2: Form wiring — schema-derived dependents and file companions

**Files:**
- Modify: `future_sections/forms.py:255-320` (inside `TeacherCourseSectionForm.__init__`)
- Test: `future_sections/tests/test_form_field_wiring.py` (create)

**Interfaces:**
- Consumes: `TeachingSectionFieldSchema.get_dependent_fields()`, `get_file_field_names()` (Task 1).
- Produces: for each **visible** file field `<name>`, the form also declares a hidden companion `CharField` named `<name>_existing` whose initial value is the previously stored URL. `utils.build_sections_payload` (Task 4) and `teaching_course.html` (Task 6) both rely on that exact `_existing` suffix.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_form_field_wiring.py`:

```python
import json

from django import forms
from django.test import TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm


class _ConfigMixin:
    def _make_setting(self, fields, required=('term',)):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': list(required),
                }),
            },
        )


class DependentFieldVisibilityTests(_ConfigMixin, TestCase):
    def test_enabling_teacher_changed_makes_both_dependents_visible(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        for name in ('new_teacher_name', 'new_teacher_email'):
            self.assertNotIsInstance(
                form.fields[name].widget, forms.HiddenInput, name)

    def test_dependents_are_hidden_when_parent_is_not_enabled(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        for name in ('new_teacher_name', 'new_teacher_email'):
            self.assertIsInstance(
                form.fields[name].widget, forms.HiddenInput, name)

    def test_new_teacher_email_is_an_emailfield_when_visible(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        self.assertIsInstance(form.fields['new_teacher_email'],
                              forms.EmailField)

    def test_highschool_title_dependent_still_works(self):
        self._make_setting(fields=('term', 'highschool_title_changed'))
        form = TeacherCourseSectionForm()
        self.assertNotIsInstance(
            form.fields['new_highschool_title'].widget, forms.HiddenInput)


class FileCompanionFieldTests(_ConfigMixin, TestCase):
    def test_visible_file_field_gets_a_hidden_existing_companion(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        self.assertIn('assessment_upload_existing', form.fields)
        self.assertIsInstance(
            form.fields['assessment_upload_existing'].widget,
            forms.HiddenInput)
        self.assertFalse(form.fields['assessment_upload_existing'].required)

    def test_no_companion_when_file_field_is_not_visible(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        self.assertNotIn('assessment_upload_existing', form.fields)

    def test_companion_is_seeded_with_the_stored_url(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm(
            initial={'assessment_upload': 'https://x.test/a.pdf'})
        self.assertEqual(
            form.fields['assessment_upload_existing'].initial,
            'https://x.test/a.pdf')

    def test_label_gains_a_download_link_when_a_file_is_stored(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm(
            initial={'assessment_upload': 'https://x.test/a.pdf'})
        label = str(form.fields['assessment_upload'].label)
        self.assertIn('https://x.test/a.pdf', label)
        self.assertIn('Assessment Upload', label)

    def test_label_is_plain_when_no_file_is_stored(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        self.assertEqual(form.fields['assessment_upload'].label,
                         'Assessment Upload')

    def test_syllabus_handling_is_unchanged(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term'],
                    'required': ['term'],
                    'show_syllabus': True,
                }),
            },
        )
        form = TeacherCourseSectionForm(
            initial={'file': 'https://x.test/syllabus.pdf'})
        self.assertIn('https://x.test/syllabus.pdf',
                      str(form.fields['syllabus'].label))
        self.assertNotIn('syllabus_existing', form.fields)
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_form_field_wiring --keepdb
```

Expected: FAIL — `KeyError: 'assessment_upload_existing'` and the dependent-visibility assertions for `new_teacher_email`.

- [ ] **Step 3: Replace the hardcoded dependent map**

In `future_sections/forms.py`, inside `TeacherCourseSectionForm.__init__`, replace this block:

```python
        # Generate configurable fields from schema
        # Dependent fields are always visible when their parent is visible
        dependent_fields = {
            'new_teacher_name': 'teacher_changed',
            'new_highschool_title': 'highschool_title_changed',
        }
```

with:

```python
        # Generate configurable fields from schema
        # Dependent fields are always visible when their parent is visible
        dependent_fields = TeachingSectionFieldSchema.get_dependent_fields()
```

The loop that follows already reads `dependent_fields[field_name]`, so it now picks up `new_teacher_email` with no further edits.

- [ ] **Step 4: Add the file companion fields**

Still in `__init__`, immediately **after** the `for field_name in TeachingSectionFieldSchema.get_available_field_names():` loop closes and before the `# Set initial value for highschool_course_name` comment, insert:

```python
        # File fields keep their previously stored URL in a hidden companion so
        # that saving without re-uploading does not wipe the existing file.
        file_initial = kwargs.get('initial') or {}
        for file_name in TeachingSectionFieldSchema.get_file_field_names():
            if file_name not in visible_fields:
                continue
            self.fields[f'{file_name}_existing'] = forms.CharField(
                required=False,
                widget=forms.HiddenInput(),
            )
            stored_url = file_initial.get(file_name)
            if stored_url:
                self.fields[f'{file_name}_existing'].initial = stored_url
                self.fields[file_name].label = mark_safe(
                    f"{self.fields[file_name].label}<br>"
                    f"<small><a target='_blank' href='{stored_url}'>"
                    f"Download Uploaded File</a></small>"
                    f" or upload a new file below"
                )
```

Do not reuse the existing `initial` local variable here — it is reassigned further down inside the syllabus block, and reusing it makes the two blocks order-dependent.

- [ ] **Step 5: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_form_field_wiring --keepdb
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/forms.py future_sections/tests/test_form_field_wiring.py
git commit -m "feat(forms): derive dependent fields from schema, add file companion fields"
```

---

### Task 3: Date validation and ISO serialization

**Files:**
- Modify: `future_sections/forms.py` (`TeacherCourseSectionForm.clean`)
- Test: `future_sections/tests/test_date_validation.py` (create)

**Interfaces:**
- Consumes: `TeachingSectionFieldSchema.get_date_field_names()` (Task 1).
- Produces: `clean()` returns `cleaned_data` in which every date field value is an ISO `YYYY-MM-DD` string, never a `datetime.date`. `utils.build_sections_payload` writes this dict straight into a `JSONField`.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_date_validation.py`:

```python
import json

from django.test import TestCase

from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term
from future_sections.future_sections.forms import TeacherCourseSectionForm


class _DateFormMixin:
    def _make_setting(self, fields=('term', 'start_date', 'end_date')):
        self.academic_year = AcademicYear.objects.create(name='2026-2027')
        self.term = Term.objects.create(
            name='Fall 2026', academic_year=self.academic_year)
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.academic_year.id),
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
            },
        )

    def _bind(self, **data):
        payload = {'term': str(self.term.id)}
        payload.update(data)
        return TeacherCourseSectionForm(data=payload)


class DateOrderingTests(_DateFormMixin, TestCase):
    def test_end_before_start_is_rejected(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2026-08-01')
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_end_equal_to_start_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_end_after_start_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)

    def test_only_start_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_only_end_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind(end_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_neither_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind()
        self.assertTrue(form.is_valid(), form.errors)

    def test_hidden_date_fields_impose_no_ordering_constraint(self):
        self._make_setting(fields=('term',))
        form = self._bind(start_date='2026-09-01', end_date='2026-08-01')
        self.assertTrue(form.is_valid(), form.errors)


class DateSerializationTests(_DateFormMixin, TestCase):
    def test_cleaned_dates_are_iso_strings(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['start_date'], '2026-09-01')
        self.assertEqual(form.cleaned_data['end_date'], '2027-05-30')

    def test_cleaned_data_is_json_serializable(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)
        data = dict(form.cleaned_data)
        data.pop('syllabus', None)
        json.dumps(data)  # must not raise

    def test_us_format_input_is_normalized_to_iso(self):
        self._make_setting()
        form = self._bind(start_date='09/01/2026')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['start_date'], '2026-09-01')

    def test_empty_date_stays_empty(self):
        self._make_setting()
        form = self._bind(start_date='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(form.cleaned_data['start_date'], (None, ''))
```

If `AcademicYear` or `Term` require additional non-null fields in this tenant's schema, add them to the `objects.create(...)` calls — do not change the assertions.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_date_validation --keepdb
```

Expected: FAIL — `test_end_before_start_is_rejected` passes validation, and the serialization tests raise `TypeError: Object of type date is not JSON serializable`.

- [ ] **Step 3: Add validation and serialization to `clean`**

In `future_sections/forms.py`, replace `TeacherCourseSectionForm.clean` in full:

```python
    def clean(self):
        super().clean()

        data = self.cleaned_data

        term = data.get('term')
        if term:
            data['term_name'] = str(term)
            data['term'] = str(term.id)

        # Only compare when both values actually parsed as dates. Hidden date
        # fields are CharFields, so their values are plain strings and this
        # check correctly no-ops for them.
        start = data.get('start_date')
        end = data.get('end_date')
        if isinstance(start, datetime.date) and isinstance(end, datetime.date) \
                and end < start:
            self.add_error(
                'end_date',
                'End Date cannot be earlier than Start Date.')

        # section_info is a JSONField; date objects are not JSON serializable.
        for date_name in TeachingSectionFieldSchema.get_date_field_names():
            value = data.get(date_name)
            if isinstance(value, datetime.date):
                data[date_name] = value.isoformat()

        return data
```

Add `import datetime` to the top of `forms.py` if it is not already imported. `TeachingSectionFieldSchema` is already imported at `forms.py:19`.

- [ ] **Step 4: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_date_validation --keepdb
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/forms.py future_sections/tests/test_date_validation.py
git commit -m "feat(forms): validate date ordering and serialize dates as ISO strings"
```

---

### Task 4: Generic file upload in the section payload

**Files:**
- Modify: `future_sections/utils.py:380-420` (`build_sections_payload`)
- Test: `future_sections/tests/test_file_field_payload.py` (create)

**Interfaces:**
- Consumes: `TeachingSectionFieldSchema.get_file_field_names()` (Task 1); the `<name>_existing` companion convention (Task 2).
- Produces: `section_info['sections'][i]['assessment_upload']` holds the stored URL string (or `''`). The `_existing` companion keys never appear in the persisted payload.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_file_field_payload.py`:

```python
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, RequestFactory

from future_sections.future_sections.utils import build_sections_payload


class _FakeForm:
    def __init__(self, cleaned_data):
        self.cleaned_data = cleaned_data


class _FakeCourse:
    id = 'abc-123'


class _FakeStorage:
    def save(self, name, content):
        return name

    def url(self, name):
        return f'https://files.test/{name}'


def _post(files=None):
    factory = RequestFactory()
    request = factory.post('/', data=files or {})
    return request


class FilePayloadTests(SimpleTestCase):
    def _run(self, forms, files=None):
        request = _post(files)
        with mock.patch(
            'cis.backends.storage_backend.PrivateMediaStorage',
            _FakeStorage,
        ):
            return build_sections_payload(request, forms, _FakeCourse())

    def test_uploaded_file_is_stored_under_the_field_name(self):
        upload = SimpleUploadedFile('rubric.pdf', b'data')
        sections = self._run(
            [_FakeForm({'term': 't1', 'assessment_upload': None})],
            files={'form-0-assessment_upload': upload},
        )
        self.assertEqual(
            sections[0]['assessment_upload'],
            'https://files.test/future_section/abc-123/rubric.pdf')

    def test_existing_url_is_carried_forward_when_no_new_upload(self):
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })])
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/old.pdf')

    def test_companion_key_is_not_persisted(self):
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })])
        self.assertNotIn('assessment_upload_existing', sections[0])

    def test_new_upload_replaces_the_existing_url(self):
        upload = SimpleUploadedFile('new.pdf', b'data')
        sections = self._run(
            [_FakeForm({
                'term': 't1',
                'assessment_upload': None,
                'assessment_upload_existing': 'https://files.test/old.pdf',
            })],
            files={'form-0-assessment_upload': upload},
        )
        self.assertEqual(
            sections[0]['assessment_upload'],
            'https://files.test/future_section/abc-123/new.pdf')

    def test_hidden_file_field_value_is_preserved(self):
        # When the field is not visible it arrives as a plain URL string.
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': 'https://files.test/kept.pdf',
        })])
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/kept.pdf')

    def test_missing_file_yields_empty_string(self):
        sections = self._run([_FakeForm({'term': 't1'})])
        self.assertEqual(sections[0]['assessment_upload'], '')

    def test_rows_without_a_term_are_still_skipped(self):
        sections = self._run([_FakeForm({'term': ''})])
        self.assertEqual(sections, [])

    def test_syllabus_still_lands_in_the_file_key(self):
        upload = SimpleUploadedFile('syllabus.pdf', b'data')
        sections = self._run(
            [_FakeForm({'term': 't1', 'syllabus': None})],
            files={'form-0-syllabus': upload},
        )
        self.assertEqual(
            sections[0]['file'],
            'https://files.test/future_section/abc-123/syllabus.pdf')
        self.assertNotIn('syllabus', sections[0])
```

`PrivateMediaStorage` is imported inside the function body, so patching `cis.backends.storage_backend.PrivateMediaStorage` intercepts it. If the patch does not take effect, check whether the import moved to module scope and patch `future_sections.future_sections.utils.PrivateMediaStorage` instead — do not weaken the assertions.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_file_field_payload --keepdb
```

Expected: FAIL — `KeyError: 'assessment_upload'` on the first several tests.

- [ ] **Step 3: Add the generic file loop**

In `future_sections/utils.py`, inside `build_sections_payload`, replace the body of the per-section loop:

```python
        uploaded = request.FILES.get(f'form-{index}-syllabus')
        if uploaded:
            storage = PrivateMediaStorage()
            safe_name = get_valid_filename(uploaded.name)
            stored_path = storage.save(
                f'future_section/{future_course.id}/{safe_name}',
                uploaded,
            )
            cleaned['file'] = storage.url(stored_path)

        cleaned.pop('syllabus', None)
        sections.append(cleaned)
```

with:

```python
        uploaded = request.FILES.get(f'form-{index}-syllabus')
        if uploaded:
            storage = PrivateMediaStorage()
            safe_name = get_valid_filename(uploaded.name)
            stored_path = storage.save(
                f'future_section/{future_course.id}/{safe_name}',
                uploaded,
            )
            cleaned['file'] = storage.url(stored_path)

        cleaned.pop('syllabus', None)

        # Schema-driven file fields store their URL under their own key.
        for file_name in TeachingSectionFieldSchema.get_file_field_names():
            uploaded = request.FILES.get(f'form-{index}-{file_name}')
            if uploaded:
                storage = PrivateMediaStorage()
                safe_name = get_valid_filename(uploaded.name)
                stored_path = storage.save(
                    f'future_section/{future_course.id}/{safe_name}',
                    uploaded,
                )
                cleaned[file_name] = storage.url(stored_path)
            elif not cleaned.get(file_name):
                # No new upload: keep whatever was already stored. A hidden
                # file field already carries the URL in cleaned[file_name].
                cleaned[file_name] = cleaned.get(f'{file_name}_existing', '')
            cleaned.pop(f'{file_name}_existing', None)

        sections.append(cleaned)
```

Add the import at the top of `utils.py`:

```python
from .schemas import TeachingSectionFieldSchema
```

Also extend the function docstring's bullet list with:

```
      - Uploads any `form-<i>-<name>` file for each schema file field and
        stores the resulting URL under that field's own key, carrying forward
        the previous URL from `<name>_existing` when nothing new is posted.
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_file_field_payload --keepdb
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/utils.py future_sections/tests/test_file_field_payload.py
git commit -m "feat(utils): upload schema file fields into their own section keys"
```

---

### Task 5: Display formatting for file and date values

**Files:**
- Modify: `future_sections/schemas.py` (`format_section_display`)
- Test: `future_sections/tests/test_section_display.py` (create)

**Interfaces:**
- Consumes: `get_file_field_names()`, `get_date_field_names()` (Task 1).
- Produces: nothing new — `format_section_display` keeps its existing signature `(section: dict, template: str, show_syllabus: bool = True) -> str`.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_section_display.py`:

```python
from django.test import SimpleTestCase

from future_sections.future_sections.schemas import TeachingSectionFieldSchema


class FileDisplayTests(SimpleTestCase):
    def test_file_value_renders_as_a_link_labelled_by_the_field(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'assessment_upload': 'https://files.test/a.pdf'},
            '{assessment_upload}')
        self.assertIn("href='https://files.test/a.pdf'", out)
        self.assertIn('Assessment Upload', out)
        self.assertIn('target=\'_blank\'', out)

    def test_empty_file_value_renders_as_nothing(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'assessment_upload': ''}, 'X {assessment_upload} Y')
        self.assertNotIn('href', out)
        self.assertEqual(out, 'X Y')


class DateDisplayTests(SimpleTestCase):
    def test_iso_date_renders_in_us_format(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': '2026-09-01'}, '{start_date}')
        self.assertEqual(out, '09/01/2026')

    def test_both_dates_render(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': '2026-09-01', 'end_date': '2027-05-30'},
            '{start_date} to {end_date}')
        self.assertEqual(out, '09/01/2026 to 05/30/2027')

    def test_unparseable_date_falls_back_to_the_raw_value(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': 'sometime'}, '{start_date}')
        self.assertEqual(out, 'sometime')

    def test_empty_date_renders_as_nothing(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': ''}, 'X {start_date} Y')
        self.assertEqual(out, 'X Y')


class ExistingBehaviourTests(SimpleTestCase):
    def test_syllabus_link_still_works(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'file': 'https://files.test/s.pdf'}, '{syllabus_link}')
        self.assertIn('Syllabus', out)
        self.assertIn('https://files.test/s.pdf', out)

    def test_boolean_and_plain_values_are_unchanged(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'full_year': True, 'estimated_enrollment': '25'},
            '{full_year} | {estimated_enrollment}')
        self.assertEqual(out, 'Yes | 25')

    def test_unused_placeholders_are_stripped(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'estimated_enrollment': '25'},
            '{estimated_enrollment} | {class_period}')
        self.assertEqual(out, '25')
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_section_display --keepdb
```

Expected: FAIL — file values render as raw URLs and dates render as ISO strings.

- [ ] **Step 3: Add a date-formatting module helper**

In `future_sections/schemas.py`, add near the top of the module (after the imports, before the class):

```python
def _display_date(value: str) -> str:
    """Render an ISO date string as ``m/d/Y``; pass anything else through."""
    try:
        return datetime.date.fromisoformat(str(value)).strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return str(value)
```

Add `import datetime` to the module imports.

- [ ] **Step 4: Use it in `format_section_display`**

In `format_section_display`, replace the value-normalisation loop:

```python
        for key, value in section.items():
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "Yes" if value else ""
            display = display.replace("{" + key + "}", str(value))
```

with:

```python
        file_fields = set(cls.get_file_field_names())
        date_fields = set(cls.get_date_field_names())

        for key, value in section.items():
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "Yes" if value else ""
            elif value and key in file_fields:
                link_label = cls.get_field_meta(key).get("default_label", key)
                value = (
                    f"<a href='{value}' target='_blank'>{link_label}</a>"
                )
            elif value and key in date_fields:
                value = _display_date(value)
            display = display.replace("{" + key + "}", str(value))
```

The result is already `mark_safe`d at the end of the method, so the anchor renders as HTML.

- [ ] **Step 5: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_section_display --keepdb
```

Expected: PASS.

- [ ] **Step 6: Run the existing display tests for regressions**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_course_display --keepdb
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/schemas.py future_sections/tests/test_section_display.py
git commit -m "feat(schemas): render file fields as links and dates as m/d/Y in section display"
```

---

### Task 6: Template tags and generic dependent-field rendering

**Files:**
- Modify: `future_sections/templatetags/future_sections_tags.py`
- Modify: `future_sections/templates/future_sections/teaching_course.html:40-67` and `:128-137`
- Test: `future_sections/tests/test_template_tags.py` (create)

**Interfaces:**
- Consumes: `get_dependents_of()`, `get_dependent_fields()` (Task 1); the `<name>_existing` convention (Task 2).
- Produces: three template tags — `dependent_fields(form, parent_field_name) -> list[BoundField]`, `is_dependent_field(field_name) -> bool`, `get_existing_file_field(form, field_name) -> BoundField | None`.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_template_tags.py`:

```python
import json

from django.test import TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm
from future_sections.future_sections.templatetags.future_sections_tags import (
    dependent_fields,
    get_existing_file_field,
    is_dependent_field,
)


class _ConfigMixin:
    def _make_setting(self, fields):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
            },
        )


class IsDependentFieldTests(TestCase):
    def test_dependent_names_are_reported(self):
        for name in ('new_teacher_name', 'new_teacher_email',
                     'new_highschool_title'):
            self.assertTrue(is_dependent_field(name), name)

    def test_independent_names_are_not(self):
        for name in ('term', 'estimated_enrollment', 'start_date',
                     'assessment_upload'):
            self.assertFalse(is_dependent_field(name), name)


class DependentFieldsTests(_ConfigMixin, TestCase):
    def test_returns_name_then_email_for_teacher_changed(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        names = [f.name for f in dependent_fields(form, 'teacher_changed')]
        self.assertEqual(names, ['new_teacher_name', 'new_teacher_email'])

    def test_returns_the_highschool_dependent(self):
        self._make_setting(fields=('term', 'highschool_title_changed'))
        form = TeacherCourseSectionForm()
        names = [f.name
                 for f in dependent_fields(form, 'highschool_title_changed')]
        self.assertEqual(names, ['new_highschool_title'])

    def test_returns_empty_for_a_field_with_no_dependents(self):
        self._make_setting(fields=('term', 'notes'))
        form = TeacherCourseSectionForm()
        self.assertEqual(dependent_fields(form, 'notes'), [])


class ExistingFileFieldTests(_ConfigMixin, TestCase):
    def test_returns_the_companion_when_the_file_field_is_visible(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        field = get_existing_file_field(form, 'assessment_upload')
        self.assertIsNotNone(field)
        self.assertEqual(field.name, 'assessment_upload_existing')

    def test_returns_none_when_there_is_no_companion(self):
        self._make_setting(fields=('term', 'notes'))
        form = TeacherCourseSectionForm()
        self.assertIsNone(get_existing_file_field(form, 'notes'))
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_template_tags --keepdb
```

Expected: FAIL — `ImportError: cannot import name 'dependent_fields'`.

- [ ] **Step 3: Add the three template tags**

Append to `future_sections/templatetags/future_sections_tags.py`:

```python
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
    companion = f'{field_name}_existing'
    if companion in form.fields:
        return form[companion]
    return None
```

- [ ] **Step 4: Run the tag test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_template_tags --keepdb
```

Expected: PASS.

- [ ] **Step 5: Rewrite the field loop in the template**

In `future_sections/templates/future_sections/teaching_course.html`, replace the whole `{% for field_name in form_config.fields %}` block (from `{# Dynamically render configured fields #}` down to its `{% endfor %}`, i.e. the block containing the hardcoded `new_teacher_name` and `new_highschool_title` `<div>`s) with:

```django
                                    {# Dynamically render configured fields #}
                                    {% for field_name in form_config.fields %}
                                        {% is_dependent_field field_name as field_is_dependent %}
                                        {% if field_name != 'term' and not field_is_dependent %}
                                        <div class="col-12">
                                            {% get_form_field teaching_form field_name as field %}
                                            {% if field %}
                                                {{ field|as_crispy_field }}
                                            {% endif %}
                                            {% get_existing_file_field teaching_form field_name as existing_file %}
                                            {% if existing_file %}
                                                {{ existing_file }}
                                            {% endif %}
                                        </div>
                                        {# Conditional fields render under their parent #}
                                        {% dependent_fields teaching_form field_name as dependents %}
                                        {% for dependent in dependents %}
                                        <div class="col-12 dependent-field-wrapper" data-depends-on="{{ field_name }}">
                                            {{ dependent|as_crispy_field }}
                                        </div>
                                        {% endfor %}
                                        {% endif %}
                                    {% endfor %}
```

Notes:
- The `style="display:none;"` inline attribute is dropped. The toggle JS runs on page load and hides wrappers whose parent is not "yes", and keeping the inline style would make a wrapper flash hidden then visible when the parent *is* "yes". Losing it means a brief flash of the field before the JS runs, which is the lesser evil and matches how the rest of the form behaves.
- `{{ existing_file }}` is rendered bare, not through `as_crispy_field` — it is a `HiddenInput` and crispy would wrap it in a visible form-group.

- [ ] **Step 6: Derive the toggle field list from the DOM**

Further down in the same file, in the `<script>` block, replace:

```javascript
    // Initialize and bind for all dependent fields
    var dependentFields = ['teacher_changed', 'highschool_title_changed'];
```

with:

```javascript
    // Initialize and bind for all dependent fields. The parent names come from
    // the rendered wrappers, so a new schema field needs no change here.
    var dependentFields = [];
    $('.dependent-field-wrapper').each(function () {
        var parent = $(this).attr('data-depends-on');
        if (parent && dependentFields.indexOf(parent) === -1) {
            dependentFields.push(parent);
        }
    });
```

The `toggleDependentField` function already selects *all* wrappers for a parent (`.dependent-field-wrapper[data-depends-on="…"]`), so both `new_teacher_name` and `new_teacher_email` show, hide, and clear together.

- [ ] **Step 7: Verify the template renders**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py shell -c "
from django.template.loader import get_template
t = get_template('future_sections/teaching_course.html')
print('template compiled OK')
"
```

Expected: `template compiled OK`. A `TemplateSyntaxError` here means a tag name is misspelled or `{% load future_sections_tags %}` is missing (it is already at the top of the file).

- [ ] **Step 8: Run the full package suite**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
```

Expected: PASS. `test_review_views.py` renders instructor pages and will catch a broken template.

- [ ] **Step 9: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/templatetags/future_sections_tags.py \
        future_sections/templates/future_sections/teaching_course.html \
        future_sections/tests/test_template_tags.py
git commit -m "feat(templates): render dependent and file fields from schema metadata"
```

---

### Task 7: Settings config tables — grip column and readonly weights

**Files:**
- Modify: `future_sections/settings/future_sections.py:662-805` (the `teaching_config_html` and `add_teacher_config_html` builders) and `:46-47` (the `Media` class)

**Interfaces:**
- Consumes: nothing from earlier tasks beyond the schema fields being declared (Task 1) so the new rows appear.
- Produces: every draggable `<tbody>` row carries a leading `<td class="fw-grip">` cell; weight inputs are `readonly`; both tables' `<thead>` has a matching leading `<th>`. `field_reorder.js` (Task 8) depends on this markup.

There is no automated test for this task — it is pure markup inside a settings form. Verification is by rendering the settings page.

- [ ] **Step 1: Add the grip cell to the teaching table rows**

In the `for name in schema_fields:` loop that builds `rows_html`, change the opening of each row from:

```python
            rows_html += (
                '<tr>'
                f'<td>{default_label}</td>'
```

to:

```python
            rows_html += (
                '<tr>'
                '<td class="fw-grip text-center text-muted" '
                'style="cursor:move;width:32px;">'
                '<i class="fas fa-grip-vertical"></i></td>'
                f'<td>{default_label}</td>'
```

- [ ] **Step 2: Make the teaching weight input readonly**

In the same loop, change:

```python
                f'<input type="number" class="form-control form-control-sm tfc-weight" '
                f'data-field="{name}" min="0" step="1">'
```

to:

```python
                f'<input type="number" readonly '
                f'class="form-control form-control-sm tfc-weight" '
                f'data-field="{name}" min="0" step="1">'
```

- [ ] **Step 3: Update the teaching table header and helper text**

In `teaching_config_html`, change the header row from:

```python
            '<thead><tr>'
            '<th>Field</th>'
```

to:

```python
            '<thead><tr>'
            '<th style="width:32px"></th>'
            '<th>Field</th>'
```

And add the same leading empty cell to the pinned "Term" row, changing:

```python
            '<tr class="table-light">'
            '<td>Term <span class="badge badge-secondary">Always included</span></td>'
```

to:

```python
            '<tr class="table-light">'
            '<td></td>'
            '<td>Term <span class="badge badge-secondary">Always included</span></td>'
```

Then replace the helper text:

```python
            '<small class="form-text text-muted mb-3 d-block">'
            'Lighter weighted fields appear at the top of the form.</small>'
```

with:

```python
            '<small class="form-text text-muted mb-3 d-block">'
            'Drag a row by its handle to change the order fields appear in the '
            'form. The weight column updates automatically.</small>'
```

- [ ] **Step 4: Apply the same four changes to the Add Teacher table**

In the `for name, default_label in add_teacher_fields:` loop building `at_rows_html`, add the grip `<td>` before the label `<td>` and add `readonly` to the `.atfc-weight` input, exactly as in Steps 1-2.

In `add_teacher_config_html`: add `'<th style="width:32px"></th>'` before `'<th>Field</th>'` in the header; add `'<td></td>'` before the label cell in each of the four `always_included` rows (the loop that emits `<tr class="table-light">`); and replace its helper text with the same drag wording from Step 3.

- [ ] **Step 5: Register the new JS file**

In the `Media` class at the top of `future_sections/settings/future_sections.py`, change:

```python
    class Media:
        js = ('future_sections/js/settings.js',)
```

to:

```python
    class Media:
        js = (
            'future_sections/js/field_reorder.js',
            'future_sections/js/settings.js',
        )
```

`field_reorder.js` must load first — `settings.js` calls `initFieldReorder` during its own init.

- [ ] **Step 6: Verify the settings form still constructs**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_settings_review_fields future_sections.future_sections.tests.test_cycle_terms_settings --keepdb
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/settings/future_sections.py
git commit -m "feat(settings): add drag handles and readonly weights to field config tables"
```

---

### Task 8: Drag-and-drop reordering

**Files:**
- Create: `future_sections/staticfiles/future_sections/js/field_reorder.js`
- Modify: `future_sections/staticfiles/future_sections/js/settings.js`

**Interfaces:**
- Consumes: the grip markup and readonly weight inputs from Task 7.
- Produces: global `window.initFieldReorder(tableSelector, weightInputClass)`.

There is no JS test harness in this package, so this task is verified by rendering the settings page and dragging. Behaviour is deliberately kept thin — reordering only renumbers the weight inputs and fires `input`, which the existing `syncToHidden` already handles.

- [ ] **Step 1: Create the reorder module**

Create `future_sections/staticfiles/future_sections/js/field_reorder.js`:

```javascript
/**
 * Generic drag-and-drop row reordering for settings field-config tables.
 *
 * Rows carrying a `.fw-grip` cell become draggable. On drop, every weight
 * input in the table is renumbered from 0 in DOM order and an `input` event
 * is fired so the table's existing serializer picks up the new order.
 *
 * Rows without a `.fw-grip` cell ("Always included" rows) are not draggable
 * and are not renumbered; they are pinned at the top of the table by the
 * serializer regardless of position.
 */
(function (window, document) {
    'use strict';

    function rowsOf(table) {
        return Array.prototype.slice.call(
            table.querySelectorAll('tbody > tr'));
    }

    function isDraggable(row) {
        return !!(row && row.querySelector('.fw-grip'));
    }

    function tableOf(row) {
        return row ? row.closest('table') : null;
    }

    function renumber(table, weightInputClass) {
        var order = 0;
        rowsOf(table).forEach(function (row) {
            if (!isDraggable(row)) {
                return;
            }
            var input = row.querySelector('.' + weightInputClass);
            if (!input) {
                return;
            }
            input.value = order;
            order += 1;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        });
    }

    function initFieldReorder(tableSelector, weightInputClass) {
        var container = document.querySelector(tableSelector);
        if (!container) {
            return;
        }
        var table = container.querySelector('table');
        if (!table || table.getAttribute('data-reorder-bound') === '1') {
            return;
        }
        table.setAttribute('data-reorder-bound', '1');

        var dragging = null;

        rowsOf(table).forEach(function (row) {
            if (isDraggable(row)) {
                row.setAttribute('draggable', 'true');
            }
        });

        table.addEventListener('dragstart', function (event) {
            var row = event.target.closest('tr');
            if (!isDraggable(row)) {
                return;
            }
            dragging = row;
            row.classList.add('fw-dragging');
            // Firefox requires data to be set for the drag to start.
            event.dataTransfer.setData('text/plain', '');
            event.dataTransfer.effectAllowed = 'move';
        });

        table.addEventListener('dragover', function (event) {
            if (!dragging) {
                return;
            }
            var row = event.target.closest('tr');
            // Only reorder within the table the drag started in, and never
            // past a pinned "Always included" row.
            if (!row || !isDraggable(row) || tableOf(row) !== tableOf(dragging)) {
                return;
            }
            event.preventDefault();
            if (row === dragging) {
                return;
            }
            var rows = rowsOf(table);
            var before = rows.indexOf(row) < rows.indexOf(dragging);
            row.parentNode.insertBefore(
                dragging, before ? row : row.nextSibling);
        });

        table.addEventListener('drop', function (event) {
            if (dragging) {
                event.preventDefault();
            }
        });

        table.addEventListener('dragend', function () {
            if (!dragging) {
                return;
            }
            dragging.classList.remove('fw-dragging');
            dragging = null;
            renumber(table, weightInputClass);
        });
    }

    window.initFieldReorder = initFieldReorder;
})(window, document);
```

- [ ] **Step 2: Add the saved-order helper to `settings.js`**

In `future_sections/staticfiles/future_sections/js/settings.js`, add this function at module scope, above `initTeachingFormConfig`:

```javascript
/**
 * Reorder a config table's draggable rows to match saved weights.
 *
 * Rows render in schema declaration order; without this a saved order does
 * not survive a page reload. Unweighted rows sort last, and ties keep their
 * current DOM order.
 */
function applySavedFieldOrder($ui, weights, inputClass) {
    var $table = $ui.find('table').first();
    var $body = $table.find('tbody').first();
    if (!$body.length) return;

    var rows = [];
    $body.children('tr').each(function (index) {
        var $row = $(this);
        var $input = $row.find('.' + inputClass);
        rows.push({
            el: this,
            draggable: $row.find('.fw-grip').length > 0,
            index: index,
            weight: $input.length && weights.hasOwnProperty($input.data('field'))
                ? weights[$input.data('field')]
                : Number.MAX_SAFE_INTEGER
        });
    });

    rows.filter(function (r) { return r.draggable; })
        .sort(function (a, b) {
            if (a.weight !== b.weight) return a.weight - b.weight;
            return a.index - b.index;
        })
        .forEach(function (r) { $body.append(r.el); });
}
```

`$body.append` moves the existing element rather than copying it, so the pinned non-draggable rows stay where they are and the draggable rows are re-appended after them in weight order.

- [ ] **Step 3: Call it from both init functions**

In `initTeachingFormConfig`, after the `$ui.find('.tfc-weight').each(...)` block that populates the weight inputs, add:

```javascript
    applySavedFieldOrder($ui, weights, 'tfc-weight');
```

In `initAddTeacherFormConfig`, after the `$ui.find('.atfc-weight').each(...)` block, add:

```javascript
    applySavedFieldOrder($ui, weights, 'atfc-weight');
```

- [ ] **Step 4: Wire up the drag behaviour**

At the end of `initTeachingFormConfig`, after the `$hidden.closest('form').on('submit', syncToHidden);` line, add:

```javascript
    if (window.initFieldReorder) {
        window.initFieldReorder('#teaching-form-config-ui', 'tfc-weight');
    }
```

At the end of `initAddTeacherFormConfig`, after its `$hidden.closest('form').on('submit', syncToHidden);` line, add:

```javascript
    if (window.initFieldReorder) {
        window.initFieldReorder('#add-teacher-form-config-ui', 'atfc-weight');
    }
```

The existing `$ui.on('input', '.tfc-label, .tfc-weight', syncToHidden)` delegation (and its `.atfc-` counterpart) already listens for the `input` event `renumber` fires, so no extra binding is needed.

- [ ] **Step 5: Collect static files**

```bash
docker exec django_web_ewu python webapp/manage.py collectstatic --noinput
```

Expected: reports at least one new file copied (`field_reorder.js`).

- [ ] **Step 6: Manually verify in the browser**

Open the CE future-sections settings page. Confirm:
1. Both config tables show a grip icon on each configurable row; the "Always included" rows have no grip.
2. Weight inputs are greyed/readonly and cannot be typed into.
3. Dragging a row by anywhere in the row reorders it, and the weight column renumbers from 0 immediately.
4. A row cannot be dragged from one table into the other.
5. Save, reload the page, and confirm the table renders in the saved order.
6. Enable `start_date`, `end_date`, `assessment_upload`, and `teacher_changed`; drag them into a chosen order; save.
7. On the instructor teaching form, confirm the fields appear in that order, that the date pickers work, that setting "Did the teacher change?" to Yes reveals both New Teacher Name and New Teacher Email, and that uploading an assessment file and re-saving without re-uploading keeps the file.

- [ ] **Step 7: Run the full package suite**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/staticfiles/future_sections/js/field_reorder.js \
        future_sections/staticfiles/future_sections/js/settings.js
git commit -m "feat(settings): drag-and-drop reordering for field config tables"
```

---

## Done

After Task 8, the package is feature-complete and all tests pass. Shipping is a separate, manual step handled outside this plan: push the submodule, tag a release, bump the pin in the host's `webapp/requirements.txt`, and move the gitlink. Do not do any of that as part of executing this plan.
