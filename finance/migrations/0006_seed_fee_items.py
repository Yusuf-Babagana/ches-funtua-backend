from django.db import migrations

# The 16 named fees from the CHESF Student Portal Digest (excluding the
# School Registration/Tuition Fee, which is already the existing
# FeeStructure/Invoice tuition flow and is left untouched). No pricing is
# seeded here -- FeeItem.current_charge() returns None until the Bursar
# creates a real, active FeeItemCharge, so nothing becomes payable by
# accident from this migration alone.
FEE_ITEMS = [
    ('accommodation', 'Accommodation Fee', True, False),
    ('exam_first_semester', '1st Semester Exam Fee', False, False),
    ('exam_second_semester', '2nd Semester Exam Fee', False, False),
    ('index', 'Index Fee', False, True),
    ('practical', 'Practical Fee', False, True),
    ('departmental_registration', 'Departmental Registration', False, False),
    ('uniform_id_card', 'Student Uniform and ID Card Fee', False, False),
    ('tag_necktie', 'Student Tag and Necktie', True, False),
    ('course_material', 'Course Material', True, False),
    ('mssn_fcs', 'MSSN/FCS', False, False),
    ('nakats', 'NAKATS', False, False),
    ('src', 'SRC', False, False),
    ('project', 'Project Fee', False, False),
    ('board_exam', 'Board Exam', False, False),
    ('national_exam', 'National Exam', False, False),
    ('result_collection', 'Result Collection Fee', False, False),
]


def seed_fee_items(apps, schema_editor):
    FeeItem = apps.get_model('finance', 'FeeItem')
    for code, name, is_optional, requires_selection in FEE_ITEMS:
        FeeItem.objects.get_or_create(
            code=code,
            defaults={'name': name, 'is_optional': is_optional, 'requires_selection': requires_selection, 'is_active': True},
        )


def unseed_fee_items(apps, schema_editor):
    FeeItem = apps.get_model('finance', 'FeeItem')
    FeeItem.objects.filter(code__in=[code for code, *_ in FEE_ITEMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_feeitem_invoice_course_registration_invoice_fee_item_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_fee_items, unseed_fee_items),
    ]
