# Future Sections App

The `future_sections` app manages future course section requests for high school administrators and instructors. It provides a unified interface for both user roles with role-aware permissions.

## Installation

### 1. Add to INSTALLED_APPS

In your `settings.py`, add `future_sections` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'future_sections',
]
```

### 2. Run Migrations

```bash
python manage.py migrate future_sections
```

### 3. Register Settings and Reports

```bash
python manage.py register_settings
python manage.py register_reports
```

### 4. Include URLs

In your main `urls.py` (e.g., `myce/urls.py`), add the URL configurations:

```python
from django.urls import path, include

urlpatterns = [
    # ... other URLs

    # Portal-specific URLs
    path('highschool_admin/future_sections/', include('future_sections.urls.highschool_admin')),
    path('instructor/future_sections/', include('future_sections.urls.instructor')),
    path('ce/future_sections/', include('future_sections.urls.ce')),

    # Shared API URLs
    path('future_sections/', include('future_sections.urls')),
]
```

### 5. Load Initial Data (Optional)

If you have existing FutureCourse data from a legacy system, you can migrate it using:

```bash
python manage.py migrate_future_sections_data
```

#### 5.1

Add this to header-includes.html

<!-- Flatpickr for multi-date selection -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>

This command loads existing data from the old `cis_futurecourse` table into the new models.

### 6. Configure Settings

Navigate to **CE Portal → Settings → Classes → Section Requests** to configure:

- **Academic Year**: Select the active academic year for section requests
- **Previous Academic Year**: For comparison display of last year's offerings
- **Survey Window**: Starting and ending dates for the submission window
- **Course Status Filter**: Which course statuses to include
- **Teacher Course Status Filter**: Which teacher course certificate statuses to include
- **HS Admin Roles to Verify**: Roles shown in the personnel verification step
- **Allow New Teacher Creation**: Whether HS admins can add new instructors
- **Teaching Form Configuration**: JSON config for the section request form fields
- **Add Teacher Form Configuration**: JSON config for labels/help text on the add-teacher form
- **UI Messages**: Welcome message, window closed message, teaching/add teacher/edit role instructions
- **Review Notification**: Enable/disable email notifications when requests are reviewed
- **Pending Notifications**: Dates, cron schedule, roles, and email template for pending reminders
- **Confirmation Email**: Subject and template for post-submission confirmation emails

## Dependencies

The app depends on these Django apps:
- `cis` - Core models (Course, Teacher, HighSchool, etc.)
- `setting` - Settings framework
- `report` - Reporting framework

Python packages:
- `django-crispy-forms` - Form rendering
- `djangorestframework` - API endpoints
- `model-utils` - FieldTracker for change detection

## Features

- Course section request management
- Teaching status tracking (teaching/not teaching)
- School personnel management
- Configurable form fields via JSON settings
- Section display formatting via templates

## URL Structure

### Portal-Specific URLs

The app provides URL configurations for each portal:

```python
# In myce/urls.py
path('highschool_admin/future_sections/', include('future_sections.urls.highschool_admin')),
path('instructor/future_sections/', include('future_sections.urls.instructor')),
path('ce/future_sections/', include('future_sections.urls.ce')),
```

**High School Admin Portal:**
- `/highschool_admin/future_sections/` - Main page
- `/highschool_admin/future_sections/api/...` - API endpoints

**Instructor Portal:**
- `/instructor/future_sections/` - Main page
- `/instructor/future_sections/api/...` - API endpoints

**CE Admin Portal:**
- `/ce/future_sections/` - Main page (Course Requests dashboard)
- `/ce/future_sections/settings/` - Settings management
- `/ce/future_sections/ajax/` - AJAX dispatcher for teaching/not-teaching actions
- `/ce/future_sections/<uuid:record_id>/` - Record detail
- `/ce/future_sections/delete/` - Delete a FutureSection record
- `/ce/future_sections/bulk_actions/` - Bulk operations (mark as reviewed/submitted)
- `/ce/future_sections/get_highschool_admins/` - Return admins for a highschool
- `/ce/future_sections/send_pending_reminder/` - Send ad-hoc reminder to HS admins
- `/ce/future_sections/api/future_class_section/` - API endpoint for future class sections
- `/ce/future_sections/api/future_projection/` - API endpoint for future projections
- `/ce/future_sections/api/pending_future_class_sections/` - API endpoint for pending sections
- `/ce/future_sections/api/notification_logs/` - API endpoint for notification history

### Shared API URLs

The app also provides a global namespace for API access:

```python
# In myce/urls.py
path('future_sections/', include('future_sections.urls')),
```

- `/future_sections/` - Shared page (requires authentication)
- `/future_sections/api/actions/mark-teaching/` - Mark course as teaching
- `/future_sections/api/actions/mark-not-teaching/` - Mark course as not teaching
- `/future_sections/api/actions/remove-teaching-status/` - Remove teaching status
- `/future_sections/api/actions/add-teacher/` - Add new teacher course
- `/future_sections/api/actions/confirm-sections/` - Confirm class sections
- `/future_sections/api/actions/confirm-administrators/` - Confirm administrators
- `/future_sections/api/course-requests/` - List course requests
- `/future_sections/api/admin-positions/` - List/manage admin positions

## Configuration

### Teaching Form Configuration

The teaching form fields can be configured via the `teaching_form_config` setting in the Future Sections settings:

```json
{
    "fields": ["term", "estimated_enrollment", "class_period"],
    "required": ["term"],
    "show_syllabus": true,
    "labels": {
        "estimated_enrollment": "Expected Number of Students",
        "class_period": "Period/Hour"
    },
    "help_texts": {
        "class_period": "e.g., 1st period, 2nd hour"
    },
    "display_template": "{term_name} | {syllabus_link}"
}
```

**Configuration Options:**

- `fields` - List of fields to display (options: `term`, `estimated_enrollment`, `class_period`, `instruction_mode`, `highschool_course_name`, `number_of_sections`, `full_year`, `trimester`, `fall_only`, `spring_only`, `notes`, `teacher_changed`)
- `required` - List of required fields
- `show_syllabus` - Whether to show syllabus upload field
- `labels` - Custom labels for fields
- `help_texts` - Custom help text for fields
- `display_template` - Template for displaying section info (placeholders: `{term_name}`, `{estimated_enrollment}`, `{class_period}`, `{syllabus_link}`, etc.)

### Add Teacher Form Configuration

The add teacher form fields can be configured via the `add_teacher_form_config` setting:

```json
{
    "labels": {
        "teacher": "Select Instructor",
        "highschool": "School",
        "course": "Course to Teach",
        "term": "Starting Term",
        "estimated_enrollment": "Expected Students"
    },
    "help_texts": {
        "teacher": "Select an existing instructor or check the box to add a new one",
        "course": "Select the course this instructor will teach"
    }
}
```

**Configuration Options:**

- `labels` - Custom labels for fields
- `help_texts` - Custom help text for fields

**Available Fields:** `teacher`, `teacher_first_name`, `teacher_last_name`, `teacher_email`, `highschool`, `course`, `term`, `estimated_enrollment`, `class_period`, `instruction_mode`, `highschool_course_name`, `number_of_sections`

## Directory Structure

```
future_sections/
├── apps.py               # App config with CONFIGURATORS and REPORTS
├── forms.py              # Form classes
├── models.py             # FutureCourse, FutureSection, FutureProjection
├── permissions.py        # Permission classes (IsHSAdminOrInstructor, IsHSAdminOnly, IsInstructorOnly, CanAccessCourseRequest)
├── signals.py            # Django signals (review notification)
├── utils.py              # Shared utilities
├── reports/
│   ├── __init__.py
│   ├── future_classes.py                # Section Requests Export
│   ├── pending_future_classes.py        # Pending - HS Admin Export
│   └── pending_future_classes_courses.py # Pending - Courses Export
├── settings/
│   └── future_sections.py  # App settings configuration
├── static/
│   └── future_sections/
│       └── js/
│           └── future_sections.js  # Frontend JavaScript
├── templates/
│   └── future_sections/
│       ├── future_sections.html    # Main page template (HS Admin/Instructor)
│       ├── teaching_course.html    # Teaching form modal (shared by all portals)
│       ├── add_new_teacher.html    # Add teacher form modal
│       └── ce/
│           ├── index.html          # CE portal main page
│           └── settings.html       # CE portal settings page
├── templatetags/
│   └── future_sections_tags.py     # Custom template tags
├── urls/
│   ├── __init__.py           # Main URL configuration
│   ├── highschool_admin.py   # HS Admin portal URLs
│   ├── instructor.py         # Instructor portal URLs
│   └── ce.py                 # CE portal URLs
├── management/
│   └── commands/
│       ├── migrate_future_sections_data.py  # Data migration from cis app
│       └── notify_pending_section_requests.py # Pending reminder emails
└── views/
    ├── __init__.py
    ├── api.py            # ViewSets (FutureSectionsActionViewSet, CourseRequestViewSet, AdminPositionViewSet)
    ├── pages.py          # FutureSectionsPageView (unified for HS Admin/Instructor)
    ├── hs_admin.py       # Wrapper (delegates to FutureSectionsPageView)
    ├── instructor.py     # Wrapper (delegates to FutureSectionsPageView)
    ├── ce.py             # CE portal views (index, settings, bulk_actions, AJAX handlers, reminders)
    └── ce_api.py         # CE portal API ViewSets (FutureClassSection, FutureProjection, Pending, NotificationLog)
```

## ViewSets

### FutureSectionsActionViewSet

Handles all future sections actions:
- `mark-teaching` - Mark a course as teaching with section details
- `mark-not-teaching` - Mark a course as not being taught
- `remove-teaching-status` - Remove teaching/not-teaching status
- `add-teacher` - Add a new teacher course certificate
- `confirm-sections` - Confirm class sections
- `confirm-administrators` - Confirm school administrators

### CourseRequestViewSet

Returns course requests with merged offering status from FutureCourse. Includes `section_display` for formatted output based on settings.

### AdminPositionViewSet

Manages school administrator positions:
- `list` - Returns all highschool x role combinations
- `assign` - Assign an administrator to a position

### CE Portal ViewSets (ce_api.py)

**FutureClassSectionViewSet** - Lists all future class sections with filtering:
- Filter by academic year, high school, teacher, offering type, teacher course type, status

**FutureProjectionViewSet** - Lists future projections by high school:
- Shows confirmation status for administrators and class sections

**PendingFutureClassSectionViewSet** - Lists teacher course certificates pending response:
- Filters out already responded courses based on settings

**NotificationLogViewSet** - Read-only access to notification history:
- Returns CronLog entries for the `notify_pending_section_requests` command
- Includes run times, summary, and detailed log (emails sent, errors, skipped)

## Permissions

The app provides four permission classes in `permissions.py`:

| Class | Access |
|-------|--------|
| `IsHSAdminOrInstructor` | HS Admin OR Instructor (used by shared API ViewSets) |
| `IsHSAdminOnly` | HS Admin only |
| `IsInstructorOnly` | Instructor only |
| `CanAccessCourseRequest` | Object-level: verifies the user owns or manages the specific certificate |

- High School Administrators can manage all courses at their schools
- Instructors can only manage their own course certificates

## Signals

The app uses Django signals for event-driven behavior:

### Review Notification Signal

When a `FutureCourse` instance is saved via `.save()` and the status changes to `'reviewed'`, an email notification is sent to:
- The instructor (teacher) associated with the course
- The person who originally submitted the section request (if different from the instructor)

This is controlled by the `send_reviewed_notification` setting.

> **Note:** The bulk "Mark as Reviewed" action uses `QuerySet.update()`, which does **not** trigger this signal. The notification only fires when individual instances are saved via `.save()`.

**Shortcodes available in email template:**
- `{{course}}` - Course name
- `{{highschool}}` - High school name
- `{{instructor_first_name}}` - Instructor's first name
- `{{instructor_last_name}}` - Instructor's last name

## Reports

The app provides three export reports available in the CE Portal:

| Report | Description |
|--------|-------------|
| **Section Requests Export** | Exports all FutureCourse records with dynamic fields from `teaching_form_config` |
| **Pending Section Requests - Course(s) Export** | Exports TeacherCourseCertificate records that haven't submitted requests |
| **Pending Section Requests - High School Admin Export** | Exports HSAdministratorPosition records for schools with pending requests |

Reports use the `teaching_form_config.labels` setting for dynamic column headers.

## Troubleshooting

### Reports not appearing

1. Ensure `register_reports` has been run:
   ```bash
   python manage.py register_reports
   ```

2. Verify the app is in `INSTALLED_APPS`

### Settings not appearing

1. Ensure `register_settings` has been run:
   ```bash
   python manage.py register_settings
   ```

### Email notifications not sending

1. Check that `send_reviewed_notification` is set to "Yes" in settings
2. Verify email configuration in Django settings
3. Check that the instructor has a valid email address
4. The bulk "Mark as Reviewed" action uses `QuerySet.update()` which bypasses the `pre_save` signal — review notifications are only sent when individual records are saved via `.save()`

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture documentation with diagrams
- [PRODUCT_GUIDE.md](PRODUCT_GUIDE.md) - Configuration guide for product managers
- [cis app](/cis/) - Core models and business logic
