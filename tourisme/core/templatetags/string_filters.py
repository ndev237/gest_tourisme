"""
core/templatetags/string_filters.py
====================================
Filtres de template personnalisés pour la manipulation de chaînes.
"""

from django import template

register = template.Library()


@register.filter(name='split')
def split(value, separator=','):
    """Découpe une chaîne sur un séparateur et retourne la liste."""
    if value is None:
        return []
    return str(value).split(separator)
