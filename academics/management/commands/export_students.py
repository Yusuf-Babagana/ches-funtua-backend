import csv
from django.core.management.base import BaseCommand
from users.models import Student

class Command(BaseCommand):
    help = 'Export all students data to a CSV file'

    def handle(self, *args, **options):
        # Define the path for the export file
        file_path = 'all_students_data.csv'
        
        # Define the fields you want to retrieve
        headers = ['Full Name', 'Matric Number', 'Department', 'Level', 'Status']
        
        students = Student.objects.select_related('user', 'department').all()
        
        with open(file_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            
            for student in students:
                writer.writerow([
                    student.user.get_full_name(),
                    student.matric_number,
                    student.department.name if student.department else "N/A",
                    student.level,
                    student.status
                ])
        
        self.stdout.write(self.style.SUCCESS(f'Successfully exported {students.count()} students to {file_path}'))
