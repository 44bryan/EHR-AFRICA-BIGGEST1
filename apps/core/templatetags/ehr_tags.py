from django import template

register = template.Library()


@register.filter
def split(value, sep=','):
    """Split a string by a separator. Usage: "a,b,c"|split:"," """
    if value is None:
        return []
    return str(value).split(sep)


@register.filter
def get_item(dictionary, key):
    """Look up a key in a dict. Usage: mydict|get_item:"some_key" """
    if not isinstance(dictionary, dict):
        return ''
    return dictionary.get(str(key), '')
