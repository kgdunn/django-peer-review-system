from django import template
register = template.Library()

from django.utils import timezone
from html.parser import HTMLParser
import re

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


@register.filter(name='date_urgency_style')
def date_urgency_style(value, relative_to=timezone.now):
    """
    Formatting style returned by 'urgency' (closeness to another datetime)
    """
    if not(isinstance(value, timezone.datetime)):
        return ''

    if isinstance(relative_to, timezone.datetime):
        pass
    elif hasattr(relative_to, '__call__'):
        relative_to = relative_to()
    else:
        relative_to = timezone.now()

    deviation = value - relative_to

    if deviation.days<0:
        return ('color: #FF0000; font-weight: 900; '
                'border: red; border-width: 5px;  border-style: solid;')
    elif deviation.days>10:
        return 'color: lightpink; font-weight: 100;'
    elif deviation.days>9:
        return 'color: lightpink; font-weight: 200;'
    elif deviation.days>8:
        return 'color: pink; font-weight: 300;'
    elif deviation.days>7:
        return 'color: pink; font-weight: 400;'
    elif deviation.days>6:
        return 'color: palevioletred; font-weight: 500;'
    elif deviation.days>5:
        return 'color: palevioletred; font-weight: 600;'
    elif deviation.days>4:
        return 'color: indianred; font-weight: 700;'
    elif deviation.days>3:
        return 'color: indianred; font-weight: 800;'
    elif deviation.days>2:
        return 'color: hotpink; font-weight: 800;'
    elif deviation.days>1:
        return 'color: hotpink; font-weight: 800;'
    elif deviation.days>=0:
        return 'color: orangered; font-weight: 800;'



@register.filter(name='getfield')
def getfield(obj, field):
    return getattr(obj, field, default='')

@register.filter('slicestr')
def slicestr(value, sliceamount):
    """ Returns the fraction of the string, specified in ``sliceamount``.

    {{some_string|slicestr:"5:9"}}

    will return `onar` if ``some_string`` was "dictionary"

    """
    start, end = sliceamount.split(':')
    return value[int(start):int(end)]


@register.filter('startswith')
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False


class MLStripper(HTMLParser):
    """
    From:
    https://stackoverflow.com/questions/11061058/using-htmlparser-in-python-3-2
    """
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


@register.filter('sortorder')
def sortorder(obj):
    """
    Trys to smartly determine the sort order for this object ``obj``
    """
    if hasattr(obj, 'last'):
        return obj.last.timestamp()

    if isinstance(obj, str):
        # First assume pure numeric
        try:
            return float(obj)
        except ValueError:
            pass

        # Assume it is of the form
        #   AB [N.M]   PPP words'
        try:
            return float(obj.split('[')[1].split(']')[0])
        except (IndexError, ValueError):
            return strip_tags(obj).strip()

    return None
