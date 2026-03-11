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

### 2. Add Static Files

Add the future_sections staticfiles directory to `STATICFILES_DIRS` in `settings.py`:

```python
STATICFILES_DIRS = [
    # ... other dirs
    os.path.join(BASE_DIR, 'future_sections', 'staticfiles'),
]
```

### 2.1 Update views/term.py

from rest_framework.authentication import TokenAuthentication, SessionAuthentication

class TermViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TermSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    
    permission_classes = [CIS_user_only]

    def get_queryset(self):
        academic_year_id = self.request.GET.get('academic_year', None)
        result = Term.objects.all()

        if academic_year_id:
            result = result.filter(academic_year__id=academic_year_id)  

        return result.order_by('-code')

### 3. Run Migrations

```bash
python manage.py migrate future_sections
```

### 4. Register Settings and Reports

```bash
python manage.py register_settings
python manage.py register_reports
```

### 5. Include URLs

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

### 6. Add Flatpickr to header-includes.html

```html
<!-- Flatpickr for multi-date selection -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
```

### 7. Load Initial Data (Optional)

If you have existing FutureCourse data from a legacy system:

```bash
python manage.py migrate_future_sections_data
```

### 8. Configure Settings

Navigate to **CE Portal > Settings > Classes > Section Requests** to configure the app.

## Settings Reference

### General Settings

| Setting | Description |
|---------|-------------|
| **Page Name** | Name displayed in the breadcrumb and page title |
| **Course Requests Tab Title** | Label for the Course Requests tab |
| **School Personnel Tab Title** | Label for the School Personnel tab |
| **Requesting Information For** | The academic year you are collecting section requests for |
| **Previous Year Reference** | A prior academic year to show what was previously offered |
| **Starting Date / Ending Date** | Survey window for submissions |
| **Course Column Display Template** | Template for the Course column. Placeholders: `{course_name}`, `{course_title}`, `{credit_hours}` |

### Portal Messages

| Setting | Description |
|---------|-------------|
| **Welcome Message** | Displayed on the main page. Shortcodes: `{{academic_year}}`, `{{previous_academic_year}}`, `{{start_date}}`, `{{end_date}}`, `{{previous_year_classes}}` |
| **Welcome Message - School Personnel Review Tab** | Displayed on the personnel review tab |
| **Window Closed Message** | Displayed when the submission window is closed |
| **Message in 'Teaching' Page** | Displayed on the section info form |
| **Message in 'Add New Teacher' Page** | Displayed on the add teacher form |
| **Message in 'Edit Role' Page** | Displayed on the school admin edit form |

### School Personnel

| Setting | Description |
|---------|-------------|
| **Require School Personnel Confirmation?** | If Yes, HS admins must review and confirm school personnel. Toggles visibility of the fields below |
| **High School Roles to Verify** | Roles shown in the personnel verification step (hidden if confirmation not required) |
| **School Personnel Confirmation Checkbox Text** | Checkbox text for confirming personnel review (hidden if confirmation not required) |
| **Require All Roles Confirmed Before Submission** | If Yes, all selected roles must have an active administrator before the HS admin can submit (hidden if confirmation not required) |
| **Require All Teachers Confirmed Before Submission** | If Yes, all teachers must have course information indicated before submission |
| **Course Offerings Confirmation Checkbox Text** | Checkbox text for confirming course offerings review |
| **Confirmation Section Header** | Header text above the "Confirm & Continue" checkboxes on both tabs |

### Course & Instructor Configuration

| Setting | Description |
|---------|-------------|
| **Eligible Course Status** | Only courses with selected status(es) are available for section requests |
| **Eligible Instructor Course Status** | Only instructor-course assignments with selected status(es) appear in requests |
| **Allow HS Administrators to create new teachers?** | If Yes, shows the fields below |
| **'Add New Teacher' Prompt** | Text displayed above the add teacher button (hidden if not allowed) |
| **Create New Instructor App For** | Which instructor course statuses trigger a new instructor application (hidden if not allowed) |
| **Default Status of Instructor Apps** | Default status assigned to new instructor applications created during section requests (hidden if not allowed) |

### Form Configuration

| Setting | Description |
|---------|-------------|
| **Teaching Form Configuration** | Visual UI for configuring which fields appear on the teaching form, their labels, required status, and display order |
| **Add Teacher Form Configuration** | Visual UI for configuring the add teacher form fields |

### Reviewed Status Email

| Setting | Description |
|---------|-------------|
| **Send Email When Status Changes to Reviewed** | Enable/disable review notification emails. Toggles visibility of the fields below |
| **Reviewed Notification Email Subject** | Subject line for the review email |
| **Reviewed Notification Email Message** | Email template. Shortcodes: `{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}` |

### Pending Request Notifications

| Setting | Description |
|---------|-------------|
| **Pending Request Notification Dates** | Specific dates to send reminder notifications |
| **Notification Time (Cron Expression)** | Cron schedule for notification timing |
| **Pending Request Notification Roles** | Which HS admin roles receive reminders |
| **Pending Request Notification Subject** | Subject line for the reminder email |
| **Pending Request Notification Message** | Email template. Shortcodes: `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`, `{{academic_year}}`, `{{pending_count}}`, `{{link}}`, `{{start_date}}`, `{{end_date}}` |

### Confirmation Email

| Setting | Description |
|---------|-------------|
| **Confirmation Email Subject** | Subject line for post-submission email. Shortcodes: `{{academic_year}}` |
| **Confirmation Email Message** | Email template. Shortcodes: `{{future_sections}}`, `{{academic_year}}`, `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}` |

## Dependencies

The app depends on these Django apps:
- `cis` - Core models (Course, Teacher, HighSchool, etc.)
- `instructor_app` - Teacher application models
- `setting` - Settings framework
- `report` - Reporting framework

Python packages:
- `django-crispy-forms` - Form rendering
- `djangorestframework` - API endpoints
- `model-utils` - FieldTracker for change detection

## Directory Structure

```
future_sections/
├── apps.py               # App config with CONFIGURATORS and REPORTS
├── forms.py              # Form classes
├── models.py             # FutureCourse, FutureSection, FutureProjection
├── serializers.py        # DRF serializers
├── permissions.py        # Permission classes
├── schemas.py            # TeachingSectionFieldSchema
├── signals.py            # Django signals (review notification)
├── utils.py              # Shared utilities
├── reports/
│   ├── future_classes.py                # Section Requests Export
│   ├── pending_future_classes.py        # Pending - HS Admin Export
│   └── pending_future_classes_courses.py # Pending - Courses Export
├── settings/
│   └── future_sections.py  # App settings form
├── staticfiles/
│   └── future_sections/
│       └── js/
│           ├── future_sections.js  # Frontend JavaScript
│           └── settings.js         # Settings page toggle logic
├── templates/
│   └── future_sections/
│       ├── future_sections.html    # Main page template (HS Admin/Instructor)
│       ├── teaching_course.html    # Teaching form modal
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
    ├── api.py            # Action and data ViewSets
    ├── pages.py          # Unified page view (HS Admin/Instructor)
    ├── hs_admin.py       # HS Admin wrapper
    ├── instructor.py     # Instructor wrapper
    ├── ce.py             # CE portal views
    └── ce_api.py         # CE portal API ViewSets
```

## URL Structure

### Portal-Specific URLs

**High School Admin Portal** (`/highschool_admin/future_sections/`):
- Main page and API endpoints

**Instructor Portal** (`/instructor/future_sections/`):
- Main page and API endpoints

**CE Admin Portal** (`/ce/future_sections/`):
- Main page (Course Requests dashboard)
- Settings management
- AJAX dispatcher for teaching/not-teaching actions
- Record detail, delete, bulk actions
- Admin lookup and ad-hoc reminder sending
- API endpoints for future class sections, projections, pending sections, notification logs

### Shared API URLs (`/future_sections/`):
- `api/actions/mark-teaching/` - Mark course as teaching
- `api/actions/mark-not-teaching/` - Mark course as not teaching
- `api/actions/remove-teaching-status/` - Remove teaching status
- `api/actions/add-teacher/` - Add new teacher course
- `api/actions/confirm-sections/` - Confirm class sections
- `api/actions/confirm-administrators/` - Confirm administrators
- `api/course-requests/` - List course requests
- `api/admin-positions/` - List/manage admin positions

## Permissions

| Class | Access |
|-------|--------|
| `IsHSAdminOrInstructor` | HS Admin OR Instructor |
| `IsHSAdminOnly` | HS Admin only |
| `IsInstructorOnly` | Instructor only |
| `CanAccessCourseRequest` | Object-level: verifies user owns or manages the certificate |

## Signals

### Review Notification

When a `FutureCourse` is saved via `.save()` and the status changes to `'reviewed'`, an email is sent to the instructor and the original submitter. Controlled by `send_reviewed_notification` setting.

> **Note:** Bulk "Mark as Reviewed" uses `QuerySet.update()` which does **not** trigger this signal.

## Reports

| Report | Description |
|--------|-------------|
| **Section Requests Export** | Exports FutureCourse records with dynamic fields from `teaching_form_config` |
| **Pending - Course(s) Export** | Exports TeacherCourseCertificate records that haven't submitted requests |
| **Pending - HS Admin Export** | Exports HSAdministratorPosition records for schools with pending requests |

## Configuration

### Teaching Form Configuration

Configure via the visual UI in settings or as JSON in `teaching_form_config`:

```json
{
    "fields": ["term", "estimated_enrollment", "class_period"],
    "required": ["term"],
    "show_syllabus": true,
    "labels": {
        "estimated_enrollment": "Expected Number of Students"
    },
    "help_texts": {
        "class_period": "e.g., 1st period, 2nd hour"
    },
    "weights": {
        "estimated_enrollment": 1,
        "class_period": 2
    },
    "display_template": "{term_name} | {syllabus_link}"
}
```

### Add Teacher Form Configuration

Configure via the visual UI in settings or as JSON in `add_teacher_form_config`:

```json
{
    "fields": ["highschool", "course", "term", "teacher", "teacher_first_name"],
    "required": ["highschool", "course", "term", "teacher"],
    "labels": {
        "teacher": "Select Instructor"
    }
}
```

## Troubleshooting

### Settings JS not loading

Ensure `future_sections/staticfiles` is in `STATICFILES_DIRS` in your Django settings. Run `collectstatic` if in production.

### Reports not appearing

```bash
python manage.py register_reports
```

### Settings not appearing

```bash
python manage.py register_settings
```

### Email notifications not sending

1. Check that `send_reviewed_notification` is set to "Yes" in settings
2. Verify email configuration in Django settings
3. Check that the instructor has a valid email address
4. Bulk "Mark as Reviewed" bypasses `pre_save` signal — notifications only fire on `.save()`
