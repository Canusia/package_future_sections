# Future Sections — New Section Fields and Drag-and-Drop Field Ordering

**Date:** 2026-08-04
**Status:** Approved, not yet implemented
**Package:** `future_sections` (pip-installed submodule, `Canusia/package-future_sections`)

## Goal

Add four new configurable per-section fields to the teaching form — `start_date`,
`end_date`, `assessment_upload`, and `new_teacher_email` — and replace the numeric
weight inputs in the CE settings field tables with drag-and-drop row reordering.

## Background

`future_sections` already has a schema-driven configurable field system:

- `schemas.py` — `TeachingSectionFieldSchema` is the single source of truth. Each
  field carries `default_label`, optional `default_help_text`, `widget_type`,
  `field_type`, and optional `choices` / `depends_on` in `json_schema_extra`.
- `forms.py:180` — `TeacherCourseSectionForm` generates every schema field
  dynamically through `make_django_form_field`. `syllabus` is *not* a schema
  field: it is a hardcoded `FileField` gated by a `show_syllabus` flag, whose
  saved URL lands in a separate hidden `file` key.
- `utils.py:380` — `build_sections_payload` uploads `form-<i>-syllabus` to
  `PrivateMediaStorage` and writes the URL into `cleaned['file']`.
- `settings/future_sections.py:660-805` — the CE settings page builds two HTML
  config tables (Field / Visible / Required / Custom Label / Weight), serialized
  into hidden JSON fields `teaching_form_config` and `add_teacher_form_config`.
- `staticfiles/future_sections/js/settings.js` — reads those tables, sorts the
  visible fields by weight (lighter first, unweighted last), and writes the
  resulting `fields` array into the hidden JSON.
- `templates/future_sections/teaching_course.html` — renders fields in
  `form_config.fields` order, with hardcoded blocks for the two existing
  dependent fields.
- `cis/staticfiles/js/field_weights.js` — an existing native HTML5 drag-and-drop
  row-reorder implementation for the student application field table. It is the
  behavioral precedent, but lives in a different package and cannot be imported.

Everything downstream — export headers (`FutureCourse.get_export_labels`),
display templates (`format_section_display`), settings help text
(`settings_help_text`), and `active_form_fields` validation — derives from
`get_available_field_names()`. New schema fields therefore propagate to all of
them with no additional edits.

## Decisions

1. **`assessment_upload` is a schema field, not a second hardcoded upload.** The
   schema learns a `file` widget type so the upload participates in the same
   visible/required/label/order configuration as every other field. This is the
   only arrangement in which the upload can be drag-reordered.
2. **`syllabus` is left alone.** It keeps its hardcoded `FileField`, its
   `show_syllabus` toggle, its `file` storage key, and its `{syllabus_link}`
   display placeholder, and continues to render after all configured fields. Two
   file mechanisms coexist for now. Migrating `syllabus` onto the schema would
   require a settings shim, a backfill of existing `section_info` rows, and
   placeholder compatibility work affecting every tenant with saved projections;
   it can follow later once the file widget is proven.
3. **`start_date` and `end_date` are independent fields**, each individually
   toggleable, labelable, and orderable — no `depends_on` relationship. Ordering
   between them is enforced by validation, not by field visibility.
4. **The weight column stays, readonly.** Drag renumbers the inputs; the stored
   JSON format is unchanged. Removing the column would leave two controls
   fighting over the same value or force a config-format migration.
5. **Both config tables get drag-and-drop** — "Teaching Form Fields" and "Add
   Teacher Form Fields" — via one generic module rather than two implementations.

## Design

### Schema (`schemas.py`)

Three new `widget_type` values handled in `make_django_form_field`:

- **`file`** → `forms.FileField(required=..., widget=ClearableFileInput)`. When
  the section already has a stored value, a "Download uploaded file" link is
  appended to the label, mirroring the syllabus treatment at `forms.py:317`.
- **`date`** → `forms.DateField` with
  `widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})` and
  `input_formats` accepting ISO. Paired with `field_type: "date"`.
- **`email`** → `forms.EmailField` with a `TextInput(type=email)` widget.

The `visible=False` branch gets matching cases. `date` and `email` fall through to
the existing `CharField` + `HiddenInput`. `file` renders as a hidden `CharField`
holding the stored URL, so a field that is hidden after data was saved never
destroys the upload.

Four new fields, declared after the existing ones:

| Field | `widget_type` | Default label | Notes |
|---|---|---|---|
| `start_date` | `date` | Start Date | |
| `end_date` | `date` | End Date | |
| `assessment_upload` | `file` | Assessment Upload | optional; never required by default |
| `new_teacher_email` | `email` | New Teacher Email | `depends_on: "teacher_changed"` |

### Upload plumbing (`utils.py:380`)

`build_sections_payload` currently performs a single hardcoded lookup for
`form-<i>-syllabus`. It gains a loop over schema fields whose
`widget_type == 'file'`:

- Check `request.FILES.get(f'form-{index}-{name}')`.
- On upload, save to `PrivateMediaStorage` under
  `future_section/{future_course.id}/{safe_name}` and write the resulting URL
  into `cleaned[name]` — the field's own key, not a separate one.
- With no new file posted, carry forward the previously stored URL from the
  hidden input rather than blanking it.

The existing syllabus branch is unchanged.

### Display (`schemas.py:format_section_display`)

- Values for `file`-type fields render as
  `<a href="<url>" target="_blank">{label}</a>` using the field's configured
  label as link text, instead of interpolating a raw URL.
- Values for `date`-type fields render in the project `m/d/Y` format rather than
  ISO.

### Validation (`forms.py`, `TeacherCourseSectionForm.clean`)

When `start_date` and `end_date` are both visible and both populated, an
`end_date` earlier than `start_date` raises a field error on `end_date`. Equal
dates pass. One-sided, empty, and hidden-field cases impose no constraint.

### Template (`teaching_course.html`)

The hardcoded `new_teacher_name` and `new_highschool_title` blocks — and the
`{% if field_name != 'new_teacher_name' and field_name != 'new_highschool_title' %}`
exclusion guard around the main loop — are removed. In their place, a
`dependent_fields` template tag takes the form and a parent field name and yields
every schema field whose `depends_on` matches that parent, rendered inside a
`dependent-field-wrapper` immediately after the parent.

The existing toggle JS keys off `data-depends-on` and works unchanged, so
`new_teacher_email` requires no template edit. The hardcoded `dependent_fields`
dict at `forms.py:257` is likewise replaced by a derivation from schema metadata.

### Drag-and-drop reordering

**New file:** `future_sections/staticfiles/future_sections/js/field_reorder.js` —
a self-contained module modeled on `cis/staticfiles/js/field_weights.js` but
owned by this package. It exposes `initFieldReorder(tableSelector, weightInputClass)`:

- Marks every non-disabled `<tbody>` row `draggable="true"` and prepends a grip
  cell (`<i class="fas fa-grip-vertical">`).
- Native `dragstart` / `dragover` / `drop` handlers reorder rows within their own
  table only; a guard compares the dragged row's table against the drop target's
  so the two config tables cannot cross-contaminate.
- On drop, renumbers every `weightInputClass` input from 0 upward in DOM order,
  then fires the `input` event that `settings.js` already listens on — so the
  existing `syncToHidden` serializes the new order with no change to its logic.
- "Always included" rows (Term, School, Course, Teacher) stay non-draggable and
  pinned at the top, matching `settings.js` unconditionally prepending `term` to
  `newFields`.

**`settings.js`:**

- New `applySavedOrder($ui, weights, inputClass)` helper, called during init for
  both tables. It sorts `<tbody>` rows by saved weight (unweighted last, stable
  within ties by current DOM order) and reinserts them. Without this the table
  renders in schema-declaration order and a saved order does not survive a page
  reload.
- Call `initFieldReorder` for `#teaching-form-config-ui` / `.tfc-weight` and
  `#add-teacher-form-config-ui` / `.atfc-weight` after init.

**`settings/future_sections.py`:** add a grip `<th>` to both table headers and a
grip `<td>` to each row; mark the weight `<input type="number">` `readonly`;
change the helper text from "Lighter weighted fields appear at the top of the
form" to a description of dragging.

The stored JSON format is untouched — `fields`, `required`, `labels`, `weights`,
`show_syllabus`, and `display_template` keep their current shapes. Existing
tenant configs load and render exactly as before, now in weight order.

## Testing

Django tests under `future_sections/tests/`, following the style of
`test_location_field.py`:

- **`test_field_widget_types.py`** — `make_django_form_field` returns the correct
  field class and widget for `file`, `date`, and `email` in both visible and
  hidden modes; a hidden `file` field yields a `CharField`, not a `FileField`.
- **`test_new_section_fields.py`** — the four new names appear in
  `get_available_field_names()`; each carries the expected metadata;
  `new_teacher_email` declares `depends_on: 'teacher_changed'`; enabling
  `teacher_changed` in config makes both dependents visible.
- **`test_date_validation.py`** — `end_date` before `start_date` errors; equal
  dates pass; one-sided and empty values pass; a config with the fields hidden
  never errors.
- **`test_file_field_payload.py`** — `build_sections_payload` stores an uploaded
  assessment file under the `assessment_upload` key, preserves an existing URL
  when no new file is posted, and leaves the syllabus path intact.
- **`test_section_display.py`** — `format_section_display` renders a file value
  as an anchor and a date value as `m/d/Y`.

The JS is not unit-tested — this package has no JS test harness. The reorder
module is verified manually on the CE settings page.

Run with:

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections
```

## Shipping

`future_sections` is pip-installed, so merging `dev` does not ship this change.
The sequence is: commit inside the submodule → push to
`Canusia/package-future_sections` → tag → bump the pin in
`webapp/requirements.txt` → `git add webapp/future_sections` in the host → merge.

The new static JS file means the `submod-package-manifest` skill must run before
tagging, to confirm `MANIFEST.in` / `setup.py` actually ship it.

No model migrations are involved — all state lives in the settings JSON and in
`FutureCourse.section_info`.

## Out of scope

- Migrating `syllabus` onto the schema `file` widget type (decision 2).
- Removing the weight column in favor of position-only ordering (decision 4).
- Backfilling or reformatting existing `section_info` rows.
