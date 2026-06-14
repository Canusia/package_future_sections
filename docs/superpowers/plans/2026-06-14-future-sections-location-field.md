# Future Sections — Configurable "Location" Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Location" field to the future-sections teaching form whose dropdown options are customizable by CE admins in Settings.

**Architecture:** Section fields in this app are **schema-driven**, not model columns — they live in `FutureCourse.section_info` (a JSONField), are declared once in the Pydantic `TeachingSectionFieldSchema`, and are dynamically rendered by `TeacherCourseSectionForm`. There is already a working precedent for a settings-customizable dropdown: `instruction_mode` (its options come from a pipe-delimited `instruction_modes` Setting). This plan adds `location` by mirroring that pattern exactly: (1) declare `location` as a `select` field in the schema, (2) add a `location_options` field to the settings form, (3) wire the parsed options into the form's `location` field. **No database migration is required** (no new model column), and **no packaging changes** are required (only edits to existing inner-package `.py` files).

**Tech Stack:** Django 5.2 forms, Pydantic schema (`schemas.py`), crispy-forms, the `setting` app + DB-backed `Setting` model (key `cis_future_sections`).

---

## Context the engineer needs

- **Repo:** This is the `future_sections` editable submodule, its own git repo at `/repos/ewu/webapp/future_sections` (currently on branch `main`). The Django app code lives in the **inner** package `future_sections/future_sections/`. The app is installed as `future_sections.future_sections` (DevFutureSectionsConfig), so the test label prefix is `future_sections.future_sections.tests.…`.
- **Run all commands in the tenant container** against the live mount:
  ```
  docker exec -w /app/webapp django_web_ewu python manage.py <cmd>
  ```
  (Never run host `python`; `/app/webapp` is the live mount.)
- **Section data storage:** Each teaching section is a dict inside `FutureCourse.section_info['sections']`. The set of available section fields is defined by `TeachingSectionFieldSchema` (`future_sections/future_sections/schemas.py`). A field only renders for instructors when it is enabled in the `teaching_form_config` JSON (set via the Settings UI). Whether a field is a dropdown is decided by its schema `widget_type: "select"`, and its options come either from `choices` passed by the form or `choices` in the schema metadata.
- **The precedent to mirror — `instruction_mode`:**
  - Schema (`schemas.py`): declared with `"widget_type": "select"`, no hard-coded choices.
  - Settings form (`settings/future_sections.py`): a `instruction_modes` `CharField` holds a pipe-delimited string of options.
  - Form (`forms.py` `TeacherCourseSectionForm.__init__`): parses `instruction_modes` into a `[(v,v), …]` list and passes it as `choices` for the `instruction_mode` field via `extra_kwargs`.
- **Why no migration:** `makemigrations` inspects Django *models*. Adding a Pydantic-schema entry and a `forms.Form` field changes neither model, so `makemigrations future_sections` reports "No changes detected". The `submod-migration-deps` skill does **not** apply here.
- **Why no packaging change:** You only edit existing `.py` files inside `future_sections/future_sections/`. No new template, static file, settings module, or top-level package is added, and `MANIFEST.in` already globs the inner package. The `submod-package-manifest` skill does **not** apply here.
- **Auto-wiring you get for free** (verified — do not re-implement):
  - The Settings UI builds its "Teaching Form Fields" table by iterating `TeachingSectionFieldSchema.get_available_field_names()` (`settings/future_sections.py:603`). Adding `location` to the schema makes it appear automatically as a configurable row (Visible / Required / Custom Label / Weight).
  - The settings form's crispy layout is built by iterating `self.fields.keys()` in declaration order (`settings/future_sections.py:760-772`), and `_to_python()` serializes every cleaned field. So declaring `location_options` after `instruction_modes` auto-renders it in the right place and auto-saves it — no layout or `_to_python` edits needed.
  - CSV export (`schemas.py get_export_labels`) and section display (`schemas.py format_section_display`) iterate active fields generically, so `location` exports/displays automatically once enabled.

---

## File Structure

All paths are inside the inner package `future_sections/future_sections/`.

- **Modify:** `schemas.py` — add the `location` field to `TeachingSectionFieldSchema` (a `select` field). This is the single source of truth that makes `location` an available, configurable, dropdown section field.
- **Modify:** `settings/future_sections.py` — add a `location_options` settings field (pipe-delimited list) plus its section header, immediately after the `instruction_modes` block.
- **Modify:** `forms.py` — in `TeacherCourseSectionForm.__init__`, parse `location_options` into choices and pass them to the generated `location` field (mirror `instruction_mode`).
- **Create:** `tests/test_location_field.py` — schema-level, settings-field-level, and form-wiring tests.

---

## Setup (once, before Task 1)

- [ ] **Branch off `main` in the submodule.** `main` is the default branch, so create a feature branch:
  ```bash
  cd /repos/ewu/webapp/future_sections
  git checkout -b feat/configurable-location-field
  ```

---

## Task 1: Declare `location` as a configurable select field in the schema

**Files:**
- Modify: `future_sections/future_sections/schemas.py` (class `TeachingSectionFieldSchema`, after the `class_period` field, ~line 38)
- Test: `future_sections/future_sections/tests/test_location_field.py` (create)

- [ ] **Step 1: Write the failing test**

Create `future_sections/future_sections/tests/test_location_field.py`:

```python
from django import forms
from django.test import SimpleTestCase

from future_sections.future_sections.schemas import TeachingSectionFieldSchema


class LocationSchemaTests(SimpleTestCase):
    def test_location_is_an_available_field(self):
        self.assertIn(
            'location',
            TeachingSectionFieldSchema.get_available_field_names())

    def test_location_meta_is_a_select_with_label(self):
        meta = TeachingSectionFieldSchema.get_field_meta('location')
        self.assertEqual(meta.get('widget_type'), 'select')
        self.assertEqual(meta.get('default_label'), 'Location')

    def test_make_field_is_a_choicefield_with_provided_choices_when_visible(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'location', visible=True,
            choices=[('Room A', 'Room A'), ('Room B', 'Room B')])
        self.assertIsInstance(field, forms.ChoiceField)
        # The schema prepends a blank choice.
        self.assertEqual(field.choices[0], ('', '---------'))
        self.assertIn(('Room A', 'Room A'), field.choices)

    def test_make_field_is_hidden_when_not_visible(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'location', visible=False)
        self.assertIsInstance(field.widget, forms.HiddenInput)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationSchemaTests -v 2`
Expected: FAIL — `location` is not in the available field names (the first two tests fail; `make_django_form_field('location', …)` returns a generic field because `get_field_meta('location')` is empty).

- [ ] **Step 3: Add the `location` field to the schema**

In `future_sections/future_sections/schemas.py`, inside `class TeachingSectionFieldSchema`, add this field immediately **after** the `class_period` field declaration (so it groups with the other logistics fields):

```python
    location: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "default_label": "Location",
            "widget_type": "select",
            "field_type": "string",
        },
    )
```

(No `choices` in the metadata — like `instruction_mode`, options are supplied at form-build time from settings.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationSchemaTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/schemas.py future_sections/tests/test_location_field.py
git commit -m "feat(location): add configurable location select field to teaching schema"
```

---

## Task 2: Add the `location_options` settings field

**Files:**
- Modify: `future_sections/future_sections/settings/future_sections.py` (class `future_sections`, immediately after the `instruction_modes` field, ~line 396)
- Test: `future_sections/future_sections/tests/test_location_field.py` (append a test class)

- [ ] **Step 1: Write the failing test**

Append to `future_sections/future_sections/tests/test_location_field.py`:

```python
from future_sections.future_sections.settings.future_sections import (
    future_sections as fs_setting_form,
)


class LocationSettingFieldTests(SimpleTestCase):
    def test_location_options_field_is_declared(self):
        self.assertIn('location_options', fs_setting_form.base_fields)

    def test_location_options_field_is_optional(self):
        self.assertFalse(
            fs_setting_form.base_fields['location_options'].required)
```

> `base_fields` is the class-level declared-field dict, so this needs no DB and no form instantiation.

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationSettingFieldTests -v 2`
Expected: FAIL — `KeyError: 'location_options'` (field not declared yet).

- [ ] **Step 3: Add the settings field**

In `future_sections/future_sections/settings/future_sections.py`, immediately **after** the `instruction_modes = forms.CharField(...)` block (which ends ~line 396, before the `# ── Reviewed Status Email ──` header), add:

```python
    # ── Locations ─────────────────────────────────────────────────────────
    location_options_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Locations</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    location_options = forms.CharField(
        max_length=500,
        required=False,
        label="Available Locations",
        help_text='Enter a pipe-delimited list of locations. '
                  'Example: Main Campus|North High|Online. '
                  'These will appear as dropdown options when the Location field is enabled.',
        initial='',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Main Campus|North High|Online'
        })
    )
```

(`FFields` and `mark_safe` are already imported in this module — they are used by the adjacent `instruction_modes_header`.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationSettingFieldTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/settings/future_sections.py future_sections/tests/test_location_field.py
git commit -m "feat(location): add Available Locations setting (pipe-delimited options)"
```

---

## Task 3: Wire the configured options into the form's `location` field

**Files:**
- Modify: `future_sections/future_sections/forms.py` (`TeacherCourseSectionForm.__init__`, the instruction-mode choices block ~lines 221-244 and the schema-field loop ~lines 246-264)
- Test: `future_sections/future_sections/tests/test_location_field.py` (append a test class)

- [ ] **Step 1: Write the failing test**

Append to `future_sections/future_sections/tests/test_location_field.py`:

```python
import json

from django.test import TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm


class LocationFormWiringTests(TestCase):
    def _make_setting(self, location_options='Main Campus|North High|Online',
                      fields=('term', 'location')):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
                'location_options': location_options,
            },
        )

    def test_location_is_choicefield_with_configured_options_when_visible(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        field = form.fields['location']
        from django import forms as djforms
        self.assertIsInstance(field, djforms.ChoiceField)
        self.assertEqual(field.choices[0], ('', '---------'))
        self.assertIn(('Main Campus', 'Main Campus'), field.choices)
        self.assertIn(('Online', 'Online'), field.choices)

    def test_location_is_hidden_when_not_enabled(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        from django import forms as djforms
        self.assertIsInstance(form.fields['location'].widget, djforms.HiddenInput)

    def test_stored_location_not_in_options_is_preserved(self):
        self._make_setting(location_options='Main Campus|Online')
        form = TeacherCourseSectionForm(initial={'location': 'Legacy Room'})
        values = {c[0] for c in form.fields['location'].choices}
        self.assertIn('Legacy Room', values)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationFormWiringTests -v 2`
Expected: FAIL — `location` is generated as a `HiddenInput`/plain field (no choices passed), so `test_location_is_choicefield_with_configured_options_when_visible` fails (`location` is a CharField, or its choices lack the configured options), and `test_stored_location_not_in_options_is_preserved` fails.

- [ ] **Step 3: Parse the options and pass them as choices**

In `future_sections/future_sections/forms.py`, inside `TeacherCourseSectionForm.__init__`:

(a) **After** the existing instruction-mode "ensure stored value is in choices" block (the one that ends with `instruction_mode_choices.append((stored_mode, stored_mode))`), add the location-options parsing. Note `initial` is already defined just above (`initial = kwargs.get('initial') or {}`):

```python
        # Build location choices from settings (mirrors instruction_modes)
        location_choices = None
        raw_locations = fs_config.get('location_options', '')
        if raw_locations:
            location_choices = [
                (loc.strip(), loc.strip())
                for loc in raw_locations.split('|')
                if loc.strip()
            ]

        # If editing existing data, ensure the stored location value is selectable
        stored_location = initial.get('location', '')
        if stored_location and location_choices:
            location_values = {c[0] for c in location_choices}
            if stored_location not in location_values:
                location_choices.append((stored_location, stored_location))
```

(b) In the `for field_name in TeachingSectionFieldSchema.get_available_field_names():` loop, where `extra_kwargs` is assembled, add a branch next to the existing `instruction_mode` branch:

```python
            extra_kwargs = {}
            if field_name == 'instruction_mode' and instruction_mode_choices:
                extra_kwargs['choices'] = instruction_mode_choices
            if field_name == 'location' and location_choices:
                extra_kwargs['choices'] = location_choices
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field.LocationFormWiringTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the whole new test module**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_location_field -v 2`
Expected: PASS (9 tests total across the 3 classes).

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/forms.py future_sections/tests/test_location_field.py
git commit -m "feat(location): drive teaching-form location dropdown from Available Locations setting"
```

---

## Task 4: Verify integration & no side effects

**Files:** none (verification only)

- [ ] **Step 1: Confirm there is no model migration to create**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py makemigrations future_sections`
Expected: `No changes detected in app 'future_sections'`.
(If — unexpectedly — a migration is generated, STOP: something added a model field that wasn't intended. Do not proceed; the section fields must remain JSON-stored.)

- [ ] **Step 2: Confirm no regressions in the submodule's existing tests**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests -v 1`
Expected: all existing tests + the new `test_location_field` tests pass.

- [ ] **Step 3: Manually verify the Settings UI and instructor form**

1. In the CE portal, open **Settings → Classes → Section Requests**. Confirm:
   - The "Teaching Form Fields" table now has a **Location** row (Visible / Required / Custom Label / Weight). Tick **Visible** for it and save.
   - The new **Locations** section shows an **Available Locations** text box. Enter e.g. `Main Campus|North High|Online` and save.
2. As an instructor (or via the CE "edit sections" modal), open the teaching/section form for a course. Confirm a **Location** dropdown appears with the three configured options (plus a leading blank).
3. Save a section with a location chosen; reopen and confirm the value is retained (it is stored in `FutureCourse.section_info`). Confirm it appears in the **Section Requests Export** CSV (the export auto-includes enabled fields).

- [ ] **Step 4: Confirm packaging is untouched**

No new files/dirs were added under `future_sections/future_sections/` beyond the test module, and `MANIFEST.in` already globs `future_sections/*`. Quick check:
```bash
cd /repos/ewu/webapp/future_sections
git status --short
```
Expected: only the four touched files were changed/added; no edits to `MANIFEST.in`, `setup.cfg`, or `setup.py`. The `submod-package-manifest` skill does not apply.

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch. The submodule's default branch is `main`; per repo flow, open a PR from `feat/configurable-location-field` (do not push/merge without confirmation). After the submodule change is released/tagged, the host tenant repos pick it up via their pinned submodule pointer / pip requirement.

---

## Self-Review

**Spec coverage:**
- "Add 'location' as a field" → Task 1 adds it to the schema (the single source of truth for available section fields); it becomes enable-able in the form config automatically. ✓
- "Allow the dropdown values to be customized in settings" → Task 2 adds the `location_options` setting; Task 3 feeds those values into the `location` dropdown. ✓

**Type/name consistency:** the setting key is `location_options` everywhere (settings field name, `fs_config.get('location_options')` in forms.py, and the test value). The schema field, the form field name, and the `teaching_form_config` `fields` entry are all `location`. `make_django_form_field`'s `choices` kwarg is the same one passed via `extra_kwargs['choices']`. Pipe (`|`) is the delimiter in both the help text and the parser — consistent with `instruction_modes`.

**No placeholders:** every code step shows the exact code; every run step shows the exact container command and expected result. No migration/packaging work is invented — both are explicitly verified as no-ops.
