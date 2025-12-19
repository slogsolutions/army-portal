from django.contrib import admin
from .models import ExamDayAvailability, Shift

# @admin.register(ExamDayAvailability)
# class ExamDayAvailabilityAdmin(admin.ModelAdmin):
#     list_display = ['date']
#     filter_horizontal = ['trades']  # if categories is ManyToMany


# admin.py
from django import forms
from django.contrib import admin
from exams.models import Shift
from registration.models import CandidateProfile, CAT_CHOICES


class ShiftAdminForm(forms.ModelForm):
    category_selector = forms.ChoiceField(
        choices=[("", "-- Select Category --")] + list(CAT_CHOICES),
        required=False,
        help_text="Pick a category to assign candidates by category. Or leave blank to assign manually."
    )
    all_categories = forms.BooleanField(
        required=False,
        label="All Categories",
        help_text="Tick this to assign ALL candidates to this shift, ignoring category."
    )

    class Meta:
        model = Shift
        fields = "__all__"


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    form = ShiftAdminForm
    list_display = ("exam_center", "date", "start_time")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        category = form.cleaned_data.get("category_selector")
        all_categories = form.cleaned_data.get("all_categories")

        if all_categories:
            # assign all candidates to this shift
            CandidateProfile.objects.update(shift=obj)
        elif category:
            # assign only candidates of selected category
            CandidateProfile.objects.filter(cat=category).update(shift=obj)
