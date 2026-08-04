# CE New-Teacher Outreach — Email a Changed Teacher and Invite Them to Apply

**Date:** 2026-08-04
**Status:** Approved, not yet implemented
**Package:** `future_sections` (pip-installed submodule, `Canusia/package_future_sections`)

## Goal

Let CE staff, from the CE Section Requests page, email the new teacher named on
a section that was marked "teacher changed" — with the address pre-filled and a
message they can edit — and choose whether that email carries a generic
start-an-application link or a personal invite generated from the name and
email already captured on the section.

## Background

What already exists, and what it means for this feature:

- **The data.** `teacher_changed`, `new_teacher_name`, and `new_teacher_email`
  are per-*section* values inside `FutureCourse.section_info['sections'][i]`.
  One `FutureCourse` can hold several sections, each with its own answer, so
  "the new teacher" is a property of a section, not of a course.
  `new_teacher_email` was added earlier today and is only captured when the
  tenant enables it in the teaching-form field config.
- **The instructor-application workflow is already self-serve and
  email-driven.** `start_app` (public) collects a name and email, creates an
  unverified `TeacherApplicant`, and sends a verification email; the recipient
  verifies, lands on `complete_signup/<applicant_id>`, fills in a profile, and
  **that view creates the `TeacherApplication`** (`onboarding.py:226`) before
  logging them in. Nobody needs to create an application on their behalf.
- **`FutureCourse.create_teacher_application()`** (`models.py:120`) builds a
  `TeacherApplication` for `teacher_course.teacher_highschool.teacher.user` —
  the *existing* teacher on the certificate — so it cannot serve the
  changed-teacher case. It fires from two places, both gated only on
  `teacher_course.status in fs_config['create_new_instructor_app']`:
  `mark_teaching` (`views/api.py:164`, i.e. any ordinary "Enter Course Details"
  save) and `add_teacher` (`views/api.py:377`). On this EWU instance
  `create_new_instructor_app` is `[]`, so neither fires today.
- **`TeacherApplicant`** is a `OneToOneField` to `cis.CustomUser`, so creating
  one creates a user. `TeacherApplicant.create_new(form)` builds both, and
  `send_verification_request_email()` sends the verification link using
  `instructor_app`'s own configurable template.
- **Email sending** in this package is `mailer.send_html_mail(subject,
  text_body, html_body, from, to)` with the body rendered through a Django
  `Template` + `Context` and wrapped in the `cis/email.html` template
  (`views/api.py:507-533`). Three subject/message pairs already exist as
  tenant settings (reviewed, pending, confirmation).
- **History** is `add_history_entry(obj, user, action)` writing into
  `meta['history']`, and the CE index already renders those entries
  (`ce/index.html:461-468`).

## Decisions

1. **Two send modes, chosen by staff at compose time.** The compose box offers
   a generic **start-application link** (the teacher enters their own details)
   or a **personal invite** generated from the section's `new_teacher_name` and
   `new_teacher_email`. Staff pick per email; neither is a tenant-wide setting.
2. **The action is per section, not per course.** A course row can hold several
   sections with different new teachers, so a course-level button would be
   ambiguous. The action appears on each section line where
   `teacher_changed` is "yes".
3. **Subject and body come from a tenant template, editable before sending.**
   A fourth subject/message setting pair pre-fills the compose box; staff edit
   freely. A blank box every time would mean retyping the same message per
   school.
4. **Sends are recorded as `FutureCourse` history entries** — not in the
   Notification History tab. See the correction below.
5. **Staff must confirm the recipient address before sending.** The address was
   typed by a high school admin and may be wrong.
6. **No manual `create_teacher_application()` trigger.** The self-serve route
   creates that record itself; adding a button would produce a second,
   half-populated application the teacher never filled in.

## Two findings that change the shape of the approved plan

Both were discovered while checking the existing code, after the shape above
was agreed. Neither is a change of intent — they are corrections to how the
intent gets implemented.

### The Notification History tab cannot hold these sends

It looked like the natural home, but `NotificationLogViewSet`
(`views/ce_api.py:63`) is `CronLog.objects.filter(cron__command=
'notify_pending_section_requests')` — the run history of the scheduled
reminder job, not a general notification log. Recording a one-off staff email
there would mean fabricating a `CronLog` row for a cron run that never
happened, and it would corrupt the tab's actual meaning.

Instead each send appends a `FutureCourse` history entry via
`add_history_entry`, naming the recipient, the mode, and the sending user.
Those entries are already rendered on the CE index, so the visibility goal —
a second staff member can see who was contacted and when — is met without a
new surface.

### `complete_signup/<applicant_id>` is a capability URL

`complete_signup` is a public view that does **not** check
`account_verified` (`onboarding.py:186-245`). On POST it sets the account
password and calls `auth.login`. Whoever holds that UUID can therefore claim
the account.

So the personal-invite mode must **not** email a raw `complete_signup` link.
It creates the `TeacherApplicant` unverified and calls the existing
`send_verification_request_email()`, which sends the verification link to the
address on the record. The recipient proves they control the address before
they can set a password — the same guarantee `start_app` gives — while still
saving them from retyping the name and email already captured.

Consequence for the compose box: in personal-invite mode the staff-written
message and the verification email are two separate emails to the same
address. The compose box says so plainly, so staff are not surprised.

## Design

### Exposing the section data

The CE index renders section info from pre-formatted `section_display` strings,
which carry no structured per-section values. `FutureClassSectionSerializer`
gains a `changed_teacher_sections` `SerializerMethodField` returning, for each
section where `teacher_changed` is `'yes'`:

```python
{'index': 0, 'term_name': 'Fall 2027',
 'new_teacher_name': 'Jane Roe', 'new_teacher_email': 'jroe@zillah.k12.wa.us'}
```

`index` is the position in `section_info['sections']` and identifies the
section for the send request. Sections whose `teacher_changed` is anything
other than `'yes'` are omitted, so a course with no changed teacher yields an
empty list and renders no action.

### The CE index action

For each entry in `changed_teacher_sections`, the Section Info column renders
an envelope action carrying the `FutureCourse` id and the section index. It
opens a modal loaded from a new endpoint.

When `new_teacher_email` is empty — the tenant never enabled that field, or the
school admin left it blank — the action still renders but opens the compose box
with an empty, required recipient field, so staff can type the address they
have. It is not hidden: "teacher changed with no email captured" is exactly the
case where staff most need to make contact.

### The compose endpoint

A new `@action` on `FutureSectionsActionViewSet`, `url_path='email-new-teacher'`,
`methods=['get', 'post']`, permission `CIS_user_only` (CE staff only — this is a
CE-portal action, unlike the HS-admin actions on that viewset).

**GET** returns the rendered modal: recipient, subject, and body pre-filled from
the tenant template, a mode selector, and a confirmation checkbox.

**POST** validates and sends. Payload: `future_course_id`, `section_index`,
`recipient`, `subject`, `message`, `mode` (`start_app` | `invite`), and
`confirm_recipient`.

Validation, all server-side and all re-checked regardless of what the modal
enforced:

- `future_course_id` resolves and the section index is in range.
- The section's `teacher_changed` is `'yes'` — the action is meaningless
  otherwise, and this stops a crafted POST emailing arbitrary addresses through
  an unrelated record.
- `recipient` is a valid email address.
- `confirm_recipient` is truthy, else a field error.
- `subject` and `message` are non-empty.

### The two modes

**`start_app`** — the message is rendered with a `{{link}}` shortcode resolving
to the absolute `applicant_app:start_app` URL. Nothing is created.

**`invite`** — before sending, get-or-create the `TeacherApplicant`:

- If a `CustomUser` already exists for that address, reuse it rather than
  creating a second account, and reuse its `TeacherApplicant` if it has one.
- Otherwise create the user and applicant from `new_teacher_name` (split into
  first/last on the first space, remainder as last name) and the confirmed
  address.
- Call `send_verification_request_email()` on the applicant.
- `{{link}}` in the staff message resolves to the `applicant_app:start_app`
  URL as in the other mode, so the staff email stands alone if the verification
  mail is missed.

If applicant creation fails, no staff email is sent and the endpoint returns the
error — a half-completed invite is worse than none.

### Settings

Two new fields in the settings form, beside the existing email pairs:

- `new_teacher_email_subject` — `CharField`, optional.
- `new_teacher_email_message` — `CharField` with a CKEditor-style widget
  matching its siblings, optional, `validate_html_short_code`.

Both support `{{new_teacher_name}}`, `{{course}}`, `{{highschool}}`,
`{{academic_year}}`, `{{current_teacher_name}}`, `{{term_name}}`, and
`{{link}}`. Their help text lists the shortcodes, matching the other three
pairs. When either is blank the compose box falls back to a built-in default so
the feature works before a tenant configures anything.

These two are rich text like the other message settings, not plain text like
the button labels — they are email bodies, and the surrounding pattern already
renders them as HTML.

### Sending and recording

Rendering mirrors `views/api.py:507-533`: `Template(...).render(Context(...))`
for subject and body, wrapped by `cis/email.html`, sent with `send_html_mail`
from `DEFAULT_FROM_EMAIL`. The existing DEBUG redirect that forces recipients to
a test address applies here too, so local sends do not reach real teachers.

On success, `add_history_entry(future_course, request.user, ...)` records the
recipient, the mode, and the term, then `future_course.save()`.

## Testing

Django tests under `future_sections/tests/`:

- **`test_changed_teacher_sections.py`** — the serializer field: only
  `teacher_changed == 'yes'` sections appear; index matches position; missing
  name/email yield empty strings not `KeyError`; a course with no changed
  teacher yields `[]`.
- **`test_email_new_teacher_validation.py`** — each rejection: bad index,
  section not marked changed, invalid address, missing confirmation, empty
  subject or body. Each asserts no mail was sent.
- **`test_email_new_teacher_send.py`** — `start_app` mode sends one email,
  creates nothing, and resolves `{{link}}`; template shortcodes render;
  a history entry is appended.
- **`test_email_new_teacher_invite.py`** — `invite` mode creates the user and
  `TeacherApplicant` and calls `send_verification_request_email`; an existing
  user is reused rather than duplicated; a failure to create the applicant
  sends no staff email; no `TeacherApplication` is created by this path.
- **`test_new_teacher_email_settings.py`** — both settings declared, optional,
  and the compose defaults apply when they are blank.

Run with:

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
```

## Shipping

`future_sections` is pip-installed: commit in the submodule, push, tag, bump the
pin in `webapp/requirements.txt`, move the gitlink, merge. No model migrations —
all state is settings JSON, `section_info`, and `meta['history']`. The
`TeacherApplicant` and `CustomUser` records created by invite mode are existing
models owned by `instructor_app` and `cis`.

## Out of scope

- Any manual trigger of `create_teacher_application()` (decision 6).
- Changing when the automatic `create_new_instructor_app` rule fires, including
  the fact that it also fires on ordinary "Enter Course Details" saves.
- Bulk emailing several changed teachers at once.
- Surfacing sent emails anywhere other than the existing history rendering.
