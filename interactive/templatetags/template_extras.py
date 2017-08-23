from django import template

register = template.Library()


@register.filter(name='keyvalue')
def keyvalue(dictn, key):
    try:
        return dictn[key]
    except KeyError:
        return ''