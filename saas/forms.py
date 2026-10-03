"""Email-based account forms; normalize before validation and authentication."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .localization import text as translate


def normalized_email(value):
    return value.strip().lower()


class SignupForm(UserCreationForm):
    username = forms.EmailField(max_length=150)

    def clean_username(self):
        email = normalized_email(self.cleaned_data['username'])
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(translate('Ce compte existe déjà. Connectez-vous.'))
        return email


class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self):
        return normalized_email(self.cleaned_data['username'])
