# Future Sections - Product Guide

This guide is intended for internal product managers and covers how to configure the Section Requests module, what each setting controls, and how to use the available reports and actions.

---

## What This Module Does

The Future Sections module collects course offering plans from high schools for an upcoming academic year. High school administrators and instructors indicate which courses they plan to teach, provide section details (term, enrollment estimates, etc.), and confirm their school personnel. CE staff then reviews submissions and exports data for planning.

---

## How to Configure Settings

Navigate to **CE Portal > Settings > Classes > Section Requests**.

### Step-by-Step Setup

1. **Set the Academic Year** - Select the academic year you are collecting section requests for.
2. **Set the Previous Academic Year** - Used to display what was offered last year for reference.
3. **Set the Survey Window** - Enter a Starting Date and Ending Date. The section request form is only accessible to HS admins and instructors between these dates.
4. **Choose Course Filters** - Select which Course Statuses and Instructor Course Statuses should appear in the request form (e.g., only "Active" courses with "Teaching" instructors).
5. **Select HS Admin Roles to Verify** - Choose which high school administrator roles are shown in the personnel verification step.
6. **Configure Form Fields** - Use the Teaching Form Configuration (JSON) to control which fields appear on the section request form (term, enrollment, class period, etc.).
7. **Configure Email Notifications** - Set up reviewed and pending notification templates (see below).
8. **Save** - Click "Save Setting" at the bottom of the page.

---

## Settings Reference

### Survey Window & Academic Year

| Setting | What It Controls |
|---------|-----------------|
| **Starting Date** | The date the section request form opens for HS admins and instructors. |
| **Ending Date** | The date the form closes. After this date, users see the "Window Closed" message. |
| **Academic Year** | The target year being planned for. Shown on forms and used to filter data. |
| **Previous Academic Year** | Displayed for reference so schools can see what was offered last year. |

### Course & Instructor Filters

| Setting | What It Controls |
|---------|-----------------|
| **Course Status** | Only courses with these statuses appear in the request form (e.g., Active). |
| **Instructor Course Status** | Only instructor-course assignments with these statuses appear (e.g., Teaching). |

### School Personnel

| Setting | What It Controls |
|---------|-----------------|
| **High School Roles to Verify** | Which HS administrator roles are displayed in the personnel review/verification step. These are the roles that HS admins are asked to confirm. |
| **Allow HS Administrators to create new teachers?** | If "Yes", HS admins can add new instructors directly. The new teacher is created with "Applicant" status. |
| **'Add New Teacher' Prompt** | Label shown above the "Add New Teacher" button. |
| **Create New Instructor Application For** | Which status the teacher application is created with when a new instructor is added. |
| **Checkbox Language for Adding/Confirming School Personnel** | Text shown next to the confirmation checkboxes during the personnel review step. |
| **Confirm School Personnel / Course Offerings Header** | Text displayed above the confirm-and-continue checkboxes. |

### Form Customization

| Setting | What It Controls |
|---------|-----------------|
| **Welcome Message** | Displayed at the top of the section request page. Supports shortcodes: `{{academic_year}}`, `{{previous_academic_year}}`, `{{start_date}}`, `{{end_date}}`, `{{previous_year_classes}}`. |
| **Welcome Message - School Personnel Review Tab** | Displayed on the personnel review tab. |
| **Window Closed Message** | Shown when users visit the page outside the survey window. |
| **Message in 'Teaching' Page** | Instructions shown on the form where section details are entered. |
| **Message in 'Add New Teacher' Page** | Instructions on the add-new-teacher form. |
| **Message in 'Edit Role' Page** | Instructions on the edit-role form. |
| **Teaching Form Configuration** | JSON that controls which fields appear on the section request form, which are required, custom labels, help text, and how sections are displayed. See README.md for full JSON schema. |
| **Add Teacher Form Configuration** | JSON that controls labels, help text, and field ordering on the add-teacher form. Available fields: `teacher`, `teacher_first_name`, `teacher_last_name`, `teacher_email`, `highschool`, `course`, `term`, `estimated_enrollment`, `class_period`, `instruction_mode`, `highschool_course_name`, `number_of_sections`. See README.md for full JSON schema. |
| **Course Display Template** | Template for how courses are displayed in the table. Placeholders: `{course_name}`, `{course_title}`, `{credit_hours}`. |

### Reviewed Notification

These settings control the email sent when CE staff marks a section request as "Reviewed".

| Setting | What It Controls |
|---------|-----------------|
| **Send Email When Status Changes to Reviewed** | "Yes" to enable, "No" to disable. |
| **Reviewed Notification Email Subject** | Subject line of the email. |
| **Reviewed Notification Email Message** | Body of the email. Shortcodes: `{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}`. |

**Who receives it:** The instructor and the person who originally submitted the request (if different).

### Pending Request Notifications

These settings control reminder emails sent to HS administrators whose schools have not yet responded.

| Setting | What It Controls |
|---------|-----------------|
| **Pending Request Notification Dates** | Specific dates on which reminders are sent. Click to select dates from a calendar. |
| **Notification Time (Cron Expression)** | The time of day reminders are sent (e.g., `0 8 * * *` for 8:00 AM daily). |
| **Pending Request Notification Roles** | Which HS administrator roles should receive the reminder. If none are selected, all active administrators at schools with pending requests are notified. |
| **Pending Request Notification Subject** | Subject line of the reminder email. |
| **Pending Request Notification Message** | Body of the reminder email. Shortcodes: `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`, `{{academic_year}}`, `{{pending_count}}`, `{{link}}`. |

**How it works:** On each date listed in "Notification Dates", the system checks which schools still have unanswered course requests. It then emails the administrators at those schools (filtered by the selected roles) with a reminder and a link to the section request page.

### Post-Submission Confirmation Email

These settings control the email sent to HS administrators after they confirm and submit their section requests.

| Setting | What It Controls |
|---------|-----------------|
| **Confirmation Email Subject** | Subject line of the confirmation email. Shortcodes: `{{academic_year}}`. |
| **Confirmation Email Message** | Body of the confirmation email. Shortcodes: `{{future_sections}}` (HTML table of submitted sections), `{{academic_year}}`, `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`. |

**Who receives it:** The HS administrator who submitted the confirmation.

---

## Screens Overview

### HS Admin / Instructor Portal

**Section Requests Page** (`/highschool_admin/future_sections/` or `/instructor/future_sections/`)

- Shows the Welcome Message at the top.
- Lists all instructor-course combinations for the user's school(s).
- Each row has action buttons: "Teaching" or "Not Teaching".
- Clicking "Teaching" opens a form with fields configured via Teaching Form Configuration.
- HS admins also see tabs for personnel review and confirmation checkboxes.
- If outside the survey window, shows the Window Closed Message instead.

### CE Staff Portal

**Course Requests Dashboard** (`/ce/future_sections/`)

- Three DataTable tabs:
  1. **Section Requests** - All submitted FutureCourse records with status, school, instructor, course, and section details.
  2. **School Progress** - FutureProjection records showing which schools have confirmed personnel and sections.
  3. **Pending Requests** - Instructor-course combinations that have not yet been responded to.
- Checkboxes on each row allow selecting records for bulk actions.
- Filter by academic year using the dropdown at the top.

**Settings Page** (`/ce/future_sections/settings/`)

- The full settings form described above.

---

## Available Reports

Reports are accessed from **CE Portal > Reports**. Each generates a downloadable Excel/CSV export.

| Report | Description | Parameters |
|--------|-------------|------------|
| **Section Requests Export** | All submitted section requests for a given academic year. Includes school, instructor, course, offering status, and all dynamic fields from Teaching Form Configuration (term, enrollment, etc.). One row per section. | Academic Year |
| **Pending Section Requests - Course(s) Export** | Instructor-course combinations that have NOT submitted a response. Useful for identifying who still needs to respond. Includes school, instructor name, course, and status. | Academic Year |
| **Pending Section Requests - HS Admin Export** | HS administrators at schools that have pending requests. Includes school details (name, address, phone, CEEB), admin contact info, position, and status. Useful for targeted outreach. | Academic Year, Position(s) |

---

## Bulk Actions for Processing Requests

On the **Course Requests Dashboard**, CE staff can select one or more section request records and apply bulk actions:

| Action | What It Does |
|--------|-------------|
| **Mark as Reviewed** | Sets the status of selected records to "Reviewed". **Note:** The bulk action currently does not trigger the review notification email (see Known Limitation below). |
| **Mark as Submitted** | Resets the status of selected records back to "Submitted". This can be used if a record was marked as reviewed prematurely. No email is sent. |

### Known Limitation

The "Mark as Reviewed" bulk action updates records directly in the database without triggering Django's save signals. This means the **review notification email is not sent** when using the bulk action, even if the "Send Email When Status Changes to Reviewed" setting is enabled. The notification signal only fires when individual `FutureCourse` records are saved via `.save()`.

### Processing Workflow

1. Open the **Course Requests Dashboard**.
2. Filter by the active academic year.
3. Review submissions in the Section Requests tab.
4. Select records using the checkboxes.
5. Use the bulk action dropdown to **Mark as Reviewed**.
6. Use the **Pending Requests** tab and reports to follow up with schools that haven't responded.

### Additional CE Actions

The CE portal also provides these actions beyond bulk operations:

| Action | Where | What It Does |
|--------|-------|-------------|
| **Send Survey to Instructors** | Settings page | Emails survey links to selected instructors |
| **Send Pending Reminder** | Course Requests dashboard | Sends ad-hoc reminder emails to HS admins at specific schools |
| **Mark Teaching/Not Teaching** | AJAX actions | CE staff can mark courses as teaching or not teaching on behalf of instructors |
