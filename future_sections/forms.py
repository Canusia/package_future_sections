import json
from urllib.parse import urlparse

from django.utils.safestring import mark_safe
from django.utils.html import format_html

from django.core.validators import validate_email
import datetime
from django import forms
from django.forms.formsets import BaseFormSet
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from cis.models.highschool_administrator import HSAdministrator, HSPosition, HSAdministratorPosition
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool

from cis.models.highschool import HighSchool
from cis.models.course import Cohort, Course
from cis.models.term import AcademicYear, Term
from cis.validators import validate_html_short_code
from .models import FutureCourse, FutureProjection
from .schemas import TeachingSectionFieldSchema
from .utils import sanitize_plain_text


def parse_choice_list(raw, pairs=False):
    """Parse a pipe-delimited option list into Django choice pairs.

    By default (``pairs=False``) every token becomes ``(token, token)`` —
    this is the historical behavior of `instruction_modes` and
    `location_options`, and it is preserved *exactly*, byte for byte,
    because a plain label may legitimately contain a colon (e.g.
    ``"Hybrid: F2F and Online"``). Splitting on that colon would silently
    change both the stored value and the displayed label for existing
    settings, so no colon splitting happens unless explicitly requested.

    With ``pairs=True``, each token is either ``value:Label`` or a bare
    ``Label`` used as both, and only the FIRST colon splits (so a label may
    still contain colons; a value may not). Use this for option lists that
    are designed around distinct stored values from the start — it is not
    a safe default for settings that already exist.

    Blank tokens are dropped in both modes; in ``pairs=True`` mode, tokens
    with an empty value are also dropped.
    """
    choices = []
    for token in (raw or '').split('|'):
        token = token.strip()
        if not token:
            continue
        if not pairs:
            choices.append((token, token))
            continue
        value, sep, label = token.partition(':')
        value = value.strip()
        if not value:
            continue
        label = label.strip() if sep else ''
        choices.append((value, label or value))
    return choices


class SearchInstructorByCohortForm(forms.Form):
    cohort = forms.ModelMultipleChoiceField(
        queryset=Cohort.objects.all().order_by('name'),
        label="Cohort")

class ConfirmHighSchoolAdministratorsForm(forms.Form):

    academic_year = forms.ModelChoiceField(
        label='Academic Year',
        queryset=None,
        widget=forms.HiddenInput
    )

    highschools = forms.ModelMultipleChoiceField(
        label='School(s)',
        queryset=None,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                'class': 'd-none',
                'readonly': True
            }
        )
    )

    confirm = forms.BooleanField(
        label='I confirm',
        widget=forms.CheckboxInput
    )

    action = forms.CharField(
        widget=forms.HiddenInput,
        initial='confirmed_administrators'
    )

    def clean(self):
        # check to make sure all required administrators have been picked
        data = self.cleaned_data

        if data.get('action') == 'confirmed_administrators':
            from .settings.future_sections import future_sections
            from cis.models.highschool_administrator import HSAdministratorPosition

            config = future_sections.from_db()

            if config.get('require_all_roles_confirmed') == '1':
                role_ids = config.get('school_admin_roles', [])

                for role_id in role_ids:
                    for hs in self.fields['highschools'].queryset:
                        if not HSAdministratorPosition.objects.filter(
                            position__id=role_id,
                            highschool=hs,
                            status__iexact='active'
                        ).exists():
                            raise ValidationError('One or more administrator(s) are missing. Please assign an administrator for each role.')

        return data


    def save(self, request):
        data = self.cleaned_data

        academic_year = data.get('academic_year')
        for hs in data.get('highschools'):
            fp = FutureProjection.objects.filter(
                highschool=hs,
                academic_year=academic_year
            )
            if not fp.exists():
                fp = FutureProjection(
                    highschool=hs,
                    academic_year=academic_year,
                    meta={},
                    created_by=request.user
                )
                fp.save()
            else:
                fp = fp[0]

            action = data.get('action')

            fp.meta[f'{action}'] = 'Yes'
            fp.meta[f'{action}_at'] = datetime.datetime.now().strftime('%m/%d/%Y')
            fp.meta[f'{action}_by'] = request.user.id

            # print(fp.meta)
            fp.save()
        
    def __init__(self, highschools, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from .settings.future_sections import future_sections
        config = future_sections.from_db()

        label = config.get('confirm_administrators', 'I agree and confirm that I am authorized to do this')

        self.fields['academic_year'].queryset = AcademicYear.objects.filter(
            id=config.get('academic_year', AcademicYear.objects.first().id)
        )

        self.fields['academic_year'].initial = config.get('academic_year')

        self.fields['highschools'].queryset = highschools
        self.fields['highschools'].initial = highschools

        self.fields['confirm'].label = label

class ConfirmClassSectionsForm(ConfirmHighSchoolAdministratorsForm, forms.Form):
    
    def clean(self):
        data = self.cleaned_data

        highschools = data.get('highschools')

        from .settings.future_sections import future_sections
        fs_config = future_sections.from_db()

        ht_courses = TeacherCourseCertificate.objects.filter(
            teacher_highschool__highschool__in=highschools,
            course__status__in=fs_config.get('course_status'),
            status__in=fs_config.get('teacher_course_status')
        )
        
        if data.get('action') == 'confirmed_class_sections':
            ht_courses = ht_courses.filter(
                course__stream__contains='pathways'
            )
        elif data.get('action') == 'confirmed_facilitator_class_sections':
            ht_courses = ht_courses.filter(
                course__stream__contains='dual_enrollment'
            )
        else:
            ht_courses = ht_courses.exclude(
                course__stream__in=['pathways', 'dual_enrollment']
            )

        if fs_config.get('require_all_teachers_confirmed') == '1':
            for ht_course in ht_courses:
                if not FutureCourse.objects.filter(
                    academic_year=data.get('academic_year'),
                    teacher_course=ht_course
                ).exists():
                    raise ValidationError('You have not indicated course information for one or more teachers. Please correct that and try again.')

        return data

    def __init__(self, highschools, action, *args, **kwargs):
        super().__init__(highschools, *args, **kwargs)

        self.fields['action'].initial = action

        from .settings.future_sections import future_sections
        config = future_sections.from_db()

        label = config.get('confirmed_class_sections', 'I agree and confirm that I am authorized to do this')

        self.fields['confirm'].label = label

class TeacherCourseSectionForm(forms.Form):

    term = forms.ModelChoiceField(
        queryset=None,
        label='Term',
        widget=forms.Select(attrs={'class': 'col-md-10'}))

    syllabus = forms.FileField(
        required=False,
        label='Syllabus'
    )

    file = forms.CharField(
        required=False,
        widget=forms.HiddenInput
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from .settings.future_sections import future_sections as fs_settings
        fs_config = fs_settings.from_db()

        academic_year_id = fs_config.get('academic_year')

        self.fields['term'].queryset = Term.objects.filter(
            academic_year__id=academic_year_id
        )

        # Get teaching form configuration
        try:
            form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
        except Exception:
            form_config = {}

        visible_fields = form_config.get('fields', ['term', 'estimated_enrollment'])
        required_fields = form_config.get('required', ['term'])
        show_syllabus = form_config.get('show_syllabus', False)
        custom_labels = form_config.get('labels', {})
        custom_help_texts = form_config.get('help_texts', {})

        # Build instruction mode choices from settings
        instruction_mode_choices = parse_choice_list(
            fs_config.get('instruction_modes', '')) or None

        # If editing existing data, ensure stored instruction_mode value is in choices
        initial = kwargs.get('initial') or {}
        stored_mode = initial.get('instruction_mode', '')
        if stored_mode and instruction_mode_choices:
            choice_values = {c[0] for c in instruction_mode_choices}
            if stored_mode not in choice_values:
                instruction_mode_choices.append((stored_mode, stored_mode))

        # Build location choices from settings (mirrors instruction_modes)
        location_choices = parse_choice_list(
            fs_config.get('location_options', '')) or None

        # If editing existing data, ensure the stored location value is selectable
        stored_location = initial.get('location', '')
        if stored_location and location_choices:
            location_values = {c[0] for c in location_choices}
            if stored_location not in location_values:
                location_choices.append((stored_location, stored_location))

        # Course-type selects. Unlike instruction_mode/location these are
        # HIDDEN when unconfigured rather than rendered empty: they default to
        # required, and a tenant that has not set options cannot satisfy an
        # empty dropdown. Existing fields keep their current behavior.
        option_driven = {
            'course_type': parse_choice_list(
                fs_config.get('course_types', ''), pairs=True),
            'course_request_type': parse_choice_list(
                fs_config.get('course_request_types', ''), pairs=True),
        }
        for name, parsed in option_driven.items():
            stored = initial.get(name, '')
            if parsed and stored and stored not in {c[0] for c in parsed}:
                parsed.append((stored, stored))

        # Generate configurable fields from schema
        # Dependent fields are always visible when their parent is visible
        dependent_fields = TeachingSectionFieldSchema.get_dependent_fields()

        for field_name in TeachingSectionFieldSchema.get_available_field_names():
            extra_kwargs = {}
            if field_name == 'instruction_mode' and instruction_mode_choices:
                extra_kwargs['choices'] = instruction_mode_choices
            if field_name == 'location' and location_choices:
                extra_kwargs['choices'] = location_choices

            is_visible = field_name in visible_fields
            if field_name in dependent_fields:
                parent = dependent_fields[field_name]
                if parent in visible_fields:
                    is_visible = True

            if field_name in option_driven:
                if not option_driven[field_name]:
                    # No options configured — render nothing at all.
                    self.fields[field_name] = (
                        TeachingSectionFieldSchema.make_django_form_field(
                            field_name, visible=False, required=False))
                    continue
                extra_kwargs['choices'] = option_driven[field_name]

            self.fields[field_name] = TeachingSectionFieldSchema.make_django_form_field(
                field_name,
                visible=is_visible,
                required=field_name in required_fields,
                label_override=custom_labels.get(field_name),
                help_text_override=custom_help_texts.get(field_name),
                **extra_kwargs,
            )

        # File fields keep their previously stored URL in a hidden companion so
        # that saving without re-uploading does not wipe the existing file.
        file_initial = kwargs.get('initial') or {}
        for file_name in TeachingSectionFieldSchema.get_file_field_names():
            if file_name not in visible_fields:
                continue
            self.fields[f'{file_name}_existing'] = forms.CharField(
                required=False,
                widget=forms.HiddenInput(),
            )
            stored_url = file_initial.get(file_name)
            if stored_url:
                self.fields[f'{file_name}_existing'].initial = stored_url
                if urlparse(stored_url).scheme.lower() in ('http', 'https'):
                    self.fields[file_name].label = format_html(
                        '{}<br><small><a target="_blank" '
                        'rel="noopener noreferrer" href="{}">'
                        'Download Uploaded File</a></small>'
                        ' or upload a new file below',
                        self.fields[file_name].label,
                        stored_url,
                    )

        # Set initial value for highschool_course_name if provided
        if kwargs.get('initial', {}).get('highschool_course_name'):
            self.fields['highschool_course_name'].initial = kwargs['initial']['highschool_course_name']

        # Legacy form_field_messages support (for backward compatibility)
        try:
            form_labels = json.loads(fs_config.get('form_field_messages', '{}'))
        except Exception:
            form_labels = {}

        for field_name, field in self.fields.items():
            if form_labels.get(field_name):
                field_attr = form_labels.get(field_name, {})
                if field_attr.get('label'):
                    field.label = mark_safe(field_attr.get('label', ''))
                if field_attr.get('help_text'):
                    field.help_text = mark_safe(field_attr.get('help_text', ''))

        # Handle syllabus visibility
        if not show_syllabus:
            self.fields['syllabus'].widget = forms.HiddenInput()

        # Apply custom labels/help_texts to non-schema fields (term, syllabus)
        for field_name in ('term', 'syllabus'):
            if field_name in custom_labels:
                self.fields[field_name].label = mark_safe(custom_labels[field_name])
            if field_name in custom_help_texts:
                self.fields[field_name].help_text = mark_safe(custom_help_texts[field_name])

        # Handle file link in syllabus label if file exists
        if kwargs.get('initial'):
            initial = kwargs.get('initial')
            if initial.get('file') and show_syllabus:
                self.fields['syllabus'].label = mark_safe(
                    f"Syllabus<br><small><a target='_blank' href='{initial.get('file')}'>Download Uploaded File</a></small> or upload a new file below"
                )

    def clean(self):
        super().clean()

        data = self.cleaned_data

        term = data.get('term')
        if term:
            data['term_name'] = str(term)
            data['term'] = str(term.id)

        # Only compare when both values actually parsed as dates. Hidden date
        # fields are CharFields, so their values are plain strings and this
        # check correctly no-ops for them.
        start = data.get('start_date')
        end = data.get('end_date')
        if isinstance(start, datetime.date) and isinstance(end, datetime.date) \
                and end < start:
            self.add_error(
                'end_date',
                'End Date cannot be earlier than Start Date.')

        # section_info is a JSONField; date objects are not JSON serializable.
        for date_name in TeachingSectionFieldSchema.get_date_field_names():
            value = data.get(date_name)
            if isinstance(value, datetime.date):
                data[date_name] = value.isoformat()

        # Required file fields: a plain HTML file input can't be pre-filled,
        # so a required file field always looks empty on a save that isn't
        # re-uploading. Only when the field errored solely because it was
        # required (no file posted, and every error on the field has code
        # 'required') and the hidden `_existing` companion is carrying a
        # previously stored URL, accept it here instead of blocking the whole
        # form. Any other validation error on the field (e.g. empty-file,
        # size, extension, content-type) is left intact. This is not the
        # authoritative acceptance: build_section_info_from_formset only
        # persists this value if it matches a URL already stored somewhere
        # on the record, so a tampered `_existing` value still can't inject
        # an arbitrary URL — it just ends up stored as ''.
        for file_name in TeachingSectionFieldSchema.get_file_field_names():
            if file_name not in self.fields:
                continue
            existing_value = data.get(f'{file_name}_existing')
            errors = self._errors.get(file_name)
            if (existing_value and errors
                    and not self.files.get(self.add_prefix(file_name))
                    and all(e.code == 'required' for e in errors.as_data())):
                del self._errors[file_name]
                data[file_name] = existing_value

        return data


class HSAdministratorPositionForm(forms.Form):
    highschool = forms.ModelChoiceField(queryset=None)
    position = forms.ModelChoiceField(queryset=None)

    administrator = forms.ModelChoiceField(
        queryset=None,
        required=False,
        help_text='<label style="font-size:1.2em"><input type="checkbox" name="administrator_not_listed" value="administrator_not_listed" id="id_administrator_not_listed">&nbsp;Add new administrator that is not in the list',
    )

    new_administrator_first_name = forms.CharField(
        label='First Name',
        required=False
    )

    new_administrator_last_name = forms.CharField(
        label='Last Name',
        required=False
    )

    new_administrator_email = forms.CharField(
        label='Email Address',
        required=False
    )

    action = forms.CharField(
        widget=forms.HiddenInput,
        required=True,
        initial='edit_highschool_admin_role'
    )

    confirm_school_personnel = forms.BooleanField(
        widget=forms.CheckboxInput,
        label=mark_safe('By checking this box<br>-I under that adding this person will give them access to lorem ipsum.<br>-I confirm I have the authority to do this'),
        required=True
    )

    def clean_new_administrator_first_name(self):
        return sanitize_plain_text(
            self.cleaned_data.get('new_administrator_first_name')
        )

    def clean_new_administrator_last_name(self):
        return sanitize_plain_text(
            self.cleaned_data.get('new_administrator_last_name')
        )

    def clean(self):
        data = self.data

        if not data.get('administrator') and not data.get('administrator_not_listed'):
            raise ValidationError('Please select an existing administrator or enter a new one')
        
        if data.get('administrator_not_listed'):
            if not data.get('new_administrator_first_name'):
                raise ValidationError('Enter the administrator\'s first name')
            
            if not data.get('new_administrator_last_name'):
                raise ValidationError('Enter the administrator\'s last name')
            
            if not data.get('new_administrator_email'):
                raise ValidationError('Enter the administrator\'s last email')
            
            try:
                validate_email(data.get('new_administrator_email'))
            except ValidationError:
                raise ValidationError('Please enter a valid email')

        data = self.cleaned_data    
        return data
        
    def save(self, request, commit=True):
        data = self.data
        cleaned_data = self.cleaned_data

        if data.get('administrator_not_listed'):
            # add new hs admin
            hsadmin = HSAdministrator.get_or_add(
                cleaned_data.get('new_administrator_email'),
                first_name=cleaned_data.get('new_administrator_first_name'),
                last_name=cleaned_data.get('new_administrator_last_name')
            )

            HSAdministratorPosition.objects.filter(
                highschool=cleaned_data.get('highschool'),
                position=cleaned_data.get('position')
            ).update(status='Inactive')

            hsadmin_position = HSAdministratorPosition.get_or_add(
                hsadmin=hsadmin,
                highschool=cleaned_data.get('highschool'),
                position=cleaned_data.get('position'),
                status='Active'
            )
        else:
            # deactivate all users in the role            
            HSAdministratorPosition.objects.filter(
                highschool=cleaned_data.get('highschool'),
                position=cleaned_data.get('position')
            ).update(status='Inactive')

            hsadmin_position = HSAdministratorPosition.get_or_add(
                hsadmin=cleaned_data.get('administrator'),
                highschool=cleaned_data.get('highschool'),
                position=cleaned_data.get('position'),
                status='Active'
            )
        return hsadmin_position
    
    def __init__(self, request, highschool_id, role_id, administrator_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['highschool'].queryset = HighSchool.objects.filter(
            id=highschool_id
        )

        self.fields['position'].queryset = HSPosition.objects.filter(
            id=role_id
        )

        self.fields['position'].initial = role_id
        self.fields['highschool'].initial = highschool_id

        self.fields['administrator'].queryset = HSAdministrator.objects.filter(
            id__in=HSAdministratorPosition.objects.filter(
                highschool__id=highschool_id
            ).values_list('hsadmin')
        )

        from .settings.future_sections import future_sections
        fs_config = future_sections.from_db()
        self.fields['confirm_school_personnel'].label = fs_config.get('confirm_new_personnel', 'Change Me in Settings')

        if administrator_id:
            self.fields['administrator'].initial = administrator_id

from django.forms import ModelChoiceField
class CourseTitleChoiceField(ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.title}'

class AddNewTeacherForm(TeacherCourseSectionForm):

    teacher = forms.ModelChoiceField(
        queryset=None,
        required=False,
        help_text='<label style="font-size:1.2em"><input type="checkbox" name="teacher_not_listed" value="teacher_not_listed" id="id_teacher_not_listed">&nbsp;The Teacher is not in the list',
    )

    teacher_first_name = forms.CharField(
        label='Teacher First Name',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'col-5'
        })
    )
    teacher_last_name = forms.CharField(
        label='Teacher Last Name',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'col-7'
        })
    )
    teacher_email = forms.EmailField(
        label='Teacher Email',
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'col-5'
        })
    )

    highschool = forms.ModelChoiceField(
        queryset=None,
        label='School',
        widget=forms.Select(attrs={'class': 'col-md-10'}))

    campus = forms.ModelChoiceField(
        queryset=None,
        label='Campus',
        required=False,
        empty_label='All Campuses',
        widget=forms.Select(attrs={'class': 'col-md-10'}))

    course = CourseTitleChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': 'col-md-10'}))

    term = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': 'col-md-10'}))

    academic_year_id = forms.CharField(
        widget=forms.HiddenInput
    )

    action = forms.CharField(
        required=True,
        widget=forms.HiddenInput
    )

    field_order = [
        'highschool',
        'term',
        'course',
        'number_of_sections',
        'teacher',
        'teacher_first_name',
        'teacher_last_name',
        'teacher_email',        
        'highschool_course_name',
        'start_date',
        'start_time',
        'end_date',
        'end_time',
        'classroom_hour',
        'instruction_mode'
    ]
    
    
    def __init__(self, request, academic_year, course_type, *args, **kwargs):
        # Call parent __init__ which applies teaching form visibility rules from settings
        super().__init__(*args, **kwargs)

        # Apply add_teacher_form_config: visibility, required, labels, help_texts, ordering
        from .settings.future_sections import future_sections as fs_settings
        fs_config = fs_settings.from_db()

        try:
            add_teacher_config = json.loads(fs_config.get('add_teacher_form_config', '{}'))
        except Exception:
            add_teacher_config = {}

        always_included = {'highschool', 'campus', 'course', 'term', 'teacher'}

        # Restore always-included fields that may have been hidden by parent TeacherCourseSectionForm
        for field_name in always_included:
            if field_name in self.fields:
                field = self.fields[field_name]
                if isinstance(field.widget, forms.HiddenInput):
                    if isinstance(field, forms.ModelChoiceField):
                        field.widget = forms.Select(attrs={'class': 'form-control'})
                    else:
                        field.widget = forms.TextInput(attrs={'class': 'form-control'})

        # Visibility: only the new-teacher fields are configurable here
        config_fields = add_teacher_config.get('fields', None)
        configurable_fields = {
            'teacher_first_name', 'teacher_last_name', 'teacher_email',
        }
        if config_fields is not None:
            config_fields_set = set(config_fields)
            for field_name in configurable_fields:
                if field_name in self.fields:
                    field = self.fields[field_name]
                    if field_name in config_fields_set:
                        # Restore widget if it was hidden by parent
                        if isinstance(field.widget, forms.HiddenInput):
                            if isinstance(field, forms.EmailField):
                                field.widget = forms.EmailInput(attrs={'class': 'form-control'})
                            else:
                                field.widget = forms.TextInput(attrs={'class': 'form-control'})
                    else:
                        # Hide fields not in config
                        field.widget = forms.HiddenInput()
                        field.required = False
        else:
            # No config.fields — restore new-teacher fields (shown/hidden by JS checkbox toggle)
            for field_name in configurable_fields:
                if field_name in self.fields:
                    field = self.fields[field_name]
                    if isinstance(field.widget, forms.HiddenInput):
                        if isinstance(field, forms.EmailField):
                            field.widget = forms.EmailInput(attrs={'class': 'form-control'})
                        else:
                            field.widget = forms.TextInput(attrs={'class': 'form-control'})

        # Required: set field.required for fields in config.required
        config_required = add_teacher_config.get('required', None)
        if config_required is not None:
            config_required_set = set(config_required)
            for field_name, field in self.fields.items():
                if field_name in always_included:
                    continue  # always-included stay required
                if field_name in config_required_set:
                    field.required = True

        # Ordering: sort fields by weight
        config_weights = add_teacher_config.get('weights', None)
        if config_weights is not None:
            always_first = ['highschool', 'campus', 'course', 'term', 'teacher']
            weighted = []
            remaining = []
            for field_name in self.fields:
                if field_name in always_first:
                    continue
                if field_name in config_weights:
                    weighted.append((field_name, config_weights[field_name]))
                else:
                    remaining.append(field_name)
            weighted.sort(key=lambda x: x[1])
            ordered = always_first + [f for f, _ in weighted] + remaining
            self.order_fields(ordered)

        # Labels and help_texts
        custom_labels = add_teacher_config.get('labels', {})
        custom_help_texts = add_teacher_config.get('help_texts', {})

        for field_name, field in self.fields.items():
            if field_name in custom_labels:
                field.label = mark_safe(custom_labels[field_name])
            if field_name in custom_help_texts:
                field.help_text = mark_safe(custom_help_texts[field_name])

        # Campus dropdown. The course list is scoped to a campus: the
        # submitted value when the form is bound (so a course chosen after
        # switching campus still validates on POST), otherwise All Campuses
        # on first render.
        from cis.models.course import Campus
        from django.core.exceptions import ValidationError
        from .utils import addable_courses_for_user

        # Campuses holding at least one selectable course; All Campuses (the
        # empty choice) is the default and applies no campus filter. Courses
        # with no campus are offered under every selection.
        from .utils import campuses_with_selectable_courses
        self.fields['campus'].queryset = campuses_with_selectable_courses()

        active_campus = None
        if self.is_bound and self.data.get('campus'):
            try:
                active_campus = Campus.objects.get(id=self.data.get('campus'))
            except (Campus.DoesNotExist, ValidationError, ValueError):
                active_campus = None

        from cis.utils import user_has_highschool_admin_role, user_has_instructor_role
        from cis.models.teacher import Teacher

        if user_has_highschool_admin_role(request.user):
            user = HSAdministrator.objects.get(user__id=request.user.id)
            highschools = user.get_highschools()

            self.fields['teacher'].queryset = Teacher.objects.filter(
                id__in=TeacherHighSchool.objects.filter(
                    highschool__in=highschools
                ).values('teacher__id')
            ).order_by(
                'user__last_name'
            )
        elif user_has_instructor_role(request.user):

            teacher_user = Teacher.objects.get(user__id=request.user.id)
            highschools = teacher_user.get_highschools(teacher_user)

            self.fields['teacher'].queryset = Teacher.objects.filter(
                id=teacher_user.id
            ).order_by(
                'user__last_name'
            )
            self.fields['teacher'].initial = teacher_user
            # don't let them create a new teacher
            self.fields['teacher'].help_text = ''

            highschools = HighSchool.objects.filter(
                id__in=highschools.values_list('highschool__id')
            )

            # Instructors: only courses they're certified for, scoped to campus.
            self.fields['course'].queryset = addable_courses_for_user(
                request, academic_year, course_type, active_campus)

            self.fields['academic_year_id'].initial = academic_year.id
            self.fields['highschool'].queryset = highschools
            self.fields['term'].queryset = Term.objects.filter(academic_year=academic_year)
            self.fields['action'].initial = "add_new_teacher"
            self._order_campus_before_course()
            return  # Exit early for instructors

        self.fields['academic_year_id'].initial = academic_year.id
        self.fields['highschool'].queryset = highschools
        self.fields['term'].queryset = Term.objects.filter(academic_year=academic_year)

        # For HS Admins: all active courses in the selected campus.
        self.fields['course'].queryset = addable_courses_for_user(
            request, academic_year, course_type, active_campus)

        self.fields['action'].initial = "add_new_teacher"
        self._order_campus_before_course()

    def _order_campus_before_course(self):
        """Render the campus dropdown immediately before the course field,
        regardless of any add_teacher_form_config weight ordering applied above."""
        if 'campus' not in self.fields or 'course' not in self.fields:
            return
        order = [name for name in self.fields if name != 'campus']
        order.insert(order.index('course'), 'campus')
        self.order_fields(order)

    def clean(self):
        super().clean()

        data = self.cleaned_data

        data['highschool'] = str(data.get('highschool').id)
        data['course'] = str(data.get('course').id)
        data['estimated_enrollment'] = str(data.get('estimated_enrollment'))

        return data

    def clean_teacher_email(self):
        data = self.cleaned_data.get('teacher_email').replace(' ', '').lower()
        teacher = self.cleaned_data.get('teacher')

        if not data and not teacher:
            raise ValidationError('Please choose a teacher from the list or enter their email')
        
        if data:
            try:
                validate_email(data)
                return data
            except ValidationError:
                raise ValidationError('Please enter a valid email address')

    def clean_teacher_first_name(self):
        return sanitize_plain_text(self.cleaned_data.get('teacher_first_name'))

    def clean_teacher_last_name(self):
        return sanitize_plain_text(self.cleaned_data.get('teacher_last_name'))

    def clean_highschool_course_name(self):
        return sanitize_plain_text(self.cleaned_data.get('highschool_course_name'))

    def clean_new_teacher_name(self):
        return sanitize_plain_text(self.cleaned_data.get('new_teacher_name'))

    def save(self, request, academic_year, commit=True):

        data = self.cleaned_data
        from cis.models.highschool import HighSchool

        teacher = None
        if not data.get('teacher'):
            if data.get('teacher_email'):
                teacher = Teacher.get_or_add(
                    psid=None,
                    email=data.get('teacher_email'),
                    username=data.get('teacher_email'),
                    first_name=data.get('teacher_first_name'),
                    last_name=data.get('teacher_last_name'),
                )

                if not teacher:
                    print('failed to add teacher')
                    return False
        else:
            teacher = data.get('teacher')

        if teacher:
            if not TeacherHighSchool.objects.filter(
                teacher=teacher,
                highschool__id=data.get('highschool')
            ).exists():
                highschool = HighSchool.objects.get(
                    pk=data.get('highschool')
                )

                teacher_hs = TeacherHighSchool(
                    teacher=teacher,
                    highschool=highschool
                )
                teacher_hs.save()
            else:
                teacher_hs = TeacherHighSchool.objects.filter(
                    teacher=teacher,
                    highschool__id=data.get('highschool')
                )
                teacher_hs = teacher_hs[0]

            from .settings.future_sections import future_sections as fs_settings
            fs_config = fs_settings.from_db()
            
            if not TeacherCourseCertificate.objects.filter(
                teacher_highschool=teacher_hs,
                course__id=data.get('course'),
                status__in=fs_config.get('teacher_course_status', ['Applicant'])
            ).exists():
                course = Course.objects.get(pk=data.get('course'))

                teacher_course = TeacherCourseCertificate(
                    teacher_highschool=teacher_hs,
                    course=course,
                    status='Applicant'
                )
                teacher_course.save()
            else:
                teacher_course = TeacherCourseCertificate.objects.filter(
                    teacher_highschool=teacher_hs,
                    course__id=data.get('course')
                )
                
                if teacher_course.exists():
                    teacher_course = teacher_course[0]

        future_course = FutureCourse.get_or_add(
            teacher_course,
            academic_year,
            submitter=request.user
        )

        if future_course.section_info:
            initial_data = future_course.section_info.get('sections')
        else:
            initial_data = []

        section_data = {}
        section_data['term'] = str(data.get('term'))
        section_data['term_name'] = str(data.get('term_name'))
        section_data['estimated_enrollment'] = data.get('estimated_enrollment')
        
        uploaded_file = request.FILES.get(f'syllabus')

        if uploaded_file:
            from cis.backends.storage_backend import PrivateMediaStorage
            from django.utils.text import get_valid_filename

            media_storage = PrivateMediaStorage()
            
            safe_filename = get_valid_filename(uploaded_file.name)
            path = f"future_section/{future_course.id}/{safe_filename}"

            # Save the file
            path = media_storage.save(path, uploaded_file)
            
            # Get the URL
            url = media_storage.url(path)
            
            # Store the path or URL in cleaned_data
            section_data['file'] = url

        # section_info.append(teaching_form.cleaned_data)
        initial_data.append(section_data)

        future_course.section_info = {'teaching':'yes', 'sections': initial_data}
        future_course.save()

        return future_course
    
class TeacherCourseTeachingForm(forms.Form):
    teacher_course_certificate_id = forms.CharField(widget=forms.HiddenInput)
    academic_year_id = forms.CharField(widget=forms.HiddenInput)
    
class TeacherCourseBaseLinkFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        
        terms = []
        # number_of_sections = []
        duplicates = False        
        for form in self.forms:
            if form.cleaned_data:
                term = form.cleaned_data.get('term')
                # number_of_sections = form.cleaned_data.get('number_of_sections')

                # if term in terms:
                #     duplicates = True
                terms.append(term)

                if duplicates:
                    raise ValidationError(
                        'Terms must be unique',
                        code='duplicate_terms'
                    )
        if len(terms) == 0:
            raise ValidationError(
                'Please enter at least 1 section information'
            )

class TeacherCourseNotTeachingForm(forms.Form):
    #course = forms.ModelChoiceField(queryset=None)
    id = forms.CharField()
    ajax = forms.CharField()
    course_certificate = forms.CharField()
    future_course = forms.CharField()

    TAUGHT_BY_ANOTHER_OPTIONS = (
        ('another', 'Yes'),
        ('not_taught', 'No'),
        ('not_sure', "I'm not sure"),
    )

    taught_by_another = forms.ChoiceField(choices=TAUGHT_BY_ANOTHER_OPTIONS)
    other_instructor = forms.CharField(required=False)

    def clean_other_instructor(self):
        taught_by_another = self.cleaned_data['taught_by_another']
        other_instructor = self.cleaned_data['other_instructor'].strip()

        if taught_by_another == 'another' and other_instructor == '':
            raise ValidationError(_("Please enter the instructor's name"), code="invalid")

        return other_instructor


class EmailNewTeacherForm(forms.Form):
    """Compose box for emailing the new teacher named on a changed section.

    Every rejection lives here rather than in the view, so a crafted POST is
    checked identically to a modal submission.
    """

    # Each label carries its own explanation because the two options differ in
    # what they *create*, not just in wording — a reader cannot tell them apart
    # from the choice text alone.
    MODE_CHOICES = (
        ('start_app', mark_safe(
            'Send a link to start an application'
            '<small class="form-text text-muted">'
            'Your message includes a link to the public application form. '
            'The teacher enters their own name and email to begin. '
            'Nothing is created now.'
            '</small>')),
        ('invite', mark_safe(
            'Create an invitation for this teacher'
            '<small class="form-text text-muted">'
            'Creates an applicant account from the name and email on this '
            'section, and your message links straight to it — the teacher '
            'confirms this address and sets a password without re-entering '
            'their details. Use this only when you are confident the address '
            'is correct.'
            '</small>')),
    )

    section_index = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    recipient = forms.EmailField(
        label='To',
        widget=forms.EmailInput(attrs={'class': 'form-control'}))
    subject = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        validators=[validate_html_short_code])
    message = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
        validators=[validate_html_short_code])
    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        initial='start_app',
        label='How should this teacher reach the application?',
        help_text='Both options send the message you have written above.',
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

    def clean(self):
        cleaned = super().clean()
        # `section` is only meaningful on a fully valid form — a caller that
        # reads it must not see a resolved section from a rejected submission.
        if self.errors:
            self.section = None
        return cleaned
