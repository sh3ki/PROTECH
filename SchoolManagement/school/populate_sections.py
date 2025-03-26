from school.models import School, Section  # Adjust based on your app name

def populate_sections():
    # Clear existing sections if needed (Optional)
    Section.objects.all().delete()

    # Fetch all schools
    schools = School.objects.all()
    for school in schools:
        for grade in range(7, 13):  # Grade 7 to 12 (13 exclusive)
            for section_number in range(1, 6):  # Section 1 to 5
                section_name = f"Section {section_number}"
                Section.objects.create(
                    grade=grade,
                    name=section_name,
                    school=school
                )
    print("Sections populated successfully!")

# Run using Django shell:
# python manage.py shell < populate_sections.py
