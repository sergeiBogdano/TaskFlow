/* TaskFlow-SEO — общие JS-функции */

const STATUS_LABELS = {todo:'К выполнению', in_progress:'В работе', done:'Выполнено', overdue:'Просрочено'};
const PRIO_LABELS = {high:'Высокий', medium:'Средний', low:'Низкий'};
const TYPE_LABELS = {article:'Статья', seo:'SEO', dev:'Разработка', custom:'Обычная'};
const STATUS_CLASS = {todo:'bg-secondary', in_progress:'bg-primary', done:'bg-success', overdue:'bg-danger'};

let detailTaskId = null;

/* ─── Чек-лист ───────────────────────────────────────────── */

function addChecklistItem(containerId, value) {
  const c = document.getElementById(containerId);
  if (!c) return;
  const div = document.createElement('div');
  div.className = 'input-group input-group-sm mb-1';
  div.innerHTML = '<input type="text" class="form-control form-control-sm" value="' + (value || '') + '" placeholder="Пункт"><button class="btn btn-sm btn-outline-danger" type="button" onclick="this.parentElement.remove()"><i class="bi bi-x"></i></button>';
  c.appendChild(div);
}

function loadTemplate(type, prefix) {
  const container = document.getElementById(prefix + 'Checklist');
  if (!container) return;
  container.innerHTML = '';
  const tplMap = {};
  if (typeof TEMPLATES !== 'undefined') {
    Object.keys(TEMPLATES).forEach(k => { tplMap[k] = TEMPLATES[k].map(i => i.text); });
  }
  const items = tplMap[type] || [];
  items.forEach(text => addChecklistItem(prefix + 'Checklist', text));
}

function collectChecklist(containerId) {
  const c = document.getElementById(containerId);
  if (!c) return null;
  const items = [];
  c.querySelectorAll('input[type="text"]').forEach(inp => {
    const v = inp.value.trim();
    if (v) items.push({text: v, done: false});
  });
  return items.length ? items : null;
}

/* ─── Модалка просмотра/редактирования задачи ──────────── */

function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function openDetailModal(id) {
  fetch('/api/tasks/all').then(r => r.json()).then(all => {
    const t = all.find(x => x.id === id);
    if (!t) { alert('Задача не найдена'); return; }

    detailTaskId = t.id;
    const modal = new bootstrap.Modal(document.getElementById('taskDetailModal'));
    document.getElementById('detailTitle').textContent = '#' + t.id + ' ' + t.title;

    const calDate = t.completion_date ? new Date(t.completion_date).toLocaleString('ru-RU') : '—';
    const deadlineStr = t.deadline ? new Date(t.deadline).toLocaleString('ru-RU') : '—';

    let accessesHtml = '';
    if (t.client_accesses && t.client_accesses.length) {
      accessesHtml = '<label class="form-label fw-semibold mt-2"><i class="bi bi-key text-warning me-1"></i>Доступы ' + esc(t.client) + '</label>'
        + '<div class="small">'
        + t.client_accesses.map(a => {
          let pwEnc = esc(a.password || '');
          let pwHtml = '<span style="cursor:pointer;border-bottom:1px dashed var(--bs-secondary-color)" onclick="this.textContent=this.dataset.pw;this.style.cursor=\'default\'" data-pw="' + pwEnc + '">\u2022\u2022\u2022\u2022\u2022\u2022</span>';
          return '<div class="border rounded p-2 mb-1" style="background:var(--bs-tertiary-bg)">'
            + '<div class="fw-semibold small mb-1">' + esc(a.title) + '</div>'
            + '<div class="row g-1 align-items-center">'
            + (a.url ? '<div class="col-12"><a href="' + esc(a.url) + '" target="_blank" class="text-decoration-none small"><i class="bi bi-link-45deg"></i> ' + esc(a.url) + '</a></div>' : '')
            + '<div class="col-5"><span class="text-secondary">Логин:</span> <span class="acp-val">' + esc(a.login) + '</span> <span class="acp-copy" onclick="copyText(this)" title="Копировать"><i class="bi bi-clipboard"></i></span></div>'
            + '<div class="col-5"><span class="text-secondary">Пароль:</span> ' + pwHtml + ' <span class="acp-copy" onclick="copyText(this.previousElementSibling.dataset.pw||this.previousElementSibling.textContent)" title="Копировать"><i class="bi bi-clipboard"></i></span></div>'
            + (a.notes ? '<div class="col-12"><span class="text-secondary">Прим.:</span> ' + esc(a.notes) + '</div>' : '')
            + '</div></div>';
        }).join('')
        + '</div>';
    }

    document.getElementById('detailBody').innerHTML = '<table class="table table-sm table-borderless mb-2">'
      + '<tr><td class="text-secondary" style="width:140px">Задача</td><td><strong>' + esc(t.title) + '</strong></td></tr>'
      + '<tr><td class="text-secondary">Тип</td><td>' + (TYPE_LABELS[t.task_type]||t.task_type) + '</td></tr>'
      + (t.client ? '<tr><td class="text-secondary">Клиент</td><td>' + esc(t.client) + '</td></tr>' : '')

      + '<tr><td class="text-secondary">Срок (крайний)</td><td>' + deadlineStr + '</td></tr>'
      + '<tr><td class="text-secondary">Дата выполнения</td><td>' + calDate + '</td></tr>'
      + '<tr><td class="text-secondary">Статус</td><td><span class="badge ' + (STATUS_CLASS[t.status]||'bg-secondary') + '">' + (STATUS_LABELS[t.status]||t.status) + '</span></td></tr>'
      + '<tr><td class="text-secondary">Важность</td><td>' + (PRIO_LABELS[t.priority]||t.priority) + '</td></tr>'
      + '</table>'
      + '<label class="form-label mb-0 mt-1">Заметка</label><textarea class="form-control mb-2" id="detailNotes" rows="2" style="white-space:pre-wrap">' + esc(t.notes) + '</textarea>'
      + '<label class="form-label mb-0 mt-1">Комментарий</label><textarea class="form-control mb-2" id="detailComment" rows="3" style="white-space:pre-wrap">' + esc(t.comment) + '</textarea>'
      + (t.checklist && t.checklist.length
        ? '<label class="form-label fw-semibold mt-2">Чек-лист</label><div id="detailChecklist">'
          + t.checklist.map((ci, i) => renderChecklistItem(ci, i)).join('')
          + '</div>'
        : '')
      + accessesHtml;

    // Файлы
    let filesHtml = '<label class="form-label fw-semibold mt-3 mb-1"><i class="bi bi-paperclip me-1"></i>Файлы</label><div id="fileList" class="mb-1"></div>'
      + '<div class="d-flex align-items-center gap-2"><input type="file" id="fileUpload" class="form-control form-control-sm" style="max-width:250px" multiple>'
      + '<button class="btn btn-sm btn-outline-primary" onclick="uploadFiles(' + t.id + ')"><i class="bi bi-upload"></i></button></div>'
      + '<div id="fileDropZone" style="border:2px dashed var(--bs-border-color);border-radius:6px;padding:1rem;text-align:center;color:var(--bs-secondary-color);font-size:0.85rem;cursor:pointer;margin-top:0.5rem">'
      + 'Перетащите файлы сюда</div>';
    document.getElementById('detailBody').insertAdjacentHTML('beforeend', filesHtml);
    setupFileDropZone(t.id);

    // Загружаем список файлов
    fetch('/api/tasks/' + t.id + '/files').then(r => r.json()).then(files => {
      const container = document.getElementById('fileList');
      if (!container) return;
      if (files.length) {
        container.innerHTML = files.map(f =>
          '<div class="d-flex align-items-center gap-2 py-1"><a href="/api/files/' + f.id + '/download" class="small text-truncate flex-grow-1">' + esc(f.name) + '</a>'
          + '<small class="text-secondary flex-shrink-0">' + (f.size ? Math.round(f.size/1024) + 'KB' : '') + '</small>'
          + '<span class="text-danger" style="cursor:pointer" onclick="deleteFile(' + f.id + ', this)"><i class="bi bi-x"></i></span></div>'
        ).join('');
      } else {
        container.innerHTML = '<div class="small text-secondary">Нет файлов</div>';
      }
    });

    // Повторение
    let recurringHtml = '';
    if (t.recurring_interval) {
      const intervalMap = {daily:'Ежедневно', weekly:'Еженедельно', monthly:'Ежемесячно'};
      recurringHtml = '<div class="mt-2 small text-secondary"><i class="bi bi-arrow-repeat me-1"></i>Повтор: ' + (intervalMap[t.recurring_interval] || t.recurring_interval)
        + (t.recurring_remaining != null ? ' (осталось ' + t.recurring_remaining + ')' : '')
        + ' <span class="text-primary" style="cursor:pointer" onclick="generateNext(' + t.id + ')">Создать следующий</span></div>';
    }
    document.getElementById('detailBody').insertAdjacentHTML('beforeend', recurringHtml);

    // Комментарии
    const commentHtml = '<label class="form-label fw-semibold mt-3 mb-1"><i class="bi bi-chat-dots me-1"></i>Комментарии</label>'
      + '<div id="commentList" class="mb-1 small"></div>'
      + '<div class="input-group input-group-sm"><input type="text" id="commentInput" class="form-control" placeholder="Напишите комментарий... (для @упоминания используйте @username)">'
      + '<button class="btn btn-outline-primary" onclick="addComment(' + t.id + ')"><i class="bi bi-send"></i></button></div>';
    document.getElementById('detailBody').insertAdjacentHTML('beforeend', commentHtml);
    loadComments(t.id);

    document.getElementById('detailFooter').innerHTML = ''
      + '<button class="btn btn-primary btn-sm" onclick="saveDetailChanges()"><i class="bi bi-check-lg"></i> Сохранить</button>'
      + (t.status !== 'done'
        ? '<form method="POST" action="/tasks/' + t.id + '/done" class="d-inline"><button class="btn btn-success btn-sm"><i class="bi bi-check-lg"></i> Выполнено</button></form>'
        : '')
      + '<a href="/tasks/' + t.id + '/print" target="_blank" class="btn btn-outline-secondary btn-sm"><i class="bi bi-printer"></i></a>'
      + (t.client_id
        ? '<a href="/tasks?client_id=' + t.client_id + '" class="btn btn-outline-primary btn-sm"><i class="bi bi-box-arrow-up-right"></i> В список задач</a>'
        : '');

    modal.show();

    // Auto-start: todo → in_progress
    if (t.status === 'todo') {
      fetch('/api/tasks/' + t.id + '/start', {method: 'POST'}).then(r => r.json()).then(data => {
        if (data.ok && data.status === 'in_progress') {
          const badge = document.querySelector('#detailBody .badge');
          if (badge) {
            badge.className = 'badge bg-primary';
            badge.textContent = 'В работе';
          }
        }
      });
    }
  });
}

function renderChecklistItem(ci, i) {
  const checked = ci.done ? 'checked' : '';
  const textVal = ci.text || '';
  const reminderVal = ci.reminder || '';
  const reminderHtml = reminderVal
    ? '<input type="datetime-local" class="form-control form-control-sm" id="ci_remind_' + i + '" value="' + reminderVal.replace('Z','').slice(0,16) + '" style="max-width:200px">'
    : '<input type="datetime-local" class="form-control form-control-sm" id="ci_remind_' + i + '" style="max-width:200px">';
  return '<div class="input-group input-group-sm mb-1">'
    + '<div class="input-group-text">'
    + '<input class="form-check-input mt-0" type="checkbox" ' + checked + ' onchange="onChecklistToggle(' + i + ', this.checked)">'
    + '</div>'
    + '<input type="text" class="form-control" id="ci_text_' + i + '" value="' + textVal.replace(/"/g,'&quot;') + '">'
    + reminderHtml
    + '<button class="btn btn-outline-danger" onclick="removeDetailChecklistItem(' + i + ')"><i class="bi bi-x"></i></button>'
    + '</div>';
}

function onChecklistToggle(i, checked) {
  fetch('/api/tasks/' + detailTaskId + '/checklist-item', {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({index: i, done: checked})
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      if (data.auto_status) {
        const badge = document.querySelector('#detailBody .badge');
        if (badge) {
          badge.className = 'badge ' + (STATUS_CLASS[data.auto_status] || 'bg-secondary');
          badge.textContent = STATUS_LABELS[data.auto_status] || data.auto_status;
        }
        const footer = document.getElementById('detailFooter');
        if (data.auto_status === 'done' && footer) {
          const doneBtn = footer.querySelector('.btn-success');
          if (doneBtn) doneBtn.remove();
        }
      }
    }
  });
}

function removeDetailChecklistItem(i) {
  const el = document.querySelector('#detailChecklist .input-group:nth-child(' + (i+1) + ')');
  if (el) el.remove();
}

function saveDetailChanges() {
  const notes = document.getElementById('detailNotes')?.value || '';
  const comment = document.getElementById('detailComment')?.value || '';
  const checklistItems = [];
  const container = document.getElementById('detailChecklist');
  if (container) {
    const groups = container.querySelectorAll('.input-group');
    groups.forEach(g => {
      const cb = g.querySelector('.form-check-input');
      const textInput = g.querySelector('input[id^="ci_text_"]');
      const remindInput = g.querySelector('input[id^="ci_remind_"]');
      if (textInput) {
        const text = textInput.value.trim();
        if (text) {
          const item = {text: text, done: cb ? cb.checked : false};
          if (remindInput && remindInput.value) {
            const d = new Date(remindInput.value);
            if (!isNaN(d.getTime())) item.reminder = d.toISOString();
          }
          checklistItems.push(item);
        }
      }
    });
  }

  fetch('/api/tasks/' + detailTaskId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({notes: notes, comment: comment, checklist: checklistItems.length ? checklistItems : null})
  }).then(r => {
    if (r.ok) {
      showToast('Сохранено');
      location.reload();
    } else {
      alert('Ошибка сохранения');
    }
  }).catch(() => alert('Ошибка сети'));
}

/* ─── Копирование текста ──────────────────────────────── */

function copyText(v) {
  const text = typeof v === 'string' ? v : (v.dataset ? v.dataset.pw : v.textContent);
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Скопировано');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    showToast('Скопировано');
  });
}

/* ─── Файлы ──────────────────────────────────────────────── */
let fileDropTaskId = null;

function uploadFiles(taskId) {
  const input = document.getElementById('fileUpload');
  if (!input || !input.files.length) return;
  uploadFileList(taskId, input.files);
}

function uploadFileList(taskId, files) {
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    fetch('/api/tasks/' + taskId + '/upload', {method: 'POST', body: fd})
      .then(r => r.json())
      .then(() => { location.reload(); });
  }
}

function deleteFile(fileId, el) {
  if (!confirm('Удалить файл?')) return;
  fetch('/api/files/' + fileId, {method: 'DELETE'})
    .then(() => { const row = el.closest('div'); if (row) row.remove(); });
}

function setupFileDropZone(taskId) {
  const dz = document.getElementById('fileDropZone');
  if (!dz) return;
  dz.addEventListener('click', () => document.getElementById('fileUpload')?.click());
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor = 'var(--bs-primary)'; });
  dz.addEventListener('dragleave', () => { dz.style.borderColor = 'var(--bs-border-color)'; });
  dz.addEventListener('drop', function(e) {
    e.preventDefault();
    dz.style.borderColor = 'var(--bs-border-color)';
    if (e.dataTransfer.files.length) uploadFileList(taskId, e.dataTransfer.files);
  });
}

function generateNext(taskId) {
  if (!confirm('Создать следующий экземпляр задачи?')) return;
  fetch('/api/tasks/' + taskId + '/generate-next', {method: 'POST'})
    .then(r => r.json())
    .then(data => {
      if (data.ok) showToast('Создана задача #' + data.new_id);
      else showToast(data.error || 'Ошибка');
    });
}

/* ─── Комментарии ──────────────────────────────────────── */

function loadComments(taskId) {
  fetch('/api/tasks/' + taskId + '/comments')
    .then(r => r.json())
    .then(comments => {
      const container = document.getElementById('commentList');
      if (!container) return;
      if (comments.length) {
        container.innerHTML = comments.map(c =>
          '<div class="border rounded p-2 mb-1" style="background:var(--bs-tertiary-bg)">'
          + '<div class="d-flex justify-content-between"><strong class="small">' + esc(c.author_name) + '</strong>'
          + '<small class="text-secondary">' + c.created_at + '</small></div>'
          + '<div class="small mt-1">' + esc(c.content).replace(/@(\w+)/g, '<span class="text-primary">@$1</span>') + '</div>'
          + '</div>'
        ).join('');
      } else {
        container.innerHTML = '<div class="text-secondary small">Нет комментариев</div>';
      }
    });
}

function addComment(taskId) {
  const input = document.getElementById('commentInput');
  if (!input || !input.value.trim()) return;
  const fd = new FormData();
  fd.append('content', input.value.trim());
  fetch('/api/tasks/' + taskId + '/comments', {method: 'POST', body: fd})
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        input.value = '';
        loadComments(taskId);
      } else {
        showToast('Ошибка');
      }
    });
}

document.addEventListener('DOMContentLoaded', function() {
  const commentInput = document.getElementById('commentInput');
  if (commentInput) {
    commentInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        addComment(detailTaskId);
      }
    });
  }
});

/* ─── Toast-уведомления ─────────────────────────────────── */

function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast align-items-center text-bg-success border-0 position-fixed bottom-0 end-0 m-3';
  t.innerHTML = '<div class="d-flex"><div class="toast-body">' + msg + '</div><button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button></div>';
  document.body.appendChild(t);
  const toast = new bootstrap.Toast(t, {delay: 3000});
  toast.show();
  t.addEventListener('hidden.bs.toast', function() { t.remove(); });
}
