# CE New-Teacher Outreach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let CE staff email the new teacher named on a "teacher changed" section, with the address pre-filled and the message editable, and choose whether that email carries a generic start-application link or a personal invite generated from the captured name and email.

**Architecture:** The CE index opens modals by GETting `future_sections_ce:future_sections_actions` with an `action` name and injecting the returned HTML into a modal body. This feature adds an `email-new-teacher` branch to that dispatcher (GET renders the compose form, POST validates and sends), a serializer field exposing the changed-teacher sections so the index can render one action per affected section, and a tenant subject/message setting pair that pre-fills the compose box. Invite mode creates an unverified `TeacherApplicant` and triggers the existing verification email rather than mailing a capability URL.

**Tech Stack:** Django 5.2, DRF (serializer only), jQuery + DataTables + Bootstrap 4 modals, `mailer.send_html_mail`, `instructor_app`'s `TeacherApplicant`.

## Global Constraints

- **Package:** all work is inside `/repos/ewu/webapp/future_sections` — the `Canusia/package_future_sections` submodule, a separate git repo, branch `feat/new-section-fields`. Commit there, never in the parent `/repos/ewu` repo.
- **Design spec:** `docs/superpowers/specs/2026-08-04-ce-new-teacher-outreach-design.md`. Read it before starting.
- **Import path:** tests import via `future_sections.future_sections.<module>`; application code uses relative imports.
- **No model migrations.** State lives in settings JSON, `FutureCourse.section_info`, and `FutureCourse.meta['history']`. `TeacherApplicant` and `CustomUser` are existing models owned by other packages. If you run `makemigrations`, you have gone off-plan.
- **Never email a `complete_signup` link.** `complete_signup` is public, does not check `account_verified`, and on POST sets the account password and logs the user in — the URL is a capability. Invite mode sends the verification email instead.
- **Do not create a `TeacherApplication`.** The self-serve `complete_signup` flow creates it (`onboarding.py:226`); creating one here would leave a duplicate, half-populated application.
- **Do not change when the automatic `create_new_instructor_app` rule fires.**
- **Test command:** `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.<module> --keepdb` — `--keepdb` is required or the runner dies on EOFError. Full suite: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb`. Baseline is 190 tests passing; that number must only go up.
- **Run every command in the foreground.** Do not background anything or wait on notifications.
- **Do NOT** `git push`, tag, or touch `webapp/requirements.txt`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `future_sections/urls/ce.py` | CE URL registration and role guard | Modify — guard the `ajax` path |
| `future_sections/serializers.py` | `FutureCourseSerializer` | Modify — `changed_teacher_sections` field |
| `future_sections/settings/future_sections.py` | Tenant settings form | Modify — subject/message pair |
| `future_sections/forms.py` | Compose form + validation | Modify — `EmailNewTeacherForm` |
| `future_sections/views/ce.py` | CE action dispatcher | Modify — `email-new-teacher` branch |
| `future_sections/utils.py` | Shared helpers | Modify — applicant get-or-create |
| `future_sections/templates/future_sections/ce/email_new_teacher.html` | Compose modal body | **Create** |
| `future_sections/templates/future_sections/ce/index.html` | CE index | Modify — per-section action + modal |
| `future_sections/tests/test_ce_ajax_permission.py` | Endpoint guard | **Create** |
| `future_sections/tests/test_changed_teacher_sections.py` | Serializer field | **Create** |
| `future_sections/tests/test_new_teacher_email_settings.py` | Settings | **Create** |
| `future_sections/tests/test_email_new_teacher_form.py` | Form validation | **Create** |
| `future_sections/tests/test_email_new_teacher_send.py` | Send + history | **Create** |
| `future_sections/tests/test_email_new_teacher_invite.py` | Invite mode | **Create** |

---

### Task 1: Guard the CE ajax endpoint

**Files:**
- Modify: `future_sections/urls/ce.py`
- Test: `future_sections/tests/test_ce_ajax_permission.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `/ce/future_sections/ajax` requires the `ce` role. Every later task's endpoint inherits this.

This is a security prerequisite, not a feature step. `index`, `detail`, and `settings` are each wrapped in `user_passes_test(user_has_cis_role, login_url='/')`; the `ajax` path is not, so any authenticated user can invoke its branches today. Task 5 puts an email sender behind this URL, so the guard lands first and separately.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_ce_ajax_permission.py`:

```python
"""The CE ajax dispatcher must be CE-only.

index/detail/settings are each wrapped in user_passes_test(user_has_cis_role);
the ajax path was not, so any authenticated user could drive CE actions.
"""

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cis.models.customuser import CustomUser


class CEAjaxPermissionTests(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor', 'student', 'highschool_admin'):
            Group.objects.get_or_create(name=name)
        self.url = reverse('future_sections_ce:future_sections_actions')

    def _user(self, email, group):
        user = CustomUser.objects.create_user(
            username=email, email=email, password='pw')
        user.groups.add(Group.objects.get(name=group))
        return user

    def test_anonymous_is_redirected(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))

    def test_non_ce_user_is_rejected(self):
        self._user('s@x.com', 'student')
        self.client.login(username='s@x.com', password='pw')
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))
        self.assertNotEqual(response.status_code, 200)

    def test_ce_user_is_allowed_through(self):
        self._user('ce@x.com', 'ce')
        self.client.login(username='ce@x.com', password='pw')
        response = self.client.get(self.url)
        # No action supplied, so the view returns None -> 500 is NOT expected;
        # what matters is that the guard did not bounce us.
        self.assertNotIn(response.status_code, (302, 403))
```

If `CustomUser.objects.create_user` needs extra fields in this tenant, add them; do not weaken the assertions. If the no-action GET raises because the view returns `None`, add an `action=noop` query param to that last request rather than changing the guard.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_ce_ajax_permission --keepdb
```

Expected: `test_non_ce_user_is_rejected` and `test_anonymous_is_redirected` FAIL — the endpoint currently lets them through.

- [ ] **Step 3: Add the guard**

In `future_sections/urls/ce.py`, change:

```python
    path(
        'ajax',
        future_sections_actions,
        name='future_sections_actions'
    ),
```

to:

```python
    path(
        'ajax',
        user_passes_test(user_has_cis_role, login_url='/')(
            future_sections_actions),
        name='future_sections_actions'
    ),
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_ce_ajax_permission --keepdb
```

Expected: PASS.

- [ ] **Step 5: Run the full suite for regressions**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
```

Expected: PASS. Any test that drove this endpoint as a non-CE user was asserting the gap; fix the test's user, not the guard.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/urls/ce.py future_sections/tests/test_ce_ajax_permission.py
git commit -m "fix(ce): require the ce role on the future_sections ajax endpoint"
```

---

### Task 2: Expose the changed-teacher sections

**Files:**
- Modify: `future_sections/serializers.py` (`FutureCourseSerializer`)
- Test: `future_sections/tests/test_changed_teacher_sections.py` (create)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `FutureCourseSerializer.changed_teacher_sections` — a list of `{'index': int, 'term_name': str, 'new_teacher_name': str, 'new_teacher_email': str}`, one per section whose `teacher_changed` is `'yes'`, in `section_info['sections']` order. Task 6's CE index renders one action per entry; Task 5 validates `section_index` against the same list.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_changed_teacher_sections.py`:

```python
from django.test import SimpleTestCase

from future_sections.future_sections.serializers import FutureCourseSerializer


class _Obj:
    """Stand-in for FutureCourse — the field only reads section_info."""
    def __init__(self, section_info):
        self.section_info = section_info


def _changed(section_info):
    return FutureCourseSerializer().get_changed_teacher_sections(
        _Obj(section_info))


class ChangedTeacherSectionsTests(SimpleTestCase):
    def test_only_sections_marked_changed_are_returned(self):
        out = _changed({'sections': [
            {'teacher_changed': 'no', 'term_name': 'Fall'},
            {'teacher_changed': 'yes', 'term_name': 'Spring',
             'new_teacher_name': 'Jane Roe', 'new_teacher_email': 'j@x.com'},
        ]})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['new_teacher_name'], 'Jane Roe')

    def test_index_is_the_position_in_sections(self):
        out = _changed({'sections': [
            {'teacher_changed': 'no'},
            {'teacher_changed': 'no'},
            {'teacher_changed': 'yes', 'new_teacher_email': 'j@x.com'},
        ]})
        self.assertEqual(out[0]['index'], 2)

    def test_missing_name_and_email_become_empty_strings(self):
        out = _changed({'sections': [{'teacher_changed': 'yes'}]})
        self.assertEqual(out[0]['new_teacher_name'], '')
        self.assertEqual(out[0]['new_teacher_email'], '')

    def test_no_changed_sections_yields_empty_list(self):
        self.assertEqual(
            _changed({'sections': [{'teacher_changed': 'no'}]}), [])

    def test_empty_and_missing_section_info_are_safe(self):
        self.assertEqual(_changed({}), [])
        self.assertEqual(_changed(None), [])

    def test_several_changed_sections_are_all_returned(self):
        out = _changed({'sections': [
            {'teacher_changed': 'yes', 'new_teacher_email': 'a@x.com'},
            {'teacher_changed': 'yes', 'new_teacher_email': 'b@x.com'},
        ]})
        self.assertEqual([e['index'] for e in out], [0, 1])

    def test_non_yes_values_do_not_count(self):
        for value in ('Yes', 'YES', 'true', '1', ''):
            self.assertEqual(
                _changed({'sections': [{'teacher_changed': value}]}), [],
                value)
```

Note the last case: the stored value is the schema choice `'yes'` exactly. Matching loosely would surface sections the instructor never flagged.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_changed_teacher_sections --keepdb
```

Expected: FAIL — `AttributeError: 'FutureCourseSerializer' object has no attribute 'get_changed_teacher_sections'`.

- [ ] **Step 3: Add the serializer field**

In `future_sections/serializers.py`, add to `FutureCourseSerializer` beside `section_display`:

```python
    changed_teacher_sections = serializers.SerializerMethodField()
```

and the method:

```python
    def get_changed_teacher_sections(self, obj):
        """Sections flagged 'teacher changed', for the CE outreach action.

        The CE index renders sections from pre-formatted display strings, so
        the structured values the compose box needs are surfaced here.
        """
        info = obj.section_info or {}
        out = []
        for index, section in enumerate(info.get('sections', []) or []):
            if (section or {}).get('teacher_changed') != 'yes':
                continue
            out.append({
                'index': index,
                'term_name': section.get('term_name', '') or '',
                'new_teacher_name': section.get('new_teacher_name', '') or '',
                'new_teacher_email': section.get('new_teacher_email', '') or '',
            })
        return out
```

`Meta.fields` is `'__all__'`, so the new field is included automatically.

- [ ] **Step 4: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_changed_teacher_sections --keepdb
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/serializers.py future_sections/tests/test_changed_teacher_sections.py
git commit -m "feat(ce): expose changed-teacher sections on the future course serializer"
```

---

### Task 3: The subject and message settings

**Files:**
- Modify: `future_sections/settings/future_sections.py`
- Test: `future_sections/tests/test_new_teacher_email_settings.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: settings keys `new_teacher_email_subject` and `new_teacher_email_message`, plus module constants `DEFAULT_NEW_TEACHER_EMAIL_SUBJECT` and `DEFAULT_NEW_TEACHER_EMAIL_MESSAGE` importable from `future_sections.settings.future_sections`. Task 4 pre-fills the compose box from the setting, falling back to these constants.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_new_teacher_email_settings.py`:

```python
from django.test import SimpleTestCase

from future_sections.future_sections.settings.future_sections import (
    future_sections as FSForm,
    DEFAULT_NEW_TEACHER_EMAIL_SUBJECT,
    DEFAULT_NEW_TEACHER_EMAIL_MESSAGE,
)


class NewTeacherEmailSettingTests(SimpleTestCase):
    def test_both_fields_are_declared(self):
        for name in ('new_teacher_email_subject', 'new_teacher_email_message'):
            self.assertIn(name, FSForm.base_fields, name)

    def test_both_fields_are_optional(self):
        # Blank falls back to the built-in default rather than blocking a save.
        for name in ('new_teacher_email_subject', 'new_teacher_email_message'):
            self.assertFalse(FSForm.base_fields[name].required, name)

    def test_defaults_are_non_empty(self):
        self.assertTrue(DEFAULT_NEW_TEACHER_EMAIL_SUBJECT.strip())
        self.assertTrue(DEFAULT_NEW_TEACHER_EMAIL_MESSAGE.strip())

    def test_default_message_uses_the_link_shortcode(self):
        # Without {{link}} the recipient has no way to reach the application.
        self.assertIn('{{link}}', DEFAULT_NEW_TEACHER_EMAIL_MESSAGE)

    def test_help_text_lists_the_shortcodes(self):
        help_text = FSForm.base_fields['new_teacher_email_message'].help_text
        for code in ('{{new_teacher_name}}', '{{course}}', '{{highschool}}',
                     '{{link}}'):
            self.assertIn(code, help_text, code)
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_new_teacher_email_settings --keepdb
```

Expected: FAIL — `ImportError` on the two constants.

- [ ] **Step 3: Add the constants**

In `future_sections/settings/future_sections.py`, at module level above the form class:

```python
DEFAULT_NEW_TEACHER_EMAIL_SUBJECT = (
    'Invitation to apply — {{course}} at {{highschool}}'
)

DEFAULT_NEW_TEACHER_EMAIL_MESSAGE = (
    '<p>Dear {{new_teacher_name}},</p>'
    '<p>{{highschool}} has indicated you will be teaching {{course}} for '
    '{{academic_year}}. To teach this course you need to complete an '
    'instructor application.</p>'
    '<p>Please begin here: {{link}}</p>'
)
```

- [ ] **Step 4: Add the two settings fields**

Add them immediately after the `reviewed_email_message` field, so the email settings stay grouped:

```python
    new_teacher_email_subject = forms.CharField(
        max_length=None,
        required=False,
        label='New Teacher Email Subject',
        help_text='Subject line pre-filled when CE staff email a new teacher '
                  'named on a section marked as having changed teachers. '
                  'Leave blank to use the default.'
    )

    new_teacher_email_message = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        validators=[validate_html_short_code],
        label='New Teacher Email Message',
        help_text='Body pre-filled when CE staff email a new teacher. Staff '
                  'can edit it before sending. Shortcodes: '
                  '{{new_teacher_name}}, {{course}}, {{highschool}}, '
                  '{{academic_year}}, {{current_teacher_name}}, '
                  '{{term_name}}, {{link}}. Leave blank to use the default.'
    )
```

Match the widget used by the sibling `reviewed_email_message` field if it is a CKEditor widget rather than a plain `Textarea` — read that field and copy its widget. These are email bodies and are rendered as HTML, unlike the plain-text button labels.

- [ ] **Step 5: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_new_teacher_email_settings --keepdb
```

Expected: PASS.

- [ ] **Step 6: Confirm the settings page still renders**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py shell -c "
from crispy_forms.utils import render_crispy_form
from django.test import RequestFactory
from future_sections.future_sections.settings.future_sections import future_sections as F
req = RequestFactory().get('/?report_id=00000000-0000-0000-0000-000000000000')
html = render_crispy_form(F(req, initial=F.from_db() or {}))
for n in ('new_teacher_email_subject', 'new_teacher_email_message'):
    print(n, 'present:', f'name=\"{n}\"' in html)
"
```

Expected: both `True`.

- [ ] **Step 7: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/settings/future_sections.py future_sections/tests/test_new_teacher_email_settings.py
git commit -m "feat(settings): add the new-teacher outreach subject and message"
```

---

### Task 4: The compose form

**Files:**
- Modify: `future_sections/forms.py`
- Test: `future_sections/tests/test_email_new_teacher_form.py` (create)

**Interfaces:**
- Consumes: Task 3's defaults.
- Produces: `EmailNewTeacherForm(data=None, *, future_course=None)` in `future_sections/forms.py`, with fields `section_index` (integer), `recipient` (email), `subject`, `message`, `mode` (choices `start_app` / `invite`), `confirm_recipient` (boolean). Task 5's view constructs it with the resolved `FutureCourse` and relies on its `clean` for every rejection.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_email_new_teacher_form.py`:

```python
from django.test import SimpleTestCase

from future_sections.future_sections.forms import EmailNewTeacherForm


class _Course:
    def __init__(self, sections):
        self.section_info = {'sections': sections}


CHANGED = {'teacher_changed': 'yes', 'new_teacher_email': 'j@x.com',
           'new_teacher_name': 'Jane Roe'}
UNCHANGED = {'teacher_changed': 'no'}


def _form(course, **overrides):
    data = {
        'section_index': 0,
        'recipient': 'j@x.com',
        'subject': 'Hello',
        'message': 'Body {{link}}',
        'mode': 'start_app',
        'confirm_recipient': True,
    }
    data.update(overrides)
    return EmailNewTeacherForm(data=data, future_course=course)


class EmailNewTeacherFormTests(SimpleTestCase):
    def test_valid_payload_passes(self):
        self.assertTrue(_form(_Course([CHANGED])).is_valid())

    def test_section_index_out_of_range_is_rejected(self):
        form = _form(_Course([CHANGED]), section_index=5)
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_negative_section_index_is_rejected(self):
        form = _form(_Course([CHANGED]), section_index=-1)
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_section_not_marked_changed_is_rejected(self):
        # Stops a crafted POST emailing an arbitrary address via any record.
        form = _form(_Course([UNCHANGED]))
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_invalid_recipient_is_rejected(self):
        form = _form(_Course([CHANGED]), recipient='not-an-email')
        self.assertFalse(form.is_valid())
        self.assertIn('recipient', form.errors)

    def test_missing_confirmation_is_rejected(self):
        form = _form(_Course([CHANGED]), confirm_recipient=False)
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_recipient', form.errors)

    def test_blank_subject_is_rejected(self):
        form = _form(_Course([CHANGED]), subject='')
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

    def test_blank_message_is_rejected(self):
        form = _form(_Course([CHANGED]), message='')
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_unknown_mode_is_rejected(self):
        form = _form(_Course([CHANGED]), mode='something_else')
        self.assertFalse(form.is_valid())
        self.assertIn('mode', form.errors)

    def test_invite_mode_is_accepted(self):
        self.assertTrue(_form(_Course([CHANGED]), mode='invite').is_valid())

    def test_recipient_need_not_match_the_captured_address(self):
        # Staff may correct a typo the school admin made.
        self.assertTrue(
            _form(_Course([CHANGED]), recipient='corrected@x.com').is_valid())

    def test_section_is_available_after_validation(self):
        form = _form(_Course([CHANGED]))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.section['new_teacher_name'], 'Jane Roe')
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_form --keepdb
```

Expected: FAIL — `ImportError: cannot import name 'EmailNewTeacherForm'`.

- [ ] **Step 3: Write the form**

Add to `future_sections/forms.py`:

```python
class EmailNewTeacherForm(forms.Form):
    """Compose box for emailing the new teacher named on a changed section.

    Every rejection lives here rather than in the view, so a crafted POST is
    checked identically to a modal submission.
    """

    MODE_CHOICES = (
        ('start_app', 'Send a link to start an application'),
        ('invite', 'Create an invitation for this teacher'),
    )

    section_index = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    recipient = forms.EmailField(
        label='To',
        widget=forms.EmailInput(attrs={'class': 'form-control'}))
    subject = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}))
    message = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10}))
    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        initial='start_app',
        widget=forms.RadioSelect)
    confirm_recipient = forms.BooleanField(
        required=True,
        label='I have checked this email address is correct',
        error_messages={
            'required': 'Confirm the email address before sending.'})

    def __init__(self, *args, future_course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.future_course = future_course
        self.section = None

    def clean_section_index(self):
        index = self.cleaned_data['section_index']
        sections = ((self.future_course.section_info or {}).get('sections')
                    or []) if self.future_course else []
        if index >= len(sections):
            raise ValidationError('That section no longer exists.')
        section = sections[index] or {}
        if section.get('teacher_changed') != 'yes':
            raise ValidationError(
                'That section is not marked as having a new teacher.')
        self.section = section
        return index
```

`ValidationError` is already imported in this module; confirm before adding it.

- [ ] **Step 4: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_form --keepdb
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/forms.py future_sections/tests/test_email_new_teacher_form.py
git commit -m "feat(ce): add the new-teacher outreach compose form"
```

---

### Task 5: Render and send — `start_app` mode

**Files:**
- Modify: `future_sections/views/ce.py`
- Create: `future_sections/templates/future_sections/ce/email_new_teacher.html`
- Test: `future_sections/tests/test_email_new_teacher_send.py` (create)

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: the `email-new-teacher` action on `future_sections_actions`. GET (`future_course_id`, `section_index`) returns the modal body; POST sends and returns `{'status': 'Success', 'message': ..., 'action': 'reload_future_courses'}` — the shape `ce/index.html:920-935` already handles. Task 6 wires the UI to it; Task 7 adds invite mode to the same POST branch.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_email_new_teacher_send.py`:

```python
import json

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from cis.models.customuser import CustomUser
from cis.models.course import Course, Cohort
from cis.models.district import District
from cis.models.highschool import HighSchool
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherHighSchool, TeacherCourseCertificate,
)
from cis.models.term import AcademicYear

from future_sections.future_sections.models import FutureCourse


class _Base(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor', 'faculty'):
            Group.objects.get_or_create(name=name)

        self.ay = AcademicYear.objects.create(name='2027-2028')
        cohort = Cohort.objects.create(designator='HI', name='History')
        self.course = Course.objects.create(
            cohort=cohort, catalog_number='111', title='History 111',
            name='HIST 111', credit_hours=3, status='Active')
        district = District.objects.create(name='D')
        self.hs = HighSchool.objects.create(name='Zillah High', district=district)

        tuser = CustomUser.objects.create(
            username='t@x.com', email='t@x.com',
            first_name='Brock', last_name='Anderson')
        teacher = Teacher.objects.create(user=tuser)
        ths = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=self.hs)
        cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=self.course, status='Teaching')

        self.fc = FutureCourse.objects.create(
            teacher_course=cert, academic_year=self.ay,
            section_info={'teaching': 'yes', 'sections': [{
                'teacher_changed': 'yes',
                'term_name': 'Fall 2027',
                'new_teacher_name': 'Jane Roe',
                'new_teacher_email': 'jane@zillah.test',
            }]},
        )

        Setting.objects.update_or_create(
            key='cis_future_sections',
            defaults={'value': {'academic_year': str(self.ay.id)}})

        self.ce = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        self.client.login(username='ce@x.com', password='pw')
        self.url = reverse('future_sections_ce:future_sections_actions')

    def _post(self, **overrides):
        data = {
            'action': 'email-new-teacher',
            'future_course_id': str(self.fc.id),
            'section_index': 0,
            'recipient': 'jane@zillah.test',
            'subject': 'Invitation',
            'message': 'Hello {{new_teacher_name}} — apply here: {{link}}',
            'mode': 'start_app',
            'confirm_recipient': 'on',
        }
        data.update(overrides)
        return self.client.post(self.url, data)


class ComposeRenderTests(_Base):
    def test_get_returns_the_compose_box_prefilled(self):
        response = self.client.get(self.url, {
            'action': 'email-new-teacher',
            'future_course_id': str(self.fc.id),
            'section_index': 0,
        })
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('jane@zillah.test', body)
        self.assertIn('confirm_recipient', body)


class StartAppSendTests(_Base):
    def test_sends_one_email_to_the_recipient(self):
        self._post()
        self.assertEqual(len(mail.outbox), 1)

    def test_shortcodes_are_rendered(self):
        self._post()
        body = mail.outbox[0].body + str(mail.outbox[0].alternatives)
        self.assertIn('Jane Roe', body)
        self.assertNotIn('{{new_teacher_name}}', body)
        self.assertNotIn('{{link}}', body)

    def test_a_history_entry_is_recorded(self):
        self._post()
        self.fc.refresh_from_db()
        history = (self.fc.meta or {}).get('history', [])
        self.assertTrue(any('jane@zillah.test' in e['action']
                            for e in history), history)

    def test_nothing_is_created_in_start_app_mode(self):
        before = CustomUser.objects.count()
        self._post()
        self.assertEqual(CustomUser.objects.count(), before)

    def test_missing_confirmation_sends_nothing(self):
        response = self._post(confirm_recipient='')
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotEqual(response.status_code, 500)

    def test_section_not_marked_changed_sends_nothing(self):
        self.fc.section_info['sections'][0]['teacher_changed'] = 'no'
        self.fc.save()
        self._post()
        self.assertEqual(len(mail.outbox), 0)

    def test_non_ce_user_cannot_send(self):
        self.client.logout()
        other = CustomUser.objects.create_user(
            username='i@x.com', email='i@x.com', password='pw')
        other.groups.add(Group.objects.get(name='instructor'))
        self.client.login(username='i@x.com', password='pw')
        self._post()
        self.assertEqual(len(mail.outbox), 0)
```

The DEBUG recipient redirect in this codebase forces `to` to a test address; assert on `len(mail.outbox)` and body content, not on the exact `to`, so the tests pass in both settings.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_send --keepdb
```

Expected: FAIL — the action is unrecognised, so GET returns `None` and no mail is sent.

- [ ] **Step 3: Create the compose template**

Create `future_sections/templates/future_sections/ce/email_new_teacher.html`:

```html
{% load crispy_forms_tags %}
<div class="modal-header">
    <h5 class="modal-title">Email {{ new_teacher_name|default:"new teacher" }}</h5>
</div>
<div class="modal-body">
    <p class="text-muted small">
        {{ course }} &middot; {{ highschool }} &middot; {{ term_name }}
    </p>
    <form method="post" action="{{ form_action_url }}" class="fs-ajax-form">
        {% csrf_token %}
        <input type="hidden" name="action" value="email-new-teacher">
        <input type="hidden" name="future_course_id" value="{{ future_course_id }}">
        {{ form|crispy }}
        <p class="alert alert-info small mb-3">
            Choosing <strong>Create an invitation</strong> also sends a separate
            verification email so the teacher can confirm this address.
        </p>
        <input type="submit" class="btn btn-primary" value="Send">
        <button type="button" class="btn btn-sm" onclick="window.closeTeachingModal()">Cancel</button>
    </form>
</div>
```

- [ ] **Step 4: Add the dispatcher branches**

In `future_sections/views/ce.py`, add to `future_sections_actions`'s POST branch:

```python
        if action == 'email-new-teacher':
            return email_new_teacher(request)
```

and to its GET branch:

```python
        elif action == 'email-new-teacher':
            return email_new_teacher(request)
```

Then add the view function:

```python
def email_new_teacher(request):
    """Compose and send an email to the new teacher named on a section."""
    from django.conf import settings as django_settings
    from django.template import Context, Template
    from django.template.loader import get_template
    from django.urls import reverse as url_reverse
    from mailer import send_html_mail

    from ..forms import EmailNewTeacherForm
    from ..settings.future_sections import (
        DEFAULT_NEW_TEACHER_EMAIL_SUBJECT,
        DEFAULT_NEW_TEACHER_EMAIL_MESSAGE,
    )
    from ..utils import add_history_entry, get_fs_config

    source = request.POST if request.method == 'POST' else request.GET
    future_course = get_object_or_404(
        FutureCourse, pk=source.get('future_course_id'))
    fs_config = get_fs_config()

    sections = (future_course.section_info or {}).get('sections') or []
    try:
        index = int(source.get('section_index', 0))
    except (TypeError, ValueError):
        index = -1
    section = sections[index] if 0 <= index < len(sections) else {}

    teacher_course = future_course.teacher_course
    highschool = teacher_course.teacher_highschool.highschool
    start_app_url = request.build_absolute_uri(
        url_reverse('applicant_app:start_app'))

    context_values = {
        'new_teacher_name': section.get('new_teacher_name', ''),
        'course': str(teacher_course.course),
        'highschool': highschool.name,
        'academic_year': str(future_course.academic_year),
        'current_teacher_name': str(teacher_course.teacher_highschool.teacher),
        'term_name': section.get('term_name', ''),
        'link': start_app_url,
    }

    if request.method == 'GET':
        form = EmailNewTeacherForm(
            future_course=future_course,
            initial={
                'section_index': index,
                'recipient': section.get('new_teacher_email', ''),
                'subject': (fs_config.get('new_teacher_email_subject')
                            or DEFAULT_NEW_TEACHER_EMAIL_SUBJECT),
                'message': (fs_config.get('new_teacher_email_message')
                            or DEFAULT_NEW_TEACHER_EMAIL_MESSAGE),
            },
        )
        return render(
            request,
            'future_sections/ce/email_new_teacher.html',
            {
                'form': form,
                'future_course_id': str(future_course.id),
                'form_action_url': url_reverse(
                    'future_sections_ce:future_sections_actions'),
                **context_values,
            },
        )

    form = EmailNewTeacherForm(data=request.POST, future_course=future_course)
    if not form.is_valid():
        return JsonResponse({
            'status': 'error',
            'message': 'Please correct the errors and try again.',
            'errors': form.errors,
        }, status=400)

    data = form.cleaned_data
    recipient = data['recipient']

    context = Context(context_values)
    subject = Template(data['subject']).render(context)
    text_body = Template(data['message']).render(context)
    html_body = get_template('cis/email.html').render({'message': text_body})

    to = [recipient]
    if getattr(django_settings, 'DEBUG', True):
        to = ['kadaji@gmail.com']

    send_html_mail(subject, text_body, html_body,
                   django_settings.DEFAULT_FROM_EMAIL, to)

    add_history_entry(
        future_course, request.user,
        f"Emailed new teacher {recipient} ({data['mode']})"
        f" for {context_values['term_name'] or 'section'}")
    future_course.save()

    return JsonResponse({
        'status': 'Success',
        'display': 'swal',
        'message': f'Email sent to {recipient}.',
        'action': 'reload_future_courses',
    })
```

Add any of `render`, `JsonResponse`, `get_object_or_404` that are not already imported at the top of `views/ce.py`.

- [ ] **Step 5: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_send --keepdb
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/views/ce.py future_sections/templates/future_sections/ce/email_new_teacher.html future_sections/tests/test_email_new_teacher_send.py
git commit -m "feat(ce): compose and send the new-teacher outreach email"
```

---

### Task 6: Invite mode

**Files:**
- Modify: `future_sections/utils.py`, `future_sections/views/ce.py`
- Test: `future_sections/tests/test_email_new_teacher_invite.py` (create)

**Interfaces:**
- Consumes: Task 5's view.
- Produces: `get_or_create_applicant(email, full_name)` in `utils.py`, returning `(applicant, created)`.

- [ ] **Step 1: Write the failing test**

Create `future_sections/tests/test_email_new_teacher_invite.py`, reusing Task 5's `_Base` by importing it:

```python
from unittest import mock

from django.core import mail

from cis.models.customuser import CustomUser

from future_sections.future_sections.tests.test_email_new_teacher_send import (
    _Base,
)


def _applicant_model():
    import importlib.util
    if importlib.util.find_spec('instructor_app.instructor_app'):
        from instructor_app.instructor_app.models.teacher_applicant_model \
            import TeacherApplicant
    else:
        from instructor_app.models.teacher_applicant_model import (
            TeacherApplicant)
    return TeacherApplicant


class InviteModeTests(_Base):
    def test_creates_a_user_and_applicant(self):
        TeacherApplicant = _applicant_model()
        before = TeacherApplicant.objects.count()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(TeacherApplicant.objects.count(), before + 1)
        self.assertTrue(
            CustomUser.objects.filter(email='jane@zillah.test').exists())

    def test_sends_the_verification_email(self):
        TeacherApplicant = _applicant_model()
        with mock.patch.object(
                TeacherApplicant, 'send_verification_request_email') as send:
            self._post(mode='invite')
        self.assertTrue(send.called)

    def test_does_not_create_a_teacher_application(self):
        # complete_signup creates that record; a second one would be a
        # half-populated duplicate.
        import importlib.util
        if importlib.util.find_spec('instructor_app.instructor_app'):
            from instructor_app.instructor_app.models.teacher_applicant \
                import TeacherApplication
        else:
            from instructor_app.models.teacher_applicant import (
                TeacherApplication)
        before = TeacherApplication.objects.count()
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(TeacherApplication.objects.count(), before)

    def test_existing_user_is_reused(self):
        CustomUser.objects.create(
            username='jane@zillah.test', email='jane@zillah.test',
            first_name='Jane', last_name='Roe')
        before = CustomUser.objects.count()
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(CustomUser.objects.count(), before)

    def test_staff_email_is_still_sent(self):
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(len(mail.outbox), 1)

    def test_applicant_failure_sends_no_staff_email(self):
        with mock.patch(
                'future_sections.future_sections.utils.get_or_create_applicant',
                side_effect=Exception('boom')):
            self._post(mode='invite')
        self.assertEqual(len(mail.outbox), 0)
```

If the `TeacherApplicant` module path differs, correct the import — do not weaken assertions.

- [ ] **Step 2: Run the test and verify it fails**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_invite --keepdb
```

Expected: FAIL — invite mode currently behaves exactly like `start_app`, so nothing is created.

- [ ] **Step 3: Add the helper**

In `future_sections/utils.py`:

```python
def get_or_create_applicant(email, full_name):
    """Return ``(TeacherApplicant, created)`` for *email*.

    Reuses an existing user and applicant rather than creating a second
    account for the same address. The applicant is left unverified: the
    caller sends the verification email so the recipient proves they control
    the address before they can set a password.
    """
    import importlib.util
    from cis.models.customuser import CustomUser

    if importlib.util.find_spec('instructor_app.instructor_app'):
        from instructor_app.instructor_app.models.teacher_applicant_model \
            import TeacherApplicant
    else:
        from instructor_app.models.teacher_applicant_model import (
            TeacherApplicant)

    first_name, _, last_name = (full_name or '').strip().partition(' ')

    user = CustomUser.objects.filter(email__iexact=email).first()
    if user is None:
        user = CustomUser.objects.create(
            username=email, email=email,
            first_name=first_name, last_name=last_name)

    applicant = TeacherApplicant.objects.filter(user=user).first()
    if applicant is not None:
        return applicant, False

    return TeacherApplicant.objects.create(user=user), True
```

- [ ] **Step 4: Branch on the mode in the view**

In `email_new_teacher`, immediately after `recipient = data['recipient']` and **before** any mail is sent:

```python
    if data['mode'] == 'invite':
        from ..utils import get_or_create_applicant
        try:
            applicant, _created = get_or_create_applicant(
                recipient, context_values['new_teacher_name'])
            applicant.send_verification_request_email()
        except Exception as exc:
            logger.error('New-teacher invite failed for %s: %s',
                         recipient, exc)
            return JsonResponse({
                'status': 'error',
                'message': ('Could not create the invitation. '
                            'No email was sent.'),
            }, status=400)
```

A half-completed invite is worse than none, so the staff email is skipped when this fails. Confirm `logger` exists in `views/ce.py`; add `logger = logging.getLogger(__name__)` if not.

- [ ] **Step 5: Run the test and verify it passes**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_email_new_teacher_invite --keepdb
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/utils.py future_sections/views/ce.py future_sections/tests/test_email_new_teacher_invite.py
git commit -m "feat(ce): invite mode creates an applicant and sends verification"
```

---

### Task 7: Wire the CE index

**Files:**
- Modify: `future_sections/templates/future_sections/ce/index.html`

**Interfaces:**
- Consumes: Task 2's serializer field, Task 5's endpoint.
- Produces: nothing later depends on.

No automated test — this is DataTables render markup. Verification is by rendering the template and by a manual browser check.

- [ ] **Step 1: Add the action to the Section Info column**

In the `records_all` column config, the Section Info renderer currently ends with `return offer_info;` for the teaching case. Extend it so each changed-teacher section gets an envelope action:

```javascript
                                                if (teaching == 'yes') {
                                                    var offer_info = 'Marked as Offering';
                                                    $.each(sd.displays || [], function(k, displayText) {
                                                        if (displayText) {
                                                            offer_info += '<br>' + displayText;
                                                        }
                                                    });
                                                    $.each(row.changed_teacher_sections || [], function(k, cs) {
                                                        var who = cs.new_teacher_name || cs.new_teacher_email || 'new teacher';
                                                        offer_info += '<br><a href="#" class="email-new-teacher" ' +
                                                            'data-toggle="modal" data-target="#teachingModal" ' +
                                                            'data-future-course="' + row.id + '" ' +
                                                            'data-section-index="' + cs.index + '" ' +
                                                            'title="Email the new teacher">' +
                                                            '<i class="fas fa-envelope"></i>&nbsp;Email ' +
                                                            $('<div>').text(who).html() + '</a>';
                                                    });
                                                    return offer_info;
                                                }
```

The name is escaped through `$('<div>').text(...).html()` — it is instructor-supplied free text.

- [ ] **Step 2: Add the click handler**

Beside the existing `$(document).on('click', ".course-action", …)` handler, add:

```javascript
        $(document).on('click', '.email-new-teacher', function () {
            var $link = $(this);
            $.blockUI();
            $.ajax({
                type: 'GET',
                url: "{% url 'future_sections_ce:future_sections_actions' %}",
                data: {
                    'action': 'email-new-teacher',
                    'future_course_id': $link.attr('data-future-course'),
                    'section_index': $link.attr('data-section-index')
                },
                success: function (response) {
                    $.unblockUI();
                    $('#teachingModal .modal-content > .modal-body').html(response);
                },
                error: function () {
                    $.unblockUI();
                    alert('Could not open the email form');
                }
            });
        });
```

The existing `.fs-ajax-form` submit handler already POSTs the compose form and handles the `swal` + `reload_future_courses` response shape, so no extra submit wiring is needed.

- [ ] **Step 3: Verify the template compiles and renders**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py shell -c "
from django.template.loader import get_template
get_template('future_sections/ce/index.html')
get_template('future_sections/ce/email_new_teacher.html')
print('templates compile OK')
"
```

Expected: `templates compile OK`.

- [ ] **Step 4: Run the full suite**

```bash
docker exec -w /app/webapp django_web_ewu python manage.py test future_sections --keepdb
```

Expected: PASS, at or above 190 + the new tests.

- [ ] **Step 5: Manual browser check**

On `/ce/future_sections/`, with a course whose section is marked "teacher changed":

1. The Section Info cell shows an "Email <name>" link per changed section, and none for unchanged sections.
2. Clicking it opens the modal with the address, subject, and body pre-filled.
3. Sending without ticking the confirmation shows an error and sends nothing.
4. `start_app` mode sends the message and creates no records.
5. `invite` mode sends the message and the verification email, and creates one applicant.
6. The new history entry appears against that course.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/templates/future_sections/ce/index.html
git commit -m "feat(ce): add the email-new-teacher action to the section info column"
```

---

## Done

Shipping is separate and manual: push the submodule, tag, bump the pin in `webapp/requirements.txt`, move the gitlink, merge. Do not do any of that as part of executing this plan.
