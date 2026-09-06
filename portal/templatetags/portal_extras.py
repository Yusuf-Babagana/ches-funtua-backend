from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter(name='naira')
def naira(value):
    """
    Format a number as Nigerian Naira, e.g. 125000 -> "₦125,000.00".
    Mirrors the frontend's Intl.NumberFormat('en-NG', {style:'currency',
    currency:'NGN'}) convention used throughout the old Next.js dashboards,
    so figures look the same after the migration.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return value
    return f'₦{amount:,.2f}'


@register.filter(name='role_label')
@stringfilter
def role_label(value):
    """'desk-officer' -> 'Desk Officer', 'hod' -> 'Hod' (title-cased, hyphens as spaces)."""
    return value.replace('-', ' ').replace('_', ' ').title()
