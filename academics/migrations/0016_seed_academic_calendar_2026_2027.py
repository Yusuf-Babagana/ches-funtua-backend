from datetime import date

from django.db import migrations

SESSION = '2026/2027'
NEXT_SESSION = '2027/2028'

# Each tuple: (level, semester, order, activity, start_date, end_date, duration_text, notes)
# Transcribed from the CHES Funtua Office of the Academic Secretary calendar
# for the 2026/2027 session. Multi-line "Consideration of result" blocks in
# the source tables are split into one event per sub-activity.
EVENTS = [
    # ---- 100L First Semester (Fresh Students) ----
    ('100', 'first', 1, 'Sales of Application Form', date(2026, 3, 2), None, '', ''),
    ('100', 'first', 2, 'New Intake Entrance Examination', date(2026, 6, 10), None, '', ''),
    ('100', 'first', 3, 'Marking of Entrance Examination', date(2026, 6, 24), None, '', ''),
    ('100', 'first', 4, 'Release of Admission', date(2026, 7, 10), None, '', ''),
    ('100', 'first', 5, 'Collection of Admission Letter', date(2026, 7, 13), None, '', ''),
    ('100', 'first', 6, 'School Registration', date(2026, 8, 3), date(2026, 9, 4), '4 weeks', ''),
    ('100', 'first', 7, 'Course Registration', date(2026, 8, 17), date(2026, 9, 11), '4 weeks', ''),
    ('100', 'first', 8, 'Late Registration', date(2026, 9, 7), date(2026, 9, 27), '3 weeks', ''),
    ('100', 'first', 9, 'Students Arrival on Campus', date(2026, 8, 21), None, '', ''),
    ('100', 'first', 10, 'Lectures', date(2026, 9, 28), date(2026, 12, 23), '13 weeks', ''),
    ('100', 'first', 11, 'Matriculation/Orientation', date(2026, 10, 17), None, '', ''),
    ('100', 'first', 12, '1st Semester Examination', date(2027, 1, 4), date(2027, 1, 8), '1 week', ''),
    ('100', 'first', 13, 'Marking of Examination', date(2027, 1, 14), date(2027, 1, 30), '', 'Consideration of result'),
    ('100', 'first', 14, 'Departmental Board of Studies', date(2027, 2, 5), None, '', 'Consideration of result'),
    ('100', 'first', 15, 'Academic Board of Studies', date(2027, 2, 10), None, '', 'Consideration of result'),
    ('100', 'first', 16, 'Release of 1st Semester Result', date(2027, 2, 15), None, '', 'Consideration of result'),
    ('100', 'first', 17, 'Total Duration of Academic Activities', None, None, '14 weeks', ''),

    # ---- 100L Second Semester (Returning Students) ----
    ('100', 'second', 1, 'Students Arrival on Campus', date(2027, 2, 15), None, '', ''),
    ('100', 'second', 2, 'Course Registration', date(2027, 2, 15), date(2027, 3, 5), '3 weeks', ''),
    ('100', 'second', 3, 'Lectures', date(2027, 2, 15), date(2027, 3, 5), '3 weeks', ''),
    ('100', 'second', 4, 'Eidel Fitr Break', date(2027, 3, 8), date(2027, 3, 12), '1 week', ''),
    ('100', 'second', 5, "Lectures Cont'd", date(2027, 3, 15), date(2027, 5, 14), '9 weeks', ''),
    ('100', 'second', 6, 'Eidel Kabeer Break', date(2027, 5, 15), date(2027, 5, 21), '1 week', ''),
    ('100', 'second', 7, '2nd Semester Examination', date(2027, 5, 24), date(2027, 5, 28), '1 week', ''),
    ('100', 'second', 8, 'Practical Attachment', date(2027, 6, 14), date(2027, 9, 3), '12 weeks', ''),
    ('100', 'second', 9, 'Marking of Examination', date(2027, 6, 4), date(2027, 6, 18), '', 'Consideration of result'),
    ('100', 'second', 10, 'Departmental Board of Studies', date(2027, 6, 25), None, '', 'Consideration of result'),
    ('100', 'second', 11, 'Academic Board of Studies', date(2027, 6, 30), None, '', 'Consideration of result'),
    ('100', 'second', 12, 'Release of 2nd Semester Result', date(2027, 7, 1), None, '', 'Consideration of result'),
    ('100', 'second', 13, 'Total Duration of Academic Activities', None, None, '13 weeks', ''),

    # ---- 200L First Semester (Returning Students) ----
    ('200', 'first', 1, 'Students Arrival on Campus', date(2026, 9, 21), None, '', ''),
    ('200', 'first', 2, 'Course Registration', date(2026, 9, 28), date(2026, 10, 9), '2 weeks', ''),
    ('200', 'first', 3, 'Lectures', date(2026, 9, 28), date(2026, 12, 23), '13 weeks', ''),
    ('200', 'first', 4, 'Christmas/New Year Break', date(2026, 12, 24), date(2027, 1, 4), '10 days', ''),
    ('200', 'first', 5, '1st Semester Examination', date(2027, 1, 4), date(2027, 1, 8), '1 week', ''),
    ('200', 'first', 6, 'Marking of Examination', date(2027, 1, 14), date(2027, 1, 30), '', 'Consideration of result'),
    ('200', 'first', 7, 'Departmental Board of Studies', date(2027, 2, 5), None, '', 'Consideration of result'),
    ('200', 'first', 8, 'Academic Board of Studies', date(2027, 2, 10), None, '', 'Consideration of result'),
    ('200', 'first', 9, 'Release of 1st Semester Result', date(2027, 2, 15), None, '', 'Consideration of result'),
    ('200', 'first', 10, 'Total Duration of Academic Activities', None, None, '14 weeks', ''),

    # ---- 200L Second Semester (Returning Students) ----
    ('200', 'second', 1, 'Students Arrival on Campus', date(2027, 2, 15), None, '', ''),
    ('200', 'second', 2, 'Course Registration', date(2027, 2, 15), date(2027, 3, 5), '3 weeks', ''),
    ('200', 'second', 3, "Lectures Cont'd", date(2027, 2, 15), date(2027, 3, 5), '3 weeks', ''),
    ('200', 'second', 4, 'Eidel Fitr Break', date(2027, 3, 8), date(2027, 3, 12), '1 week', ''),
    ('200', 'second', 5, "Lectures Cont'd", date(2027, 3, 15), date(2027, 5, 14), '9 weeks', ''),
    ('200', 'second', 6, 'Eidel Kabeer Break', date(2027, 5, 15), date(2027, 5, 21), '1 week', ''),
    ('200', 'second', 7, '2nd Semester Examination', date(2027, 5, 24), date(2027, 5, 28), '1 week', ''),
    ('200', 'second', 8, 'Practical Attachment', date(2027, 6, 14), date(2027, 9, 3), '12 weeks', ''),
    ('200', 'second', 9, 'Marking of Examination', date(2027, 6, 15), date(2027, 6, 29), '', 'Consideration of result'),
    ('200', 'second', 10, 'Departmental Board of Studies', date(2027, 7, 5), None, '', 'Consideration of result'),
    ('200', 'second', 11, 'Academic Board of Studies', date(2027, 7, 10), None, '', 'Consideration of result'),
    ('200', 'second', 12, 'Release of 2nd Semester Result', date(2027, 7, 14), None, '', 'Consideration of result'),
    ('200', 'second', 13, 'Total Duration of Academic Activities', None, None, '13 weeks', ''),

    # ---- 300L First Semester (Returning Students) ----
    ('300', 'first', 1, 'Students Arrival on Campus', date(2026, 11, 30), None, '', ''),
    ('300', 'first', 2, 'Course Registration', date(2026, 11, 30), date(2026, 12, 15), '2 weeks', ''),
    ('300', 'first', 3, 'Lectures', date(2026, 11, 30), date(2026, 12, 23), '3 weeks', ''),
    ('300', 'first', 4, 'Christmas/New Year Break', date(2026, 12, 24), date(2027, 1, 4), '10 days', ''),
    ('300', 'first', 5, "Lectures Cont'd", date(2027, 2, 15), date(2027, 3, 5), '3 weeks', ''),
    ('300', 'first', 6, 'Eidel Fitr Break', date(2027, 3, 8), date(2027, 3, 12), '1 week', ''),
    ('300', 'first', 7, "Lectures Cont'd", date(2027, 3, 15), date(2027, 4, 30), '7 weeks', ''),
    ('300', 'first', 8, '1st Semester Examination', date(2027, 5, 3), date(2027, 5, 7), '1 week', ''),
    ('300', 'first', 9, 'Marking of Examination', date(2027, 5, 14), date(2027, 5, 30), '', 'Consideration of result'),
    ('300', 'first', 10, 'Departmental Board of Studies', date(2027, 6, 5), None, '', 'Consideration of result'),
    ('300', 'first', 11, 'Academic Board of Studies', date(2027, 6, 10), None, '', 'Consideration of result'),
    ('300', 'first', 12, 'Release of 1st Semester Result', date(2027, 6, 15), None, '', 'Consideration of result'),
    ('300', 'first', 13, 'Total Duration of Academic Activities', None, None, '14 weeks', ''),

    # ---- 300L Second Semester (Returning Students) ----
    # Source table gives a 5-day course-registration/lectures window but
    # still labels "Lectures" as "3 weeks" -- transcribed faithfully as printed.
    ('300', 'second', 1, 'Students Arrival on Campus', date(2027, 5, 10), None, '', ''),
    ('300', 'second', 2, 'Course Registration', date(2027, 5, 10), date(2027, 5, 14), '1 week', ''),
    ('300', 'second', 3, 'Lectures', date(2027, 5, 10), date(2027, 5, 14), '3 weeks', ''),
    ('300', 'second', 4, 'Eidel Kabeer Break', date(2027, 5, 15), date(2027, 5, 21), '1 week', ''),
    ('300', 'second', 5, "Lectures Cont'd", date(2027, 5, 24), date(2027, 7, 23), '9 weeks', ''),
    ('300', 'second', 6, '2nd Semester Examination', date(2027, 7, 26), date(2027, 7, 30), '1 week', ''),
    ('300', 'second', 7, 'Marking of Examination', date(2027, 8, 1), date(2027, 8, 14), '', 'Consideration of result'),
    ('300', 'second', 8, 'Departmental Board of Studies', date(2027, 8, 20), None, '', 'Consideration of result'),
    ('300', 'second', 9, 'Academic Board of Studies', date(2027, 8, 25), None, '', 'Consideration of result'),
    ('300', 'second', 10, 'Release of 2nd Semester Result', date(2027, 8, 30), None, '', 'Consideration of result'),
    ('300', 'second', 11, 'Total Duration of Academic Activities', None, None, '13 weeks', ''),
]


def seed_calendar(apps, schema_editor):
    AcademicCalendarEvent = apps.get_model('academics', 'AcademicCalendarEvent')
    objs = [
        AcademicCalendarEvent(
            session=SESSION, level=level, semester=semester, order=order,
            activity=activity, start_date=start, end_date=end,
            duration_text=duration, notes=notes,
        )
        for level, semester, order, activity, start, end, duration, notes in EVENTS
    ]
    AcademicCalendarEvent.objects.bulk_create(objs)


def unseed_calendar(apps, schema_editor):
    AcademicCalendarEvent = apps.get_model('academics', 'AcademicCalendarEvent')
    AcademicCalendarEvent.objects.filter(session=SESSION).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0015_academiccalendarevent'),
    ]

    operations = [
        migrations.RunPython(seed_calendar, unseed_calendar),
    ]
