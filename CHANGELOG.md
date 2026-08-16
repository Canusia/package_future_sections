# Changelog

Releases are tagged `vYYYY.MAJOR.MINOR` on `Canusia/package_future_sections` and consumed by
each tenant through the `git+https://…@<tag>` pin in `webapp/requirements.txt`.

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
