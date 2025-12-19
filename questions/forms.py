# questions/forms.py

from django import forms
from .models import QuestionUpload, QuestionPaper
from registration.models import CAT_CHOICES
from .services import is_encrypted_dat, decrypt_dat_content, load_questions_from_excel_data

class QuestionUploadForm(forms.ModelForm):
    decryption_password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter decryption password',
            'class': 'form-control'
        }),
        help_text="Password required for encrypted DAT files"
    )
    
    category = forms.ChoiceField(
        choices=CAT_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = QuestionUpload
        fields = ["file", "decryption_password", "category"]
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'})
        }

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get("file")
        password = cleaned_data.get("decryption_password")

        if file and password:
            try:
                # Read file content into memory
                file.seek(0)
                file_content = file.read()
                file.seek(0)  # Reset file pointer

                # Basic validation - check if it looks like encrypted data
                if not is_encrypted_dat(file_content):
                    raise forms.ValidationError(
                        "File does not appear to be encrypted. Expected encrypted DAT file."
                    )

                # Test decryption with provided password
                try:
                    decrypted_data = decrypt_dat_content(file_content, password)
                    
                    # Verify it's a valid Excel file by checking magic bytes
                    if not decrypted_data.startswith(b'PK'):
                        raise forms.ValidationError(
                            "Decrypted data is not a valid Excel file format."
                        )
                    
                    # Try to parse the Excel data to validate structure
                    try:
                        questions = load_questions_from_excel_data(decrypted_data)
                        if not questions:
                            raise forms.ValidationError(
                                "No valid questions found in the Excel file."
                            )
                        
                        # Store for later use in signals
                        cleaned_data['validated_questions_count'] = len(questions)
                        
                    except Exception as e:
                        raise forms.ValidationError(
                            f"Error parsing Excel structure: {str(e)}"
                        )
                    
                except ValueError as e:
                    raise forms.ValidationError(
                        f"Decryption failed: {str(e)}. Please check your password."
                    )
                
                # Store file content for later use
                cleaned_data['file_content'] = file_content
                
            except forms.ValidationError:
                raise  # Re-raise form validation errors
            except Exception as e:
                raise forms.ValidationError(
                    f"Error processing file: {str(e)}"
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set the password from form data
        if 'decryption_password' in self.cleaned_data:
            instance.decryption_password = self.cleaned_data['decryption_password']
        
        instance.category = self.cleaned_data.get('category')
        
        if commit:
            instance.save()
        
        return instance


# ---------------------------------------------------------
# Admin ModelForm: QuestionPaperAdminForm
# The logic to disable the `trade` field for 'Secondary' papers is removed
# as 'Secondary' papers are no longer supported.
# ---------------------------------------------------------
class QuestionPaperAdminForm(forms.ModelForm):
    class Meta:
        model = QuestionPaper
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from reference.models import Trade
            tech_jco_codes = ["JE NE", "JE SYS", "OCC", "TTC", "OSS", "OP CIPH"]
            tech_or_codes = ["OCC", "TTC", "OSS", "OP CIPH"]
            all_codes = list(Trade.objects.values_list("code", flat=True))
            nontech_codes = [code for code in all_codes if code not in tech_jco_codes]
            cat_val = self.data.get("category") or (self.initial.get("category") if hasattr(self, "initial") else None) or (self.instance.category if self.instance else None)
            if cat_val == "JCOs (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)":
                self.fields["trade"].queryset = Trade.objects.filter(code__in=tech_jco_codes).order_by("name")
            elif cat_val == "OR (All tdes less Dvr MT,DR,EFS,Lmn and Tdn)":
                self.fields["trade"].queryset = Trade.objects.filter(code__in=tech_or_codes).order_by("name")
            elif cat_val == "JCOs/OR (Dvr MT,DR,EFS,Lmn and Tdn)":
                self.fields["trade"].queryset = Trade.objects.filter(code__in=nontech_codes).order_by("name")
        except Exception:
            pass
