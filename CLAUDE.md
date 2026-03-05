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
- **FutureCourse** - Tracks an instructor's intention to teach a course. Unique on `(teacher_course, academic_year)`. `section_info` JSON stores `{teaching: 'yes'/'no', sections: [...]}`. Has `status` field (`submitted`/`reviewed`) with `FieldTracker` for signal-based email notifications. Can create `TeacherApplication` via `create_teacher_application()`.
- **FutureSection** - Legacy per-section model. `FutureCourse.section_info` now stores primary data, but this model is still used in CE portal deletion and exports.

All FKs to cis models use explicit `related_name` with `fs_` prefix (e.g., `fs_futurecourse_set`).

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

Available fields: `estimated_enrollment`, `class_period`, `instruction_mode`, `highschool_course_name`, `number_of_sections`, `full_year`, `trimester`, `fall_only`, `spring_only`, `notes`, `teacher_changed`.

## Settings Form (`settings/future_sections.py`)

Large Django form with sections: General, Portal Messages, School Personnel, Course & Instructor Configuration, Form Configuration (visual UI), Reviewed Email, Pending Notifications, Confirmation Email. JS in `staticfiles/future_sections/js/settings.js` handles conditional toggles and form config UIs.

## Signals (`signals.py`)

`future_course_status_changed` - `pre_save` on `FutureCourse`. Sends email when status changes to `reviewed` (if enabled). Uses `FieldTracker`. **Note:** Bulk `QuerySet.update()` bypasses this signal.

## Management Commands

- `migrate_future_sections_data` - Migrates data from old cis tables. Supports `--execute`, `--clear`, `--verify`.
- `notify_pending_section_requests` - Sends reminder emails to HS admins. Checks `pending_notification_dates` setting. Logs to `CronLog`.

## Reports (`reports/`)

- `future_classes` - Section Requests Export (dynamic fields from teaching_form_config)
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
- DEBUG mode redirects all emails to test address
- Settings registered via `CONFIGURATORS` in `apps.py`, reports via `REPORTS`
