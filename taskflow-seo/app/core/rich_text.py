"""One safe rich-text format for tasks, comments, notes and client notes."""
import nh3
from fastapi import HTTPException

MAX_RICH_TEXT = 100_000
TAGS = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'blockquote', 'pre', 'code', 'hr', 'a'}


def clean_html(value, *, enforce=True):
    if value is None:
        return value
    if not isinstance(value, str) or (enforce and len(value) > MAX_RICH_TEXT):
        raise HTTPException(400, f'Текст: максимум {MAX_RICH_TEXT} символов')
    return nh3.clean(value, tags=TAGS, attributes={'a': {'href', 'title'}},
                     url_schemes={'http', 'https', 'mailto'}, link_rel='noopener noreferrer')


def clean_payload(value):
    if isinstance(value, list):
        return [clean_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in ('notes', 'comment', 'content', 'client_notes') and isinstance(item, str) and value.get('format', 'html') == 'html':
            result[key] = clean_html(item, enforce=False)
        else:
            result[key] = clean_payload(item)
    return result
