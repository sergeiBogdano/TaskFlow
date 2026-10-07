"""Purge checks with actual foreign-key enforcement, including CRM dependencies."""
from datetime import datetime
import pytest
from sqlalchemy import select
from tests.test_user_deletion import deletion_db
from app.core.models import (User, Workspace, WorkspaceMember, Client, Contract, Task, TaskComment,
    Module, Cycle, CrmPipeline, CrmContact, CrmDeal, CrmActivity, CrmField)
from app.web.api.workspaces import _purge_workspace

async def test_workspace_purge_is_fk_safe_and_preserves_other_space(deletion_db):
    async with deletion_db() as session:
        user = User(username='purge-root', password_hash='unused', is_root=True)
        session.add(user); await session.flush()
        space = Workspace(name='Remove', created_by=user.id)
        keep = Workspace(name='Keep', created_by=user.id)
        session.add_all([space, keep]); await session.flush()
        session.add(WorkspaceMember(workspace_id=space.id, user_id=user.id))
        client = Client(org_name='Remove client', workspace_id=space.id, contract_start=datetime(2026, 1, 1), contract_end=datetime(2027, 1, 1))
        module = Module(name='Remove module', workspace_id=space.id)
        pipeline = CrmPipeline(workspace_id=space.id, name='Sales', stages='[{"id":"new","label":"New"}]')
        session.add_all([client, module, pipeline]); await session.flush()
        cycle = Cycle(module_id=module.id, name='Cycle')
        contract = Contract(client_id=client.id, contract_type='SEO')
        contact = CrmContact(workspace_id=space.id, client_id=client.id, name='Contact')
        session.add_all([cycle, contract, contact]); await session.flush()
        task = Task(workspace_id=space.id, title='Remove task', client_id=client.id, contract_id=contract.id, module_id=module.id, cycle_id=cycle.id)
        keep_task = Task(workspace_id=keep.id, title='Keep task')
        session.add_all([task, keep_task]); await session.flush()
        deal = CrmDeal(workspace_id=space.id, pipeline_id=pipeline.id, stage='new', title='Deal', contact_id=contact.id, contract_id=contract.id, client_id=client.id, task_id=task.id)
        session.add(deal); await session.flush()
        task.crm_deal_id = deal.id
        session.add_all([CrmActivity(workspace_id=space.id, deal_id=deal.id, title='Call'), CrmField(workspace_id=space.id, key='source', label='Source'), TaskComment(task_id=task.id, content='Comment')])
        await session.commit()
        space_id, keep_id, keep_task_id = space.id, keep.id, keep_task.id
        await _purge_workspace(session, space_id)
        await session.commit()
        assert await session.get(Workspace, space_id) is None
        assert await session.get(Workspace, keep_id) is not None
        assert (await session.get(Task, keep_task_id)).title == 'Keep task'
        assert not (await session.execute(select(CrmDeal))).scalars().all()
        assert not (await session.execute(select(Module))).scalars().all()
