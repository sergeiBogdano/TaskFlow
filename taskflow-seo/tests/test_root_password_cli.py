"""Root credentials are managed on the server, never through an HTTP session."""
import pytest
from sqlalchemy import select

from app.cli import rotate_root_password
from app.core.auth import hash_password, make_session_token, session_matches_user, verify_password
from app.core.models import User
from tests.test_user_deletion import deletion_db


async def test_rotation_hashes_password_revokes_sessions_and_preserves_other_accounts(deletion_db):
    async with deletion_db() as session:
        root = User(username='root-cli', is_root=True, must_change_password=True,
                    password_hash=hash_password('old-root-password'))
        member = User(username='member-cli', password_hash=hash_password('member-password'))
        session.add_all([root, member])
        await session.commit()
        root_id, member_id = root.id, member.id
        old_version, account_key = root.session_version, root.account_key
        old_cookie = make_session_token(root.id, old_version)
    assert await rotate_root_password('new-root-password', deletion_db) == 'root-cli'
    async with deletion_db() as session:
        root = await session.get(User, root_id)
        member = await session.get(User, member_id)
        assert root.password_hash != 'new-root-password'
        assert verify_password('new-root-password', root.password_hash)
        assert not verify_password('old-root-password', root.password_hash)
        assert root.session_version == old_version + 1
        assert not session_matches_user(old_cookie, root)
        assert root.account_key == account_key
        assert root.must_change_password is False
        assert verify_password('member-password', member.password_hash)


@pytest.mark.parametrize('count', [0, 2])
async def test_command_refuses_missing_or_ambiguous_root(deletion_db, count):
    async with deletion_db() as session:
        session.add_all([User(username=f'root-{n}', is_root=True, password_hash=hash_password('original-password')) for n in range(count)])
        await session.commit()
    with pytest.raises(ValueError, match='ровно один'):
        await rotate_root_password('new-root-password', deletion_db)
    async with deletion_db() as session:
        roots = (await session.execute(select(User))).scalars().all()
        assert len(roots) == count
        assert all(verify_password('original-password', root.password_hash) for root in roots)


async def test_weak_password_rejected_without_opening_database():
    def unavailable():
        raise AssertionError('Database must not be opened')
    with pytest.raises(ValueError, match='8'):
        await rotate_root_password('short', unavailable)
