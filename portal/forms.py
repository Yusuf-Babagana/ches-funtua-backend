from django import forms


class LoginForm(forms.Form):
    """
    Plain Django form for the session-authenticated login page. Field name
    is `email` (not `username`) to match users.User.USERNAME_FIELD, but the
    view still calls Django's authenticate(username=..., password=...) --
    Django's ModelBackend resolves that kwarg against USERNAME_FIELD
    regardless of what it's called here.
    """
    email = forms.EmailField(
        label='Email address',
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'autocomplete': 'email',
            'placeholder': 'you@example.com',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': '••••••••',
        }),
    )
