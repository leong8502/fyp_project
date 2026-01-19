from django import template
import re

register = template.Library()

@register.filter(name='split')
def split(value, arg):
    """Split a string by the given separator."""
    if value:
        return [item.strip() for item in value.split(arg) if item.strip()]
    return []

@register.filter
def mask_account_in_description(value):
    """
    Masks account numbers only show last 4 digits
    """
    if not isinstance(value, str):
        return value
        
    # Pattern to find digits inside parentheses: (12345)
    pattern = r'\((\d+)\)'
    
    def replace_match(match):
        full_number = match.group(1)
        if len(full_number) <= 4:
            masked = "****"
        else:
            masked = "****" + full_number[-4:]
        return f"({masked})"
        
    return re.sub(pattern, replace_match, value)
