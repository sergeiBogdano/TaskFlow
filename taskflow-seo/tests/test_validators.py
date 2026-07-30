import pytest

from app.core.utils.validators import parse_add_command, AddTaskResult


class TestParseAddCommand:

    def test_simple_title(self):
        result = parse_add_command('Написать статью')
        assert result.title == 'Написать статью'
        assert result.tags == []
        assert result.deadline_raw is None

    def test_with_tags(self):
        result = parse_add_command('Написать статью #seo #важно')
        assert result.title == 'Написать статью'
        assert 'seo' in result.tags
        assert 'важно' in result.tags

    def test_with_deadline(self):
        result = parse_add_command('Написать статью ~завтра 18:00')
        assert result.title == 'Написать статью'
        assert result.deadline_raw == 'завтра 18:00'

    def test_with_domain_tag(self):
        result = parse_add_command('Проверить сайт #spbpack.net')
        assert result.client_domain == 'spbpack.net'
        assert result.title == 'Проверить сайт'

    def test_with_all(self):
        result = parse_add_command('Написать статью #spbpack.net #seo ~завтра 18:00')
        assert result.title == 'Написать статью'
        assert result.client_domain == 'spbpack.net'
        assert 'seo' in result.tags
        assert result.deadline_raw == 'завтра 18:00'

    def test_empty_text(self):
        result = parse_add_command('')
        assert result.title == ''
