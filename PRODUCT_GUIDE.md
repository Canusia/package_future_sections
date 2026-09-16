# Future Sections - Product Guide

This guide is intended for internal product managers and covers how to configure the Section Requests module, what each setting controls, and how to use the available reports and actions.

---

## What This Module Does

The Future Sections module collects course offering plans from high schools for an upcoming academic year. High school administrators and instructors indicate which courses they plan to teach, provide section details (term, enrollment estimates, etc.), and confirm their school personnel. CE staff then reviews submissions and exports data for planning.

---

## How to Configure Settings

Navigate to **CE Portal > Settings > Classes > Section Requests**.

### Step-by-Step Setup

1. **Set the Page Name** - Customize the breadcrumb and page title (defaults to "Future Section Requests").
2. **Set Tab Labels** - Optionally rename the "Course Requests" and "School Personnel" tabs.
3. **Set the Academic Year** - Select the academic year you are collecting section requests for ("Requesting Information For").
4. **Set the Previous Year Reference** - Select a prior academic year to show what was previously offered for reference.
5. **Set the Survey Window** - Enter a Starting Date and Ending Date. The section request form is only accessible between these dates.
6. **Configure Portal Messages** - Customize welcome messages, window closed message, and form instructions.
7. **Configure School Personnel** - Decide whether to require personnel confirmation, which roles to verify, and whether all roles must be confirmed before submission.
8. **Choose Course & Instructor Filters** - Select which Course Statuses and Instructor Course Statuses should appear in the request form.
9. **Configure New Teacher Options** - Decide whether HS admins can add new teachers and set the default instructor application status.
10. **Configure Form Fields** - Use the visual Teaching Form Configuration UI to control which fields appear, their labels, required status, and display order.
11. **Configure Email Notifications** - Set up reviewed, pending, and confirmation email templates.
12. **Save** - Click "Save Setting" at the bottom of the page.

---

## Settings Reference

### General Settings

| Setting | What It Controls |
|---------|-----------------|
| **Page Name** | The name shown in the breadcrumb and page title. Default: "Future Section Requests". |
| **Course Requests Tab Title** | Label for the Course Requests tab. Default: "Course Requests". |
| **School Personnel Tab Title** | Label for the School Personnel tab. Default: "School Personnel". |
| **Requesting Information For** | The academic year you are collecting section request information for. |
| **Previous Year Reference** | A prior academic year displayed for reference so schools can see what was offered previously. |
| **Starting Date** | The date the section request form opens for HS admins and instructors. |
| **Ending Date** | The date the form closes. After this date, users see the "Window Closed" message. |
| **Course Column Display Template** | Template for how courses are displayed in the table. Placeholders: `{course_name}`, `{course_title}`, `{credit_hours}`. Default: `{course_title}`. |

### Portal Messages

| Setting | What It Controls |
|---------|-----------------|
| **Welcome Message** | Displayed at the top of the section request page. Shortcodes: `{{academic_year}}`, `{{previous_academic_year}}`, `{{start_date}}`, `{{end_date}}`, `{{previous_year_classes}}`. |
| **Welcome Message - School Personnel Review Tab** | Displayed on the personnel review tab. |
| **Window Closed Message** | Shown when users visit the page outside the survey window. |
| **Message in 'Teaching' Page** | Instructions shown on the form where section details are entered. |
| **Message in 'Add New Teacher' Page** | Instructions on the add-new-teacher form. |
| **Message in 'Edit Role' Page** | Instructions on the edit-role form. |

### School Personnel

These settings control whether and how HS administrators are asked to review their school's personnel.

| Setting | What It Controls | Visibility |
|---------|-----------------|------------|
| **Require School Personnel Confirmation?** | If "Yes", HS admins are asked to review and confirm their school personnel during the section request process. Selecting "No" hides the related fields below. | Always visible |
| **High School Roles to Verify** | Which HS administrator roles are displayed in the personnel review/verification step. | Only when confirmation is required |
| **School Personnel Confirmation Checkbox Text** | Text shown next to the checkbox HS admins must check to confirm they've reviewed their personnel list. | Only when confirmation is required |
| **Require All Roles Confirmed Before Submission** | If "Yes", every selected role must have an active administrator assigned before the HS admin can submit. If "No", they can submit even with unfilled roles. | Only when confirmation is required |
| **Require All Teachers Confirmed Before Submission** | If "Yes", the HS admin must indicate course information (teaching/not teaching) for every instructor before they can submit the course offerings confirmation. If "No", partial responses are allowed. | Always visible |
| **Course Offerings Confirmation Checkbox Text** | Text shown next to the checkbox HS admins must check to confirm they've completed their course offerings review. | Always visible |
| **Confirmation Section Header** | Header text displayed above the "Confirm & Continue" checkboxes on both the Course Requests and School Personnel tabs. | Always visible |

### Course & Instructor Filters

| Setting | What It Controls | Visibility |
|---------|-----------------|------------|
| **Eligible Course Status** | Only courses with these statuses appear in the request form (e.g., Active). Select one or more. | Always visible |
| **Eligible Instructor Course Status** | Only instructor-course assignments with these statuses appear (e.g., Teaching). Select one or more. | Always visible |
| **Allow HS Administrators to create new teachers?** | If "Yes", HS admins can add new instructors directly from the section request page. Selecting "No" hides the related fields below. | Always visible |
| **'Add New Teacher' Prompt** | Text displayed above the "Add New Teacher" button on the section request page. | Only when new teacher creation is allowed |
| **Create New Instructor App For** | When a new teacher is added, if the teacher's course status matches any of these selected statuses, an instructor application is automatically created. | Only when new teacher creation is allowed |
| **Default Status of Instructor Apps** | The initial status assigned to instructor applications created through the section request process (e.g., "In Progress", "Submitted"). | Only when new teacher creation is allowed |

### Form Customization

| Setting | What It Controls |
|---------|-----------------|
| **Teaching Form Configuration** | Visual UI for controlling which fields appear on the section request form, which are required, custom labels, display order (by weight), and whether to show syllabus upload. Fields: term, estimated enrollment, class period, instruction mode, high school course name, number of sections, full year, trimester, fall only, spring only, notes, teacher changed. |
| **Add Teacher Form Configuration** | Visual UI for controlling the add-teacher form fields: teacher first name, last name, and email. The school, course, term, and teacher fields are always included. The same **Add Teacher Form Fields** card also includes two document upload rows, "Syllabus" and "Class Assessment", with the usual Visible / Required / Custom Label / drag-order controls. These are independent of the teaching form's own Syllabus and Assessment Upload fields — a school can be asked for documents on both forms without them overwriting each other. CE staff see the uploaded files through the `{new_teacher_syllabus}` and `{new_teacher_class_assessment}` Display Template placeholders. |

### Section Request Review

These settings control whether submitted requests must go through reviewer approval, and in what order.

| Setting | What It Controls |
|---------|-----------------|
| **Do course proposals need to be reviewed?** | If "Yes", CE can send a submitted request into review instead of straight to Reviewed. |
| **Reviewer Roles & Order** | A card that picks which CourseAdministrator role(s) on the course (e.g. Faculty, Dept. Chair, Dean) review section requests (the **Include** column) and gives each a number ("weight"). Drag a row by its handle to reorder — the numbers renumber automatically — or type the same number on two roles to have them asked together. Roles that share a number are asked together, at the same time — exactly like before this card existed. Roles with different numbers are asked in order, lowest first: one role's approval is what opens the next number up. The first time you open this card on a tenant that has never used it, it comes pre-filled from your existing reviewer roles at weight 1 (everyone in one group, asked together). **Assign a mentor during review?** follows directly below the card. |
| **Assign a mentor during review?** | If "Yes", an approval must include a mentor (an existing CourseAdministrator on the course, or a newly created one). |

### Review Escalation (Denied Decisions)

These settings control what happens — and who is told — when a reviewer does not approve a request.

| Setting | What It Controls |
|---------|-----------------|
| **Escalation Recipients** | Comma-separated staff email addresses. When any reviewer denies a request, this list is emailed and the request pauses: no further reviewer is notified until a staff member acts (see "Notify next stage" below). This is a plain staff list, not derived from a role. |
| **Escalation Email Subject / Message** | Subject and body of the denial email. Shortcodes: `{{reviewer_first_name}}`, `{{reviewer_last_name}}`, `{{reviewer_role}}`, `{{comment}}`, `{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}`, `{{academic_year}}`, `{{link}}`. |

### Reviewed Notification

These settings control the email sent when CE staff marks a section request as "Reviewed".

| Setting | What It Controls | Visibility |
|---------|-----------------|------------|
| **Send Email When Status Changes to Reviewed** | "Yes" to enable, "No" to disable. Selecting "No" hides the email fields below. | Always visible |
| **Reviewed Notification Email Subject** | Subject line of the email. | Only when enabled |
| **Reviewed Notification Email Message** | Body of the email. Shortcodes: `{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}`. Use "See Preview" to preview with real data. | Only when enabled |

**Who receives it:** The instructor and the person who originally submitted the request (if different).

### Pending Request Notifications

These settings control reminder emails sent to HS administrators whose schools have not yet responded.

| Setting | What It Controls |
|---------|-----------------|
| **Pending Request Notification Dates** | Specific dates on which reminders are sent. Click to select multiple dates from a calendar. Dates are constrained to the survey window. |
| **Notification Time (Cron Expression)** | The time of day reminders are sent (e.g., `0 8 * * *` for 8:00 AM daily). |
| **Pending Request Notification Roles** | Which HS administrator roles should receive the reminder. If none are selected, all active administrators at schools with pending requests are notified. |
| **Pending Request Notification Subject** | Subject line of the reminder email. |
| **Pending Request Notification Message** | Body of the reminder email. Shortcodes: `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`, `{{academic_year}}`, `{{pending_count}}`, `{{link}}`, `{{start_date}}`, `{{end_date}}`. Use "See Preview" to preview with real data. |

**How it works:** On each date listed in "Notification Dates", the system checks which schools still have unanswered course requests. It then emails the administrators at those schools (filtered by the selected roles) with a reminder and a link to the section request page.

### Post-Submission Confirmation Email

These settings control the email sent to HS administrators after they confirm and submit their section requests.

| Setting | What It Controls |
|---------|-----------------|
| **Confirmation Email Subject** | Subject line of the confirmation email. Shortcodes: `{{academic_year}}`. |
| **Confirmation Email Message** | Body of the confirmation email. Shortcodes: `{{future_sections}}` (HTML table of submitted sections), `{{academic_year}}`, `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`. Use "See Preview" to preview with real data. |

**Who receives it:** The HS administrator who submitted the confirmation.

---

## Screens Overview

### HS Admin / Instructor Portal

**Section Requests Page** (`/highschool_admin/future_sections/` or `/instructor/future_sections/`)

- Shows the Welcome Message at the top.
- Two tabs: **Course Requests** and **School Personnel** (tab labels are configurable).
- **Course Requests tab**: Lists all instructor-course combinations for the user's school(s). Each row has action buttons: "Teaching" or "Not Teaching". Clicking "Teaching" opens a form with fields configured via Teaching Form Configuration. Below the list is a confirmation section with the Confirmation Section Header and checkbox.
- **School Personnel tab** (if personnel confirmation is required): Shows a table of roles and assigned administrators. HS admins can assign or update personnel. Below the list is a confirmation section with checkbox.
- If outside the survey window, shows the Window Closed Message instead.
- If "Allow HS Administrators to create new teachers?" is Yes, an "Add New Teacher" button appears.

### CE Staff Portal

**Course Requests Dashboard** (`/ce/future_sections/`)

- Three DataTable tabs:
  1. **Section Requests** - All submitted FutureCourse records with status, school, instructor, course, and section details. When review is enabled, each row in review shows a stage badge ("Stage N") or a "Paused — awaiting staff" badge, and a Review filter (Approved / Not Approved / Pending / **Paused (not approved)**) narrows the list. Clicking a row's review progress opens the **reviewers modal** — every snapshotted reviewer, their decision, and whose turn it currently is ("Current stage"). Skipped reviewers are not counted as decided: the row's badge and the modal heading show them as a separate "N skipped" count; a **Notify reviewers** button appears there whenever the request is paused.
  2. **School Progress** - FutureProjection records showing which schools have confirmed personnel and sections.
  3. **Pending Requests** - Instructor-course combinations that have not yet been responded to.
  4. **Notification Logs** - History of pending notification emails sent by the system.
- Checkboxes on each row allow selecting records for bulk actions.
- Filter by academic year using the dropdown at the top.

**Settings Page** (`/ce/future_sections/settings/`)

- The full settings form described above.
- Fields are grouped into sections with headers.
- Conditional fields automatically show/hide based on Yes/No selections (e.g., personnel confirmation, new teacher creation, reviewed notifications).

---

## Available Reports

Reports are accessed from **CE Portal > Reports**. Each generates a downloadable Excel/CSV export.

| Report | Description | Parameters |
|--------|-------------|------------|
| **Section Requests Export** | All submitted section requests for a given academic year. Includes school, instructor, course, offering status, and all dynamic fields from Teaching Form Configuration (term, enrollment, etc.). One row per section. When review is enabled, also includes review round, **Current Stage**, **Review Paused**, and the reviewer/decision/mentor/decided-on/comment columns for the live round (multiple reviewers are joined with `; ` in one cell). | Academic Year |
| **Pending Section Requests - Course(s) Export** | Instructor-course combinations that have NOT submitted a response. Useful for identifying who still needs to respond. Includes school, instructor name, course, and status. | Academic Year |
| **Pending Section Requests - HS Admin Export** | HS administrators at schools that have pending requests. Includes school details (name, address, phone, CEEB), admin contact info, position, and status. Useful for targeted outreach. | Academic Year, Position(s) |

---

## Bulk Actions for Processing Requests

On the **Course Requests Dashboard**, CE staff can select one or more section request records and apply bulk actions:

| Action | What It Does |
|--------|-------------|
| **Mark as Pending Review** | Only when review is enabled. Opens a review round on each selected `submitted` request: snapshots every qualifying reviewer (per the Reviewer Roles and Reviewer Roles & Order settings) and emails the first stage. Records already pending review or reviewed are skipped and named in the response, as are records with no qualifying reviewer on the course. |
| **Notify next stage** | Only meaningful on a paused request. Clears the pause and re-notifies whoever is due — the same reviewer(s) again if a stage peer never decided, otherwise the next stage — leaving the earlier denial on the record. Requests that are not paused are skipped and named. Also available as a "Notify reviewers" button in a single request's reviewers modal. |
| **Mark as Reviewed** | Sets the status of selected records to "Reviewed". Refuses (and names) any record that is still live in `pending_review` — see Known Limitation below and "Review Flow" for why a live round is not force-closed here. |
| **Mark as Submitted** | Resets the status of selected records back to "Submitted", clearing any pause. This can be used if a record was marked as reviewed prematurely, or to abandon a stuck round and start a new one. No email is sent. |

### Known Limitation

The "Mark as Reviewed" bulk action updates records directly in the database without triggering Django's save signals. This means the **review notification email is not sent** when using the bulk action, even if the "Send Email When Status Changes to Reviewed" setting is enabled. The notification signal only fires when individual `FutureCourse` records are saved via `.save()`. It also refuses any record still in a live review round (see Review Flow) rather than silently force-closing it — reset to Submitted first if you need to abandon that round.

### Review Flow

When "Do course proposals need to be reviewed?" is Yes, a submitted request does not go straight to Reviewed:

1. CE selects one or more `submitted` requests and runs **Mark as Pending Review**. This snapshots every reviewer who currently qualifies (by CourseAdministrator role on the course) and, if the **Reviewer Roles & Order** card gives roles different numbers, groups them into stages — the lowest-numbered group is asked first.
2. Only the current stage's reviewers are emailed. As each one approves, once every reviewer in that stage has decided, the next stage (if any) is opened and emailed automatically. Approving the last stage marks the request "Reviewed" and sends the usual Reviewed notification (if enabled).
3. If any reviewer in the current stage **does not approve**, the request pauses instead of moving on: the Escalation Recipients are emailed, nobody else is automatically notified, and the dashboard shows a "Paused — awaiting staff" badge. The request stays locked to the school the whole time.
4. Staff resolve a paused request with **Notify next stage** (bulk, or the "Notify reviewers" button in the reviewers modal) — this does not discard the denial, it just gets the round moving again — or by resetting the request to Submitted to abandon the round entirely.
5. A tenant that leaves every role at the same number in the Reviewer Roles & Order card (or never opens the card at all) sees the pre-existing behavior: everyone is asked at once, and the request is Reviewed once they've all decided (with a denial still pausing it rather than closing it, since that rule applies regardless of stage count).

### Changing Reviewers During Review

From the **reviewers modal**, CE staff can change who is reviewing a request without waiting for a decision:

- **Skip** — offered on any reviewer who has not yet decided. Confirming reads: "<name> will be marked as skipped and kept in the review history. If this completes the current stage, the request moves on to the next stage (or is marked reviewed when no one is left)." The message shown afterwards says what actually happened: whether the request is now marked reviewed, or is paused and waiting for "Notify reviewers". The skipped reviewer shows a "Skipped" badge ("by <name> on <date>") in the modal and keeps a **Delete** button. If they open the request, they instead see "You were removed from this review on <date>. No decision is needed from you." with no decision form.
- **Delete** — offered on any reviewer who has not yet decided, or who has already been skipped. Confirming reads: "<name> will be deleted from this round with no record kept. If this completes the current stage, the request moves on the same way." Delete leaves no trace of the reviewer in the round's history, unlike Skip.
- **Add reviewer** — lists active course administrators in a reviewer role on the course who are not already on the round, with a stage-weight input (minimum: the current stage — a closed stage cannot be reopened). Only someone already assigned to the course as a course administrator in a reviewer role can be added; assign them there first if they are not yet an option. Adding a reviewer at the current stage emails them immediately, unless the request is paused. A skipped reviewer must be deleted before they can be added back to the round.

Neither Skip nor Delete can be used on a reviewer who has already approved or not approved — those decisions are permanent for the round.

### Processing Workflow

1. Open the **Course Requests Dashboard**.
2. Filter by the active academic year.
3. Review submissions in the Section Requests tab.
4. Select records using the checkboxes.
5. Use the bulk action dropdown to **Mark as Reviewed**.
6. Use the **Pending Requests** tab and reports to follow up with schools that haven't responded.
7. Use **Send Pending Reminder** to send ad-hoc reminders to specific schools.

### Additional CE Actions

The CE portal also provides these actions beyond bulk operations:

| Action | Where | What It Does |
|--------|-------|-------------|
| **Send Survey to Instructors** | Settings page | Emails survey links to selected instructors |
| **Send Pending Reminder** | Course Requests dashboard | Sends ad-hoc reminder emails to HS admins at specific schools |
| **Mark Teaching/Not Teaching** | AJAX actions | CE staff can mark courses as teaching or not teaching on behalf of instructors |

---

## Email Shortcodes Quick Reference

### Welcome Message
`{{academic_year}}`, `{{previous_academic_year}}`, `{{start_date}}`, `{{end_date}}`, `{{previous_year_classes}}`

### Reviewed Notification
`{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}`

### Review Escalation (Denied Decisions)
`{{reviewer_first_name}}`, `{{reviewer_last_name}}`, `{{reviewer_role}}`, `{{comment}}`, `{{course}}`, `{{highschool}}`, `{{instructor_first_name}}`, `{{instructor_last_name}}`, `{{academic_year}}`, `{{link}}`

### Pending Request Notification
`{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`, `{{academic_year}}`, `{{pending_count}}`, `{{link}}`, `{{start_date}}`, `{{end_date}}`

### Confirmation Email
`{{future_sections}}`, `{{academic_year}}`, `{{admin_first_name}}`, `{{admin_last_name}}`, `{{highschool}}`
