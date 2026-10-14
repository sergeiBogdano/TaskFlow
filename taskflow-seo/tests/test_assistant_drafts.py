import json
from app.core.assistant_drafts import note_draft, note_requested, task_fields


def test_note_output_is_inert_and_actions_are_discarded():
    draft = note_draft(json.dumps({'title': 'Заметка', 'content': '```python\nimport os\n```', 'format': 'html', 'path': '/etc/passwd', 'action': 'save', 'is_public': True}))
    assert draft == {'title': 'Заметка', 'content': '```python\nimport os\n```', 'format': 'markdown'}
    assert note_draft('{"title":"x","content":{"command":"run"}}') is None
    assert note_requested('Создай заметку о встрече')
    assert not note_requested('Проанализируй мои заметки')


def test_task_fields_allow_only_unique_requested_workspace_entities():
    fields = {'assignee': 'edit', 'client': 'edit', 'deadline': 'edit', 'priority': 'edit'}
    members = [{'id': 2, 'name': 'sergei'}]
    clients = [{'id': 5, 'name': 'мембраны'}]
    answer = '{"assignee_id":2,"client_id":5,"deadline":"2026-10-21","priority":"high","command":"rm -rf /"}'
    request = 'Создай задачу Сергею написать 5 статей на сайт мембраны, срок 2026-10-21, высокий приоритет'
    assert task_fields(answer, request, fields, members, clients) == {'assignee_id': 2, 'client_id': 5, 'deadline': '2026-10-21', 'priority': 'high'}
    assert task_fields(answer, 'Неизвестному написать статьи', fields, members, clients) == {}
    assert task_fields(answer, request, {}, members, clients) == {}
    assert task_fields(answer, request, fields, members + [{'id': 3, 'name': 'Сергей'}], clients).get('assignee_id') is None
    assert task_fields('{"assignee_id":999}', request, fields, members, clients) == {}
