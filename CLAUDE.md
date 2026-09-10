# CLAUDE.md - future_sections

## Overview

Django app managing instructor section projections for upcoming academic years. High schools forecast course offerings by collecting information from instructors about which courses they plan to teach. Serves three user roles: CE Staff (full access), HS Admins (their schools), Instructors (their own courses).

## Package Structure

Git submodule with dual app config pattern:
- **Production:** `FutureSectionsConfig` (`future_sections.apps.FutureSectionsConfig`)
- **Development:** `DevFutureSectionsConfig` (`future_sections.future_sections.apps.DevFutureSectionsConfig`)

Settings key: `cis_future_sections` in the `Setting` model.

## Models (`models.py`)

- **FutureProjection** - Tracks a high school's overall survey progress. Unique on `(academic_year, highschool)`. Meta JSON stores confirmation status and history.
- **FutureCourse** - Tracks an instructor's intention to teach a course. Unique on `(teacher_course, academic_year)`. `section_info` JSON stores `{teaching: 'yes'/'no', sections: [...]}`. Has `status` field (`submitted`/`pending_review`/`reviewed`) with `FieldTracker` for signal-based email notifications. `pending_review` and `reviewed` are the locked statuses (`LOCKED_STATUSES`): while in either, the high school administrator and instructor may no longer edit the request — see `utils.assert_editable`. `review_round` tracks the live review round; reviewer decisions live in `SectionRequestReview` rows, not in `section_info`. `review_paused_on` (and the `is_review_paused` property) is set when a reviewer denies a request — see "Review flow: rounds, stages and pause" below. Can create `TeacherApplication` via `create_teacher_application()`.
- **FutureSection** - Legacy per-section model. `FutureCourse.section_info` now stores primary data, but this model is still used in CE portal deletion and exports.
- **SectionRequestReview** (`review/helpers.py` operates on it) - One reviewer's slot on one round of review for one section request. Unique on `(future_course, reviewer, round)`. `role` and `weight` are copied from the qualifying `CourseAdministrator` at snapshot time (`qualifying_reviewers()`), so later role/weight changes never strand or reshuffle a live round. `decision` (`''`/`approved`/`not_approved`), `comment`, `mentor`, `decided_on` are filled in by `record_decision()`. Ordered `('round', 'weight', 'created_on')`.

All FKs to cis models use explicit `related_name` with `fs_` prefix (e.g., `fs_futurecourse_set`).

## Review flow: rounds, stages and pause (`review/helpers.py`)

- **Round vs. stage.** `open_review_round()` snapshots every qualifying reviewer as `SectionRequestReview` rows for one `review_round`, in one shot — that snapshot is the fixed authority on who may decide. Within a round, rows sharing a `weight` are one **stage**: `current_stage()` is the lowest weight with an undecided row. `weight` comes from the `reviewer_role_config` setting (`{role: weight}`, edited via the **Reviewer Roles & Order** settings card, ported from instructor_app); a role the config omits, or an absent/unparsable config, weighs 0 — every row lands in one stage, i.e. exactly the pre-sequential parallel-quorum behaviour. A user holding two qualifying roles is snapshotted once, under the lower-weight role (`qualifying_reviewers()`).
- **Notification is stage-scoped, not round-scoped.** Opening a round, and every stage-completing approval (`advance_or_finish()`), notifies only the current stage's undecided rows (`_notify_current_stage()` → `FutureCourse.notify_review_stage()`, reusing the `review_notification_*` email template). `pending_for(user)` (a reviewer's queue) and both reminder paths — the date-gated cron and CE's manual per-reviewer "Send reminder" — are likewise scoped to the current stage via `stage_rows()`/a correlated `Exists`, not the whole round: a later-stage reviewer sees the request in `visible_future_courses_for()` but not in their queue until their stage opens.
- **`record_decision()` only accepts a decision from the current stage.** A row whose `weight != current_stage(future_course)` raises `NotAReviewerError` (rendered by the view as a 404) — a reviewer cannot revise a verdict after their stage has closed, which the pre-sequential parallel quorum allowed (any open slot, any order).
- **Pause is not a fourth status.** A `not_approved` decision sets `FutureCourse.review_paused_on` (via `record_decision`) instead of letting the round complete, and emails `review_escalation_recipients` (`_escalate_denial()` → `FutureCourse.notify_review_escalation()`). The request stays `pending_review`, so the school-lock, badges, filters (a `paused` option) and export are unaffected — only automatic notification stops. `advance_or_finish()` is the single choke point for every status transition and refuses to act while `is_review_paused` is true, so a stage peer's approval after somebody's denial cannot complete the round out from under the pause.
- **`resume_review()`** clears the pause and calls `advance_or_finish()`, so it re-notifies whichever stage is *actually* current: the denier's own stage again if a peer there is still undecided, or the following stage once that stage is complete. It does not always advance to a new stage — the CE "Notify next stage" action and its button are deliberately labelled "Notify reviewers" for this reason. `reset_review()` (back to `submitted`) also clears the pause; history rows from the finished round are left untouched.
- **Backward compatibility:** every pre-existing `SectionRequestReview` row defaults `weight` to 0, so an unmigrated tenant (or one that never opens the new settings card) has exactly one stage — the parallel quorum behaves identically, except that opening a round now also emails that one stage immediately rather than only via the cron/manual reminder.

## Key Dependencies

- **cis models:** `Teacher`, `TeacherCourseCertificate`, `TeacherHighSchool`, `HSAdministrator`, `HSAdministratorPosition`, `HighSchool`, `AcademicYear`, `Term`, `Course`, `Setting`, `CronTab`, `CronLog`
- **instructor_app models:** `TeacherApplication`, `ApplicantSchoolCourse`, `ApplicationUpload` (used in `FutureCourse.create_teacher_application()`)
- **cis utilities:** `user_has_highschool_admin_role()`, `user_has_instructor_role()`, `PrivateMediaStorage`, `cis/email.html` template

## URL Namespaces

| Namespace | Path | Auth |
|-----------|------|------|
| `future_sections` | `/future_sections/` | None (base) |
| `future_sections_highschool_admin` | `/highschool_admin/future_sections/` | HS Admin |
| `future_sections_instructor` | `/instructor/future_sections/` | Instructor |
| `future_sections_ce` | `/ce/future_sections/` | CE Staff |

## Views Architecture

- **`views/api.py`** - `FutureSectionsActionViewSet` (mark teaching/not teaching, add teacher, confirm sections/admins), `CourseRequestViewSet`, `AdminPositionViewSet`. Role-aware via `utils.py` helpers.
- **`views/pages.py`** - `FutureSectionsPageView` (unified CBV for HS Admin and Instructor).
- **`views/ce.py`** - CE portal: index, settings, bulk actions, AJAX dispatcher, ad-hoc reminders.
- **`views/ce_api.py`** - CE API: `FutureClassSectionViewSet`, `FutureProjectionViewSet`, `PendingFutureClassSectionViewSet`, `NotificationLogViewSet`.

## Forms (`forms.py`)

- `TeacherCourseSectionForm` - Dynamic fields from `teaching_form_config` JSON via `TeachingSectionFieldSchema`.
- `AddNewTeacherForm` - Extends `TeacherCourseSectionForm`, adds teacher/school/course selection. Has `add_teacher_form_config` support.
- `ConfirmHighSchoolAdministratorsForm` / `ConfirmClassSectionsForm` - Confirmation forms with conditional validation based on settings.
- `HSAdministratorPositionForm` - Assign admin to position, supports new admin creation.

## Schema System (`schemas.py`)

`TeachingSectionFieldSchema` (Pydantic) is the single source of truth for configurable teaching form fields. Defines available field names, default labels, widget types, and provides:
- `make_django_form_field()` - Generates Django form fields
- `get_export_labels()` - Labels for CSV exports
- `format_section_display()` - Renders section display from template

Available fields (all 24 declared on the schema, in declaration order): `estimated_enrollment`, `class_period`, `location`, `instruction_mode`, `course_type`, `course_request_type`, `section_number`, `highschool_course_name`, `number_of_sections`, `full_year`, `trimester`, `fall_only`, `spring_only`, `notes`, `teacher_changed`, `new_teacher_name`, `highschool_title_changed`, `new_highschool_title`, `start_date`, `end_date`, `assessment_upload`, `new_teacher_email`, `new_teacher_syllabus`, `new_teacher_class_assessment`.

Four of these — `course_type`, `course_request_type`, `new_teacher_syllabus`, and
`new_teacher_class_assessment` — are declared on the same schema (so their values ride in
the same `section_info` JSON) but are never asked on the ordinary teaching form at all:
they are `TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS` (the two course-type selects
plus the two new-teacher uploads), configured under **Add Teacher Form Fields** and
rendered only by `AddNewTeacherForm` — `TeacherCourseSectionForm` always hides them.

`new_teacher_syllabus` and `new_teacher_class_assessment` are file fields
(`widget_type: file`), deliberately separate from the teaching form's own `syllabus` and
`assessment_upload` — a tenant can collect documents on both forms without the two sharing a
storage key. `AddNewTeacherForm` cannot simply un-hide the parent's fields for these: the
parent (`TeacherCourseSectionForm.__init__`) always builds every `ADD_TEACHER_ONLY_FIELDS`
entry as a hidden, non-required `CharField` regardless of type, and assigning a widget to an
existing field cannot turn a `CharField` into a `FileField`. `AddNewTeacherForm` instead
rebuilds each add-teacher-only file field from scratch via
`TeachingSectionFieldSchema.make_django_form_field()`, keyed off `add_teacher_form_config`
(same pattern it already used for the `course_type` / `course_request_type` selects).
Replacing an existing dict key preserves its position, so drag-configured field order
survives the rebuild.

Because `TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS` are excluded from
`teaching_form_config['fields']`, the teaching template's main render loop never emits them —
so nothing posts their value back on an ordinary teaching-form save, and
`build_section_info_from_formset` used to overwrite them with `''`. They must be rendered as
hidden inputs on the teaching form via the `add_teacher_only_fields` template tag
(`templatetags/future_sections_tags.py`) so their stored value rides along on every save;
skipping this silently erases add-teacher-only answers (including `course_type` and
`course_request_type`) the first time anyone edits the teaching form for that course.

## Releasing

Releases are tag-driven (`vYYYY.MAJOR.MINOR`), but the metadata is not decorative: **bump
`version` in `setup.py` and `setup.cfg` to the tag you are about to cut, in the commit you
tag**, and add the CHANGELOG entry there too. pip keys upgrades off that string, so a tag
whose metadata still names the previous version reads as already satisfied and tenants
silently keep the old code — v2026.6.0 shipped declaring `2026.5.2` and no tenant on
2026.5.2 could pick it up without `--force-reinstall`. Then bump each tenant's
`webapp/requirements.txt` pin and, where this is a submodule, the submodule pointer.

## Tests

The suite ships inside the wheel and runs in both deployment shapes, so no test module may
spell out `future_sections.future_sections.*`. Use relative imports, or `PKG` from
`future_sections/tests/__init__.py` where a string is required (e.g. `mock.patch`).
`test_no_hardcoded_package_prefix.py` enforces this.

Two guard tests scan files on disk rather than exercising behaviour, so they cover what no
other test renders or imports:

- `test_no_hardcoded_package_prefix.py` — no test module may spell out the nested path.
- `test_template_comments.py` — no shipped template may open a `{#` it does not close on the
  same line. Django's `{# #}` is **single-line only**: a multi-line one is not a comment at
  all, and the engine renders the text into the page (it shipped once in
  `teaching_course.html`, leaking three lines of notes into the teaching form). Use
  `{% comment %}` / `{% endcomment %}` for anything longer than one line.

Keep both when adding files: a new template or test module is covered automatically, which is
the point of scanning the tree instead of listing cases.

## Settings Form (`settings/future_sections.py`)

Large Django form with sections: General, Portal Messages, School Personnel, Course & Instructor Configuration, Form Configuration (visual UI), Section Request Review, Review Escalation, Reviewed Email, Pending Notifications, Confirmation Email. JS in `staticfiles/future_sections/js/settings.js` handles conditional toggles and form config UIs.

The **Section Request Review** section's `reviewer_role_config` is a hidden `CharField` (JSON `{role: weight}`) driven by the **Reviewer Roles & Order** card, built inline in `future_sections.py` (not `settings.js`). On first load, when no config is saved, the card seeds itself from the existing `reviewer_roles` checkboxes at weight 1 (one stage); saving keeps `reviewer_roles` (still "which roles may review" everywhere else) in sync with the card's inclusions. The **Review Escalation** section's `review_escalation_recipients` (comma-separated staff emails, no role-derived audience) plus `review_escalation_subject`/`review_escalation_message` control the denial email — see "Review flow" above.

## Signals (`signals.py`)

`future_course_status_changed` - `pre_save` on `FutureCourse`. Sends email when status changes to `reviewed` (if enabled). Uses `FieldTracker`. **Note:** Bulk `QuerySet.update()` bypasses this signal.

## Management Commands

- `migrate_future_sections_data` - Migrates data from old cis tables. Supports `--execute`, `--clear`, `--verify`.
- `notify_pending_section_requests` - Sends reminder emails to HS admins. Checks `pending_notification_dates` setting. Logs to `CronLog`.

## Reports (`reports/`)

- `future_classes` - Section Requests Export (dynamic fields from teaching_form_config). Includes eight review columns per `_faculty_review_cells()` (round, current stage weight, "Yes"/"" for paused, then reviewer/decision/mentor/decided-on/comment joined with `; `), headed **Current Stage** and **Review Paused** among others.
- `pending_future_classes_courses` - Pending requests by course
- `pending_future_classes` - Pending requests by HS admin

## Permissions (`permissions.py`)

`IsHSAdminOrInstructor`, `IsHSAdminOnly`, `IsInstructorOnly`, `CanAccessCourseRequest` (object-level certificate ownership check).

## Static Files

Located in `staticfiles/future_sections/js/`. Must be registered in `STATICFILES_DIRS` via `get_package_path()`.

## Important Patterns

- Role detection uses `cis.utils.user_has_highschool_admin_role()` / `user_has_instructor_role()`
- `utils.py` provides shared helpers: `get_fs_config()`, `get_user_context()`, `validate_certificate_access()`, `get_or_create_future_projection()`, `add_history_entry()`
- Emails use Django `Template` + `Context` with `cis/email.html` wrapper and `mailer.send_html_mail()`
- DEBUG mode redirects emails to the tenant's `testers` setting (comma-separated) via `route_notification_recipients`. With `DEBUG` on and `testers` empty, nothing is sent and the attempt is recorded as skipped — it never falls through to the real recipient. Note several older call sites still hardcode a redirect address; only the notifiers were converted in 2026.8.0.
- Settings registered via `CONFIGURATORS` in `apps.py`, reports via `REPORTS`
