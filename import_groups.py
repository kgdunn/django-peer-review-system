from basic.models import Person, Course, Group, GroupEnrolled, Group_Formation_Process

targ_course = Course.objects.get(label='66765')  # where we will copy to
gfp = Group_Formation_Process.objects.get(id=2)

import csv
with open('course-list.csv') as csvfile:
    reader = csv.DictReader(csvfile)
    #
    for row in reader:
        first = row['FirstName']
        last = row['LastName']
        display_name = '{0} {1}'.format(first, last)
        #
        students = Person.objects.filter(email=row['Email'].lower())
        if students.count():
            student = students[0]
        else:
            student = Person(is_validated = False,
                             email = row['Email'],
                             display_name = display_name,
                             official_name = display_name,
                             role = 'Learn',
                                     course = targ_course,
                             initials = first[0]+last[0],)
            student.save()
            student.user_ID = 'Stu-{0}'.format(student.id)
            student.save()
            print('Added student: {}'.format(student) )
#
        # Now enroll the student in a group
        group_name = row['GroupName']
        name = 'CE-P1-{}'.format(group_name)
        groups = Group.objects.filter(name=name)
        if groups.count():
            group = groups[0]
        else:
            group = Group(name=name, capacity=5, gfp=gfp)
            group.save()
#
        enrolled = student.groupenrolled_set.filter(group__gfp=gfp,
                                                    is_enrolled=True)
        if enrolled.count():
            enrolled.delete()
            print('Student was ALREADY ENROLLED; deleted and about to change')
#
        enrollment = GroupEnrolled(person=student,
                                   group=group,
                                   is_enrolled=True)
        enrollment.save()
        #
        print('Student: {} enrolled in group {}'.format(student, enrollment))
print('=====FINISHED=====')