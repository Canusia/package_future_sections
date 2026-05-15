from django import forms
from django.core.exceptions import ValidationError

from cis.models.course import CourseAdministrator


class _MentorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        u = obj.user
        full_name = f'{u.first_name} {u.last_name}'.strip() or u.username
        return f'{full_name} <{u.email}>' if u.email else full_name


class SectionRequestReviewForm(forms.Form):
    DECISION_CHOICES = [
        ('approved', 'Approved'),
        ('not_approved', 'Not approved'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect,
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
    )
    existing_mentor = _MentorChoiceField(
        queryset=CourseAdministrator.objects.none(),
        required=False,
        label='Mentor',
    )
    new_mentor_name = forms.CharField(required=False, label='New Mentor Name')
    new_mentor_email = forms.EmailField(required=False, label='New Mentor Email')

    def __init__(self, *args, course=None, mentor_role='Faculty',
                 require_mentor=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        self.mentor_role = mentor_role
        self.require_mentor = require_mentor
        if course is not None and require_mentor:
            qs = CourseAdministrator.objects.filter(
                course=course, role=mentor_role, status='Active',
            ).select_related('user')
            self.fields['existing_mentor'].queryset = qs
            self.has_existing_options = qs.exists()
        else:
            self.has_existing_options = False

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get('decision')
        if decision != 'approved' or not self.require_mentor:
            return cleaned
        if self.has_existing_options:
            if not cleaned.get('existing_mentor'):
                self.add_error('existing_mentor',
                               ValidationError('Please select a mentor.'))
        else:
            if not cleaned.get('new_mentor_name'):
                self.add_error('new_mentor_name',
                               ValidationError('Required when no existing mentor exists.'))
            if not cleaned.get('new_mentor_email'):
                self.add_error('new_mentor_email',
                               ValidationError('Required when no existing mentor exists.'))
        return cleaned
