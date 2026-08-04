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


@register.filter
def merge_dict(d1, d2):
    """
    Merge two dicts safely, d1 values have priority over d2.
    Usage: rd|merge_dict:d  → rd's keys override d's keys.
    Safe filter argument — never raises VariableDoesNotExist.
    """
    if not isinstance(d1, dict):
        d1 = {}
    if not isinstance(d2, dict):
        d2 = {}
    return {**d2, **d1}


@register.filter
def getattribute(obj, attr):
    """Get an attribute from an object by name. Usage: object|getattribute:"field_name" """
    return getattr(obj, str(attr), 'NT')


@register.filter
def dictfirst(dictionary, keys_str):
    """
    Return the first non-empty value from a dict for any of the comma-separated keys.
    Safe to use as a filter argument — never raises VariableDoesNotExist.
    Usage: dd|dictfirst:"key1,key2,key3"
    """
    if not isinstance(dictionary, dict):
        return ''
    for key in keys_str.split(','):
        val = dictionary.get(key.strip())
        if val is not None and val != '':
            return val
    return ''
