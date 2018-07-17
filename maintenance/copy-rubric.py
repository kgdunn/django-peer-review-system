# ------
# To copy the rubric from one template, to another.
# Assumes both rubric templates have been created, but that the destination
# template (``dst_template``) has no items and options (yet). The items and
# options from the source template (``src_template``) will be copied over.

from rubric.models import RubricTemplate, RItemTemplate
src_template = RubricTemplate.objects.get(id=121)
dst_template = RubricTemplate.objects.get(id=123)

src_items = RItemTemplate.objects.filter(r_template=src_template)
for item in src_items:
    # First get the associated options
    options = item.roptiontemplate_set.all()
    # Then copy the parent template to the new one
    item.pk = None
    item.r_template = dst_template
    item.save()
    # Then re-parent the options to the newly created/saved item
    for opt in options:
        opt.pk = None
        opt.rubric_item = item
        opt.save()
    # All done with options
# Done with all items
print('--Done--')



