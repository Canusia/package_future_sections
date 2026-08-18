# Changelog

Releases are tagged `vYYYY.MAJOR.MINOR` on `Canusia/package_future_sections` and consumed by
each tenant through the `git+https://…@<tag>` pin in `webapp/requirements.txt`.

## Unreleased

### Changed

* **"Type of course" and "This is a:" are now Add Teacher fields.** Both selects moved out
  of Teaching Form Fields into the **Add Teacher Form Fields** card, where they get the
  usual Visible / Required / Custom Label / Weight controls. They are the questions asked
  when a *new* teacher is being added, and because `AddNewTeacherForm` subclasses the
  teaching form, driving them from `teaching_form_config` also put them on the ordinary
  section-request form with no way to separate the two. The plain teaching form no longer
  renders them at all, whatever its config says. Option sources
  (`course_types` / `course_request_types`), the hide-entirely-when-unconfigured rule and
  the keep-a-retired-stored-value-selectable rule are unchanged, and nothing about how the
  value is stored changed — still the same `section_info` JSON, still no migration.

  **Tenants that enabled either field in Teaching Form Fields must re-enable it under Add
  Teacher Form Fields**; the two configs are separate keys and the setting does not carry
  over.

* **The add-teacher course-list filter is now `offering_type`, not `course_type`.** It
  selects which course list the form offers (`pathways` / `cccl` / `facilitator`) and used
  to ride in the POST body under the same name as the new form field, so the user's answer
  ("Dual Credit") could be read as the filter. It is now read from the query string only.
  The legacy `course_type` query key is still accepted, so a browser holding a cached copy
  of the older JS keeps working.

### Fixed

* **The packaged tests now run in pip-only tenants.** Every test module spelled the nested
  `future_sections.future_sections.*` path, which only resolves where the package is
  checked out as an in-tree editable submodule; in a flat pip install 28 of 32 modules
  failed to import, so the suite that ships in the wheel gave those tenants nothing but
  noise and no upgrade signal. Modules now use relative imports, and the one `mock.patch`
  target that needs a string builds it from `PKG` in `future_sections/tests/__init__.py`,
  resolved once via `find_spec`. A guard test fails if the nested prefix reappears.
  (Canusia/package_future_sections#2)

* **Version metadata now matches the tag.** `setup.py` and `setup.cfg` still declared
  `2026.5.2` when v2026.6.0 was tagged, so the wheel built from that tag reported the older
  version. pip keys upgrades off the version string, meaning a tenant already on 2026.5.2
  saw no upgrade and silently kept the old code unless it was reinstalled with
  `--force-reinstall`. The v2026.6.0 tag is left as published; this release carries the
  same code with correct metadata.

## 2026.6.0

### Added

* **Two tenant-configurable selects on the Add Teacher form.** "Type of course"
  (`course_type`) and "This is a:" (`course_request_type`) join the existing configurable
  fields, so they appear in the Add Teacher Form Fields picker with the usual Visible /
  Required / Custom Label / Weight controls and are stored in the same `JSONField` as
  everything else — no migration.
* **Two settings to drive them**, under Course Types and Course Request Types, alongside
  Instruction Modes and Locations. Both are pipe-delimited and accept `value:Label` pairs,
  so an option can be reworded later without orphaning records that already store it. Only
  the first colon splits, meaning a label may contain a colon but a value may not. Values
  are capped at 1000 characters rather than the 500 used by Instruction Modes, because a
  realistic course-request label runs past 100 characters on its own.
* `parse_choice_list(raw, pairs=False)` in `forms.py`, shared by all four option-list
  settings, replacing two near-identical inline comprehensions.

### Changed

* Instruction Modes and Locations now parse through `parse_choice_list`. Their behaviour is
  unchanged: pair-splitting is **opt-in**, and both call it with the default. A plain label
  may legitimately contain a colon — `Hybrid: F2F and Online` is a real shape — and
  splitting it would have silently changed both the stored value and the displayed label
  for settings that already exist. They can adopt `pairs=True` later, deliberately.

### Upgrade notes

* **Nothing is required, and nothing changes until you configure it.** A field whose option
  list is empty is not rendered at all, regardless of its Visible/Required setting. Both new
  fields default to visible and required, so without that rule every tenant would inherit an
  empty required dropdown it could not satisfy.
* To adopt, set the option lists in Settings → Future Sections. They ship blank on purpose:
  seeding one tenant's course vocabulary into a shared package would push it to all of them.
* Prefer short stable values (`dual:Dual Credit`) over bare labels for these two fields. A
  record holding a value you later remove from the list keeps that value selectable, but it
  renders as the bare value, so slugs age better than prose.

## 2026.5.2

### Changed

* **The add-teacher campus filter now defaults to All Campuses.** Previously the field had no
  empty choice and preselected the alphabetically-first campus, so there was no way to see the
  whole catalogue at once. The campus list is also narrowed to campuses holding at least one
  selectable course, so a campus whose courses are all inactive or all marked unavailable no
  longer appears.
* The add-teacher course list now follows the same rule as the applicant course picker in
  `instructor_app`: active, `available_for_si` not an explicit "No", and campus matching **or
  unset**.

### Fixed

* **Courses with no campus are addable again.** The course list was scoped with a bare
  `filter(campus=campus)`, which excluded courses whose `campus` is NULL — an unset campus means
  "offered everywhere". At EWU that made 3 active courses unreachable through this form.
* **Courses explicitly marked unavailable to new instructors are no longer offered.** The form
  ignored `available_for_si` entirely, so a course CE staff had marked "No" was still addable.
  All "No" spellings are honoured (`'2'`, `'0'`, `False`, `'false'`, `'False'`) — the SIS
  importer writes the raw `isopen` value and `Course.add_or_update` replaces `meta` wholesale,
  so both the CE-form and SIS vocabularies occur in the wild.
* **`distinct('title')` is now deterministic.** Postgres `DISTINCT ON` keeps the first row per
  title in `ORDER BY` order, and the ordering had no tiebreak — so when two same-titled courses
  collided (newly reachable now that All Campuses is the default and campus-less courses are
  unioned in), which one survived was planner-dependent, and the section could be created
  against an arbitrary `Course` row. Ordering is now `title, campus__name, catalog_number`.

### Upgrade notes

* **Multi-campus tenants see a new default.** The campus dropdown opens on All Campuses rather
  than the first campus, and a campus with no selectable courses vanishes from the list —
  posting such a campus now fails field validation where it was previously accepted.
* Ship this together with `instructor_app` v2026.0.26 — that package governs what applicants may
  apply for, and the two rules are meant to agree. Shipping one alone leaves a tenant where a
  course is requestable but not applicable-for, or the reverse.

### Known issues

* `distinct('title')` still **collapses** genuinely distinct courses that share a title. At EWU,
  `SPAN 201`, `SPAN 202` and `SPAN 203` are all titled "INTERMEDIATE SPANISH & CULTURE" and
  appear as a single entry, so two of the three cannot be requested. This predates the release
  and is unchanged by it; only the choice of survivor is now deterministic.
