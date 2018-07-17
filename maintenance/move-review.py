from basic.models import Person, EntryPoint, Course
from rubric.models import RubricActual
from interactive.models import Membership, ReviewReport

course = Course.objects.get(label='67174')
entry_point = EntryPoint.objects.get(course=course, LTI_id='1371427444')


# A review has been assigned, but for whatever reason it needs to be decoupled.
# Remove SS (submitting student) from RS (reviewing student)
submitter = Person.objects.get(email='submitting.student@student.tudelft.nl')
reviewer =  Person.objects.get(email='reviewing.student@student.tudelft.nl')

checks_only = False

rubrics = RubricActual.objects.filter(submission__submitted_by=submitter)
rubrics = rubrics.filter(graded_by=reviewer, submitted=False, score=0)
rubrics = rubrics.filter(rubric_template__entry_point=entry_point)
assert(rubrics.count()==1)
ra = rubrics[0]
assert(ra.score==0)
assert(ra.word_count==0)


reports = ReviewReport.objects.filter(entry_point=entry_point,
                                      reviewer=reviewer,
                                      submission=ra.submission)
assert(reports.count()==1)
rr = reports[0]


memberships = Membership.objects.filter(role='Review',
                                        group=rr.grpconf,
                                        learner=reviewer)
assert(memberships.count()==1)
mem = memberships[0]


ritems = ra.ritemactual_set.all()

group = mem.group
sub = rr.submission

assert(mem.role == 'Review')
assert(group == rr.grpconf)
assert(sub == ra.submission)
assert(rr.unique_code == ra.rubric_code)
for item in ritems:
    # Assert the user has not started using this rubric
    assert(item.roptionactual_set.filter().count() == 0)

print('About to process: mem={}; rr={}; ra={}'.format(mem.id, rr.id, ra.id))


# If checks pass, now we can remove things
if not(checks_only):
    print('ReviewReport modify: {}'.format(rr))
    rr.submission = None
    rr.grpconf = None
    rr.save()
    #
    print('DELETE Membership: {}'.format(mem))
    mem.delete()
    #
    print('DELETE RA: {}'.format(ra))
    _ = ra.delete()
    print(_)
    #
    print('Successfully modified/delete')
