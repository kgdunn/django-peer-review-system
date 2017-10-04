from django import template

register = template.Library()


@register.filter(name='keyvalue')
def keyvalue(dictn, key):
    """
    Use as follows in the template:


       {% load template_extras %}   <--- the name of this Python file
       dictvar|keyvalue:key_name

    will fetch the value of the ``key_name`` from dictionary ``dictvar``
    """
    try:
        return dictn[key]
    except KeyError:
        return ''


@register.filter(name='getfield')
def getfield(obj, field):
    return getattr(obj, field, default='')



@register.filter('startswith')
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False