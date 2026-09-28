import re

from django.core.management.base import BaseCommand

from users.models import Student

# Matches a 2- or 4-digit admission year as a standalone segment of the
# matric number, e.g. "CHE/25/100/001", "2025/CHE/001", "CHE-25-001".
YEAR_TOKEN_RE = re.compile(r'(?<!\d)(20)?(\d{2})(?!\d)')


class Command(BaseCommand):
    help = (
        "Corrects student.level based on the admission year embedded in "
        "matric_number: 2025-cohort students -> 200L, 2024-cohort students "
        "-> 300L. Runs as a dry-run (prints what would change) unless "
        "--apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually save the changes. Without this, only a preview is printed.',
        )

    def _year_for(self, matric_number):
        """Return the 2-digit admission year found in matric_number, or None."""
        for match in YEAR_TOKEN_RE.finditer(matric_number):
            century, yy = match.groups()
            if century == '20' or yy in ('24', '25'):
                return yy
        return None

    def handle(self, *args, **options):
        apply_changes = options['apply']
        target_level = {'25': '200', '24': '300'}

        changes = []
        skipped = []
        for student in Student.objects.select_related('user').order_by('matric_number'):
            yy = self._year_for(student.matric_number)
            new_level = target_level.get(yy)
            if new_level is None:
                continue
            if student.level == new_level:
                continue
            changes.append((student, new_level))

        if not changes:
            self.stdout.write(self.style.WARNING(
                'No students found whose level disagrees with their matric-number year.'
            ))
            return

        for student, new_level in changes:
            self.stdout.write(
                f"{student.matric_number}  {student.user.get_full_name():30s} "
                f"level {student.level} -> {new_level}"
            )

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f"\nDRY RUN: {len(changes)} student(s) would be updated. "
                "Re-run with --apply to save these changes."
            ))
            return

        for student, new_level in changes:
            student.level = new_level
            student.save(update_fields=['level'])

        self.stdout.write(self.style.SUCCESS(f"\nUpdated {len(changes)} student(s)."))
