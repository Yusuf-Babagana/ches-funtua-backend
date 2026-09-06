"""
Shared registration-credit-unit thresholds.

Replaces three previously-inconsistent course-COUNT caps (2 unpaid / 15
paid on the student self-service path, 6 on the desk-officer manual
override path -- see college_cms_migration_inventory.md §6.1) with one
real credit-UNIT rule, used by both the DRF API (academics/views_*.py)
and the Django-template portal (portal/services_*.py) so the two layers
can't drift apart again. Preserves the existing payment-gate exception
in spirit: a smaller free allowance while unpaid, the real ceiling once
fees are paid.
"""

MAX_CREDIT_UNITS_UNPAID = 8
MAX_CREDIT_UNITS_PAID = 24
