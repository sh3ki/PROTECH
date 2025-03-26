from django.contrib.auth.models import User
from django import forms
from .models import CustomUser


class AdminSigupForm(forms.ModelForm):
    class Meta:
        model=User
        fields=['first_name','last_name','username','password']

# for admin account
class CustomUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ['profile_picture', 'email', 'password', 'confirm_password',
                  'first_name', 'middle_name', 'last_name', 
                  'is_principal', 'is_guard', 'is_teacher', 
                  'school', 'section']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match!")
        return cleaned_data
