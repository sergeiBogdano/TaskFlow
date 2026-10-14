"""Parse untrusted model output as data. No tools, URLs, SQL or file operations."""
import json
import re
from datetime import date


def note_requested(message):
    return bool(re.search(r'\b(?:создай|создать|подготовь|напиши|сделай)\b[^\n]{0,70}\bзаметк\w*', message.casefold()))


def task_requested(message):
    return bool(re.search(r'\b(?:создай|создать|подготовь|сделай|добавь)\b[^\n]{0,70}\bзадач\w*', message.casefold()))


def mentioned(name, message):
    table = str.maketrans(dict(zip('абвгдежзийклмнопрстуфыэ', 'abvgdejziyklmnoprstufye')))
    def normalize(text):
        return text.casefold().replace('ё', 'е').replace('ь', '').replace('ъ', '').replace('ю', 'yu').replace('я', 'ya').replace('ц', 'ts').replace('ч', 'ch').replace('ш', 'sh').replace('щ', 'sch').translate(table)
    # Recognize Russian inflection and common Sergei/Sergey spellings, but only a
    # unique member match can be assigned. IDs alone never grant an assignment.
    name_tokens = [normalize(token).rstrip('iyuea') for token in re.findall(r'[\w.-]+', name) if len(token) >= 3]
    message_tokens = {normalize(token).rstrip('iyuea') for token in re.findall(r'[\w.-]+', message)}
    return bool(name_tokens) and all(len(token) >= 3 and token in message_tokens for token in name_tokens)


def decode_draft(answer):
    try:
        data = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', answer.strip()))
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def note_draft(answer):
    data = decode_draft(answer)
    if not isinstance(data.get('title'), str) or not data['title'].strip() or not isinstance(data.get('content'), str):
        return None
    # Markdown is inert text; never accept model-supplied HTML or storage/action flags.
    return {'title': data['title'].strip()[:200], 'content': data['content'][:100000], 'format': 'markdown'}


def task_fields(answer, message, fields, members, clients):
    data, result = decode_draft(answer), {}
    for key, acl, choices in [('assignee_id', 'assignee', members), ('client_id', 'client', clients)]:
        value = data.get(key)
        matches = [item['id'] for item in choices if mentioned(item['name'], message)]
        if fields.get(acl) == 'edit' and type(value) is int and matches == [value]:
            result[key] = value
    value = data.get('deadline')
    # Absolute dates explicitly supplied by the user are safe. Do not invent a time.
    if fields.get('deadline') == 'edit' and isinstance(value, str) and value in message:
        try:
            result['deadline'] = date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    if fields.get('priority') == 'edit' and data.get('priority') in ('low', 'medium', 'high', 'critical'):
        labels = {'low': r'низк\w*\s+приоритет', 'medium': r'средн\w*\s+приоритет', 'high': r'высок\w*\s+приоритет', 'critical': r'критич\w*\s+приоритет'}
        if re.search(labels[data['priority']], message.casefold()):
            result['priority'] = data['priority']
    return result
