from django.db import migrations


def seed_placeholders(apps, schema_editor):
    Program = apps.get_model('academics', 'Program')
    PracticalCenter = apps.get_model('academics', 'PracticalCenter')

    # Placeholder durations -- the "College Programs and Duration" list
    # referenced in the CHESF Student Portal Digest was never attached;
    # edit these (or add more programs) from the Django admin once the
    # real list is available.
    programs = [
        {'name': 'National Diploma', 'code': 'ND', 'program_type': 'nd', 'duration_semesters': 4},
        {'name': 'Professional Diploma', 'code': 'PD', 'program_type': 'pd', 'duration_semesters': 2},
    ]
    for data in programs:
        Program.objects.get_or_create(code=data['code'], defaults=data)

    # Placeholder centers -- the "Practical Centers" attachment referenced
    # in the digest was also never attached; edit/add real ones from the
    # Django admin.
    centers = [
        {'name': 'Main Campus Practical Center', 'location': 'CHES Funtua Main Campus'},
        {'name': 'Affiliated Teaching Hospital', 'location': 'To be confirmed'},
    ]
    for data in centers:
        PracticalCenter.objects.get_or_create(name=data['name'], defaults=data)


def unseed_placeholders(apps, schema_editor):
    Program = apps.get_model('academics', 'Program')
    PracticalCenter = apps.get_model('academics', 'PracticalCenter')
    Program.objects.filter(code__in=['ND', 'PD']).delete()
    PracticalCenter.objects.filter(name__in=[
        'Main Campus Practical Center', 'Affiliated Teaching Hospital',
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0012_practicalcenter_program_indexinformation_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_placeholders, unseed_placeholders),
    ]
