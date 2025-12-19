# forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import CandidateProfile
from reference.models import Trade

User = get_user_model()

class CandidateRegistrationForm(forms.ModelForm):
    username = forms.CharField(label="Username", required=True)
    password = forms.CharField(label="Password", widget=forms.PasswordInput, required=True)
    
    trade = forms.ModelChoiceField(
        queryset=Trade.objects.all().order_by("name"),
        empty_label="-- Select Trade --",
        widget=forms.Select(attrs={"class": "form-control"}),
        required=True
    )
    
    class Meta:
        model = CandidateProfile
        fields = [
            "army_no", "rank", "name", "trade_type", "trade", "dob", "doe", 
            "unit", "med_cat", "cat", "command",
            "nsqf_level", "exam_center", "training_center",
            "state", "district", "shift",
            "primary_qualification", "primary_duration", "primary_credits",
        ]
        widgets = {
            "doe": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if not username:
            raise forms.ValidationError("Username is required.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username
    
    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not password:
            raise forms.ValidationError("Password is required.")
        return password
    
    def clean_army_no(self):
        army_no = self.cleaned_data.get("army_no")
        if not army_no:
            raise forms.ValidationError("Army Number is required.")
        # Check if army_no already exists
        if CandidateProfile.objects.filter(army_no=army_no).exists():
            raise forms.ValidationError("This Army Number is already registered.")
        return army_no
    
    def clean_dob(self):
        dob = self.cleaned_data.get("dob")
        if not dob:
            raise forms.ValidationError("Date of Birth is required.")
        # Validate format dd-mm-yyyy
        import re
        if not re.match(r'^\d{2}-\d{2}-\d{4}$', dob):
            raise forms.ValidationError("Date of Birth must be in dd-mm-yyyy format.")
        return dob
    
    def clean(self):
        cleaned_data = super().clean()
        
        cat = cleaned_data.get("cat")
        trade_type = cleaned_data.get("trade_type")
        trade = cleaned_data.get("trade")
        
        from reference.models import Trade
        tech_jco_trades = ["JE NE", "JE SYS", "OCC", "TTC", "OSS", "OP CIPH"]
        tech_or_trades = ["OCC", "TTC", "OSS", "OP CIPH"]
        all_trades = list(Trade.objects.values_list("code", flat=True))
        nontech_trades = [code for code in all_trades if code not in tech_jco_trades]

        if cat and trade_type and trade:
            trade_code = trade.code.strip().upper()
            
            if cat == "JCOs (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)":
                if trade_type != "Tech" or trade_code not in tech_jco_trades:
                    raise forms.ValidationError("Invalid trade for JCOs Tech category.")
            elif cat == "OR (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)":
                if trade_type != "Tech" or trade_code not in tech_or_trades:
                    raise forms.ValidationError("Invalid trade for OR Tech category.")
            elif cat == "JCOs/OR (Dvr MT,DR,EFS,Lmn and Tdn)":
                if trade_type != "Non-Tech" or trade_code not in nontech_trades:
                    raise forms.ValidationError("Invalid trade for JCOs/OR Non-Tech category.")
        
        return cleaned_data

    def save(self, commit=True):
        # Create the User first
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        # create_user will hash the password
        user = User.objects.create_user(username=username, password=password)

        # Create CandidateProfile instance but don't save to DB yet
        candidate = super().save(commit=False)
        candidate.user = user

        if commit:
            candidate.save()
        return candidate


# -------------------------
# Admin Form for Marks Entry
# -------------------------
class CandidateMarksForm(forms.ModelForm):
    """Form specifically for entering marks with validation"""
    
    class Meta:
        model = CandidateProfile
        fields = [
            "primary_practical_marks", "primary_viva_marks",
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text based on trade
        if self.instance and self.instance.trade:
            trade_name = self.instance.trade.name.strip().upper()
            if trade_name in ["OCC", "DMV"]:
                self.fields['primary_practical_marks'].help_text = "Maximum: 20 marks"
                self.fields['primary_viva_marks'].help_text = "Maximum: 5 marks"
            else:
                self.fields['primary_practical_marks'].help_text = "Maximum: 30 marks"
                self.fields['primary_viva_marks'].help_text = "Maximum: 10 marks"
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Update instance with form data before validation
        instance = self.instance
        for field_name in ['primary_practical_marks', 'primary_viva_marks']:
            if field_name in cleaned_data:
                setattr(instance, field_name, cleaned_data[field_name])
        
        # Run model validation
        try:
            instance.full_clean()
        except ValidationError as e:
            # Convert model validation errors to form errors
            if hasattr(e, 'message_dict'):
                for field, messages in e.message_dict.items():
                    for message in messages:
                        self.add_error(field, message)
            else:
                raise forms.ValidationError(str(e))
        
        return cleaned_data
