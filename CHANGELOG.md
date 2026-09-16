# Changelog

Releases are tagged `vYYYY.MAJOR.MINOR` on `Canusia/package_future_sections` and consumed by
each tenant through the `git+https://…@<tag>` pin in `webapp/requirements.txt`.

## 2026.12.0

### Added
- CE can **Skip** (kept in history), **Delete**, or **Add** a reviewer on a request's live review round from the Reviewers modal. Taking out the last undecided reviewer at the current stage moves the request to the next stage (emailing it), or marks it reviewed when nobody is left. Paused requests can be changed but are not advanced. (#5)

### Migrations
- `0008_sectionrequestreview_skipped`: `skipped` decision choice, `skipped_by` FK.

## 2026.11.0

### Changed

* **Reviewer Roles & Order is the only reviewer-role control.** The separate
  **Reviewer Roles** checkbox list is gone; `reviewer_roles` is now hidden and
  derived on save from the roles the card includes, in weight order. Rows are
  drag-reorderable like **Teaching Form Fields** (weights renumber on drop; type
  the same weight on two roles to keep them in one stage), and render in saved
  order. **Assign a mentor during review?** and the mentor role now sit directly
  below the card.
* **Instruction Modes and Locations take `value:Label` pairs**, like Course
  Request Types, and stored values render as their labels in the section display
  and export. A plain token is still its own value and label. **Upgrade note:** an
  existing option whose label contains a colon (e.g. `Hybrid: F2F and Online`)
  now splits at the first colon — reword it or prefix a value
  (`hybrid:Hybrid: F2F and Online`) before upgrading.

## 2026.10.0

### Added

* **Weighted sequential review.** A new **Reviewer Roles & Order** settings card
  (ported from instructor_app's `reviewer_role_config`) gives each reviewer role
  a weight. Opening a review round still snapshots every qualifying reviewer —
  the snapshot remains the authority on who may decide — but each row now
  records the weight its role carried, and rows sharing a weight form a
  **stage**. Only the current stage is notified; an approval that completes a
  stage notifies the next one; approving the last stage marks the request
  `reviewed`. **Roles sharing one weight behave exactly like the previous
  parallel quorum** for who may decide and in what order, which is also how
  existing rows are backfilled (`weight` defaults to 0). A tenant that never
  opens the new card still sees two changes to the review flow: reviewers get
  a stage-open email the moment the round opens (see below), and a denial now
  pauses the request instead of completing the round outright (see "A denial
  pauses the request" below). The CE index badge is unaffected either way —
  it suppresses "Stage 0" as meaningless for a tenant with one undifferentiated
  stage, showing "Paused — awaiting staff" only if the request is paused.
* **A denial pauses the request.** `FutureCourse.review_paused_on` is set, the
  addresses in the new **Escalation Recipients** setting are emailed (with their
  own subject/message templates), and all automatic notification stops — no
  later reviewer is told. Pause is deliberately not a fourth status: the request
  stays `pending_review`, so it stays locked to the school and every badge,
  filter and export keeps working.
* **Notify next stage.** A CE action (bulk, and a "Notify reviewers" button in
  the reviewers modal on a paused request) that clears the pause and re-notifies
  whoever is currently due — the same stage, if a peer is still undecided, or
  the next one once the stage is complete — leaving the denial on the record as
  history. Resetting to `submitted` also clears the pause.
* The reviewers modal marks whose turn it is ("Current stage"); the CE index
  badge shows the current stage ("Stage N", suppressed when N is 0 — a
  no-order tenant's only stage) or "Paused — awaiting staff"; a new
  **Paused (not approved)** option joins the review filter; the Future Classes
  export gains Current Stage and Review Paused columns.

### Changed

* **A `not_approved` decision no longer completes the round.** It previously
  advanced the request to `reviewed` once every slot was filled, regardless of
  verdict. It now pauses the request instead, and the escalation recipients are
  emailed; no later-stage reviewer is notified until staff resume it.
* **A reviewer can no longer revise their verdict after their stage closes.**
  `record_decision` now refuses a decision from anyone outside the current
  stage, raising the existing `NotAReviewerError` (the view renders this as a
  404). This is correct for a sequential model but narrows what a reviewer
  could previously do — under the old parallel quorum every open slot could be
  decided in any order.
* **Reviewers now receive an email the moment their stage opens** (opening a
  round, or an approval that advances to the next stage), reusing the
  `review_notification_*` template. Previously they learned only via the
  date-gated cron reminder or CE's manual per-reviewer chase. This applies even
  to a tenant that sets no order, because one undifferentiated stage still
  opens at round-open.
* The reviewer reminder cron and CE's per-reviewer "Send reminder" are both
  scoped to the current stage, and the cron skips paused requests. CE can still
  chase a current-stage reviewer while paused — that is the manual path.
* A reviewer's Pending queue shows a request only once their stage opens; a
  paused request is in nobody's queue.

### Fixed

* **A multi-line `{# #}` comment in `teaching_course.html` rendered into the
  page.** Django's `{# #}` is single-line only: a `{#` whose `#}` sits on a
  later line is not a comment, so the template engine emitted all three lines
  verbatim and the implementation note was visible inside the teaching form to
  every instructor and school administrator. Now `{% comment %}`. A new
  `tests/test_template_comments.py` statically scans every shipped template and
  fails on any `{#` left unclosed on its line, so the mistake cannot ship again.

### Upgrading

* **Set Review Escalation Recipients before taking this release.** The
  `review_escalation_recipients` setting (Settings → Section Requests →
  Review Escalation) is seeded only by the settings form's `install()`,
  which runs on first registration — an already-installed tenant's stored
  setting has no value for this key. Under this release a denial pauses the
  request rather than completing the round, and the pause email goes to
  whatever `review_escalation_recipients` resolves to. With it unset, a
  denial on any tenant (including one that never opens the new **Reviewer
  Roles & Order** card, where every row is weight 0) pauses the request and
  sends nobody anything — `notify_review_escalation` logs a warning, but no
  reviewer or staff member is chased. The pause itself is still recorded and
  visible: the request stays `pending_review` and shows the "Paused —
  awaiting staff" badge on the CE index, and it is recoverable at any time
  via the reviewers modal's "Notify reviewers" action or bulk **Mark as
  Submitted** — but until a CE happens to notice the badge, it sits idle.
  Configure the recipients list before upgrading so the escalation email
  fires on the first denial after the upgrade.

## 2026.9.0

### Added

* **Two configurable uploads on the Add Teacher form.** `new_teacher_syllabus`
  ("Syllabus") and `new_teacher_class_assessment` ("Class Assessment") join the
  **Add Teacher Form Fields** settings card with the usual Visible / Required /
  Custom Label / drag-order controls. They are deliberately separate from the
  teaching form's `syllabus` and `assessment_upload` — a tenant can collect
  documents in both places without the two sharing a storage key or a
  configuration entry. Each upload is stored under its own key on the section
  and renders as a link through the `{new_teacher_syllabus}` /
  `{new_teacher_class_assessment}` Display Template placeholders. They are not
  added to the Future Classes export, whose columns follow the teaching config.

### Fixed

* **Answers collected only on the Add Teacher form are no longer erased by a
  teaching save.** The teaching template renders only the fields listed in
  `teaching_form_config`, so an add-teacher-only answer was never posted back
  and `build_section_info_from_formset` wrote `''` over it: an upload or a
  course-type selection disappeared the first time anyone edited the teaching
  form for that course. Those fields now ride along as hidden inputs (new
  `add_teacher_only_fields` template tag). Affected `course_type` and
  `course_request_type` in every release since they were introduced.

## 2026.8.0

### Added

* **Multi-reviewer review quorum.** A third status, `pending_review`, now sits between
  `submitted` and `reviewed`. CE marks a batch pending review, which snapshots the
  qualifying reviewers (from **Reviewer Roles**) as rows in a new `SectionRequestReview`
  model — one per reviewer per round — and increments `FutureCourse.review_round`. Each
  snapshot reviewer posts their own decision; once every slot in the live round is filled,
  the request advances to `reviewed` automatically. **`reviewed` carries no verdict** — it
  means everyone has weighed in, and CE still interprets the individual decisions. CE can
  reset a request back to `submitted`, which unlocks it and leaves the finished round's rows
  in place as history; the next round starts at `review_round + 1`.
* **The request is locked against high school administrator and instructor edits** while
  `pending_review` or `reviewed` (`FutureCourse.LOCKED_STATUSES`). Enforced server-side via
  `assert_editable()` on all four school-facing write endpoints (the teaching formset save,
  two API actions, and the add-teacher form), and mirrored in the school-facing table, which
  hides the edit controls on a locked row. CE is never locked out.
* **Reviewer visibility is now governed by snapshot membership**, not live
  `CourseAdministrator` rows: a user sees a request only if they hold a `SectionRequestReview`
  row on it. Deactivating a reviewer mid-round no longer strands the request (the remaining
  reviewers still complete the round), and adding a reviewer mid-round does not pull them
  into a round already in progress — they qualify starting with the next one.
* **CE index quorum UI.** The progress badge on each request shows "N of M decided"; a
  three-way status badge replaces the old binary one. Clicking the badge opens a **Reviewers
  modal** listing every snapshot reviewer with their qualifying role, decision (or
  "Awaiting"), decision date and comment, plus a per-reviewer **Send reminder** action for
  anyone still undecided.
* **Pending Review Notifications.** A new settings block — `review_notification_dates`,
  `review_notification_cron`, `review_notification_subject`, `review_notification_message` —
  drives a `notify_pending_reviews` cron/management command that emails each reviewer with an
  outstanding decision exactly once, listing everything they owe. A **Review Notification
  History** tab on the CE index shows the send log, sibling to the existing Notification
  History tab.
* The CSV export's review columns (round, reviewers, decisions, mentors, decided-on,
  comments) now list every snapshot reviewer for the live round, one semicolon-joined cell
  per field, padded so position *k* always means reviewer *k* even before everyone has
  decided.

### Changed

* **Add Teacher now saves every field the tenant has configured**, not a hardcoded four-key
  subset. `AddNewTeacherForm.save()` previously kept only `term`, `term_name` and
  `estimated_enrollment` regardless of what `teaching_form_config` rendered, so class period,
  the teacher-changed group, dates and file uploads were validated and then silently
  discarded. It now iterates `TeachingSectionFieldSchema.get_available_field_names()`, the
  same authority the form renders from.
* **`course_type` / `course_request_type` answers are persisted and displayed as labels.**
  Stored choice codes (`dual`) now render as their configured labels (`Dual Credit`) in both
  the section display and the CSV export, via a shared `choice_labels` map built from the
  `course_types` / `course_request_types` settings.
* **The add-teacher form's show/hide pairs are now derived from the schema's `depends_on`
  metadata** instead of a hardcoded two-entry list, which fixes `new_teacher_email` never
  hiding when "Did the teacher change?" is No.
* The CSV export's column set is now the union of the teaching-form config and the
  add-teacher-only fields (`FutureCourse._export_field_config()`), so add-teacher-only
  answers can appear as export columns, which was previously impossible.
* DEBUG-mode test-mail redirection (`notify_pending_section_requests`,
  `notify_pending_reviews`, and the on-demand `send_review_reminder`) now routes through the
  tenant's own `testers` setting instead of a hardcoded personal address baked into the
  shared package. If DEBUG is on and `testers` is blank, nothing is sent and the gap is
  recorded rather than silently falling through to the real recipient.

### Fixed

* The on-demand `send_review_reminder` endpoint is POST-only and CSRF-protected
  (PT-33-style), so a cross-site GET or link-prefetch can no longer trigger a real email.
* A decision can no longer be posted to a request outside its live `pending_review` round —
  closes a gap where a stale POST could re-lock a request CE had just reset, or land on an
  already-`reviewed` request.
* Re-selecting an already-`pending_review` or `reviewed` request for "mark as pending review"
  no longer opens a second round and orphans the first; it is skipped and reported
  separately from the no-qualifying-reviewer case. The action also refuses outright when
  review is not required for the tenant.
* "Mark as reviewed" now refuses (rather than force-closes) a request still live in
  `pending_review`, naming it in the response — reset remains the only way out of a live
  round.
* A reviewer's own decision status no longer shows a stale answer from a round that was
  reset and reopened; the lookup is scoped to the live round while a request is
  `pending_review`.

### Upgrade notes

* **Three migrations ship in this release:**
  * `0004_futurecourse_review_round_alter_futurecourse_status` — adds the `pending_review`
    status choice and `review_round` field.
  * `0005_sectionrequestreview` — creates the `SectionRequestReview` model.
  * `0006_migrate_legacy_faculty_review` — a data migration that converts any existing
    `section_info['faculty_review']` (including its `history` list) into
    `SectionRequestReview` rows. **Its reverse is a deliberate no-op**: the source JSON is
    never deleted, and the table can hold rows written by the live quorum workflow by the
    time anyone reverses it, so an indiscriminate delete would destroy live history along
    with the legacy conversion.
* **A tenant with review switched off is unaffected**: the review pages 404, the CE review
  controls are hidden, and the new `pending_review` status is never reached.
* **`highschool_admin >= 0.0.12` now declares a dependency on `future-sections >= 2026.8.0`.**
  Upgrade `future_sections` first, or the pin resolution order can leave a tenant on an
  incompatible pair.
* Version metadata (`setup.py` / `setup.cfg`) is bumped to `2026.8.0` in the same commit as
  the quorum work, so pip picks up the upgrade without `--force-reinstall`.

## 2026.7.0

### Added

* **A `section_number` field** on the teaching form, off by default. Enable it under
  Teaching Form Fields to give each pre-populated row a value that tells it apart from its
  siblings in the same term.

### Changed

* **"Enter Course Details" now pre-populates one row per previous-year section**, not one
  per term. A teacher who taught the same course twice in a term used to get a single row
  while the "Previous Year" column beside it counted two, and the admin had to notice and
  re-add the rest by hand. Rows are ordered by term then section number, so the order no
  longer varies between requests.

  Each row carries the mapped term plus whichever of `section_number`,
  `highschool_course_name`, `class_period` (from the prior section's `period_time`) and
  `instruction_mode` the tenant has made visible. Hidden fields are deliberately not
  pre-filled — their widgets still post, so a value copied into one would be stored without
  anyone seeing it. `location` is never copied: `ClassSection.location` is a foreign key to
  the SIS Location table while the form's select holds strings from the `location_options`
  setting, and the two vocabularies do not match.

  **A tenant whose teachers run several sections of a course in one term should enable
  Section Number**, otherwise the extra rows arrive identical and there is nothing to edit
  them against.

* The formset's unreachable "Terms must be unique" branch is deleted. It was dead code
  (`duplicates` was hardcoded `False`), and same-term rows are now the normal case, so
  anyone "fixing" it by uncommenting the check would have broken pre-population silently.

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
  `--force-reinstall`. The v2026.6.0 tag is left as published; upgrading to this release is
  the way to pick up the 2026.6.0 work.

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
