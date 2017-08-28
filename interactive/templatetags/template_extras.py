from django import template

register = template.Library()


@register.filter(name='keyvalue')
def keyvalue(dictn, key):
    try:
        return dictn[key]
    except KeyError:
        return ''


@register.filter(name='getfield')
def getfield(obj, field):
    return getattr(obj, field, default='')
