// ==================== Dark Mode ====================
function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else if (saved === 'light') {
        document.documentElement.removeAttribute('data-theme');
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
    updateThemeIcon();
}

function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    }
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = isDark ? '☀️' : '🌙';
    btn.title = isDark ? '切换浅色模式' : '切换深色模式';
}

initTheme();

// Bind theme toggle button
document.getElementById('themeToggle').addEventListener('click', toggleTheme);

// WebSocket connection with auto-reconnect
let ws;
let isRunning = true;
let notificationCount = 0;
let unreadNotifications = true;

function connectWebSocket() {
    ws = new WebSocket('ws://' + window.location.host + '/ws');

    ws.onopen = function() {
        console.log('Connected to server');
    };

    ws.onmessage = function(event) {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
            case 'connected':
                console.log('Server acknowledged connection');
                loadNotifications();
                break;
            case 'status_update':
                isRunning = msg.data.running;
                updateStatus(msg.data.running);
                break;
            case 'records_update':
                loadRecords();
                loadNotifications();
                break;
        }
    };

    ws.onclose = function() {
        console.log('WebSocket disconnected, reconnecting in 3 seconds...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = function(err) {
        console.error('WebSocket error:', err);
        ws.close();
    };
}

connectWebSocket();

// Delete mode state
const deleteMode = {
    today: false,
    yesterday: false,
    notification: false
};

// Edit mode state
const editMode = {
    today: false,
    yesterday: false,
    notification: false
};

function toggleDeleteMode(section) {
    deleteMode[section] = !deleteMode[section];
    const toggle = document.getElementById(`${section}DeleteToggle`);
    if (deleteMode[section]) {
        toggle.classList.add('active');
    } else {
        toggle.classList.remove('active');
    }
    // Only toggle button classes, no re-render
    if (section === 'notification') {
        const notificationBtns = document.querySelectorAll('#notificationContent .delete-btn');
        notificationBtns.forEach(btn => {
            if (deleteMode.notification) {
                btn.classList.remove('hidden');
            } else {
                btn.classList.add('hidden');
            }
        });
    } else {
        const containerId = section === 'today' ? 'todayRecords' : 'yesterdayRecords';
        const deleteBtns = document.querySelectorAll(`#${containerId} .delete-btn`);
        deleteBtns.forEach(btn => {
            if (deleteMode[section]) {
                btn.classList.remove('hidden');
            } else {
                btn.classList.add('hidden');
            }
        });
    }
}

function toggleEditMode(section) {
    editMode[section] = !editMode[section];
    const toggle = document.getElementById(`${section}EditToggle`);
    if (editMode[section]) {
        toggle.classList.add('active');
    } else {
        toggle.classList.remove('active');
    }
    // Toggle edit control panel visibility (using CSS class for animation)
    if (section === 'notification') {
        const identifyControls = document.querySelectorAll('#notificationContent .identify-controls');
        identifyControls.forEach(control => {
            if (editMode[section]) {
                control.style.display = 'flex';
                // Delay adding visible class to trigger animation
                setTimeout(() => control.classList.add('visible'), 10);
            } else {
                control.classList.remove('visible');
                // Wait for animation to complete before hiding
                setTimeout(() => {
                    if (!control.classList.contains('visible')) {
                        control.style.display = 'none';
                    }
                }, 300);
            }
        });
    } else {
        const containerId = section === 'today' ? 'todayRecords' : 'yesterdayRecords';
        const identifyControls = document.querySelectorAll(`#${containerId} .identify-controls`);
        identifyControls.forEach(control => {
            if (editMode[section]) {
                control.style.display = 'flex';
                // Delay adding visible class to trigger animation
                setTimeout(() => control.classList.add('visible'), 10);
            } else {
                control.classList.remove('visible');
                // Wait for animation to complete before hiding
                setTimeout(() => {
                    if (!control.classList.contains('visible')) {
                        control.style.display = 'none';
                    }
                }, 300);
            }
        });
    }
}

function updateStatus(running) {
    const statusEl = document.getElementById('status');
    const stopBtn = document.getElementById('stopBtn');
    const restartBtn = document.getElementById('restartBtn');

    if (running) {
        statusEl.className = 'status-indicator running';
        statusEl.innerHTML = '✅ 系统运行中';
        stopBtn.disabled = false;
        restartBtn.disabled = false;
    } else {
        statusEl.className = 'status-indicator stopped';
        statusEl.innerHTML = '❌ 系统已停止';
        stopBtn.disabled = true;
        restartBtn.disabled = true;
    }
}

function updateRecords(containerId, statsPrefix, records) {
    const cats = ['小巫', '猪猪', '汪三', '猪妞'];
    const counts = Object.fromEntries(cats.map(c => [c, 0]));

    records.forEach(r => {
        if (r.cat_name in counts) counts[r.cat_name]++;
    });

    cats.forEach(cat => {
        const el = document.getElementById(`${statsPrefix}-${cat}`);
        if (el) el.textContent = counts[cat];
    });

    const container = document.getElementById(containerId);
    const section = containerId.includes('today') ? 'today' : 'yesterday';

    if (records.length === 0) {
        container.innerHTML = `<div class="empty-state">📭 ${section === 'today' ? '今日' : '昨日'}暂无记录</div>`;
        return;
    }

    container.innerHTML = records.map(r => {
        const photoPath = r.photo_path.replace(/^photo\//, '');
        const photoUrl = `/static/photo/${photoPath}`;
        const deleteClass = deleteMode[section] ? '' : 'hidden';
        const editClass = editMode[section] ? 'visible' : '';
        return `
            <div class="record">
                <span class="record-time">${r.record_time}</span>
                <span class="record-cat">${r.cat_name}</span>
                <img src="${photoUrl}" class="record-img"
                     onclick="window.open('${photoUrl}', '_blank')"
                     onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTAiIGhlaWdodD0iNTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjUwIiBoZWlnaHQ9IjUwIiBmaWxsPSIjZWVlIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPjwvdGV4dD48L3N2Zz4='"
                     alt="照片">
                <div class="identify-controls ${editClass}">
                    <select class="cat-select" id="edit-cat-select-${r.id}">
                        <option value="">选择猫咪</option>
                        <option value="小巫" ${r.cat_name === '小巫' ? 'selected' : ''}>小巫</option>
                        <option value="猪猪" ${r.cat_name === '猪猪' ? 'selected' : ''}>猪猪</option>
                        <option value="汪三" ${r.cat_name === '汪三' ? 'selected' : ''}>汪三</option>
                        <option value="猪妞" ${r.cat_name === '猪妞' ? 'selected' : ''}>猪妞</option>
                    </select>
                    <button class="confirm-btn" onclick="editRecord(${r.id}, '${section}')">确认</button>
                </div>
                <button class="delete-btn ${deleteClass}" onclick="deleteRecord(${r.id}, '${section}')">✕</button>
            </div>
        `;
    }).join('');
}

async function deleteRecord(recordId, section) {
    if (!confirm('确定要删除这条记录吗？')) return;

    try {
        const response = await fetch(`/api/records/delete/${recordId}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            loadRecords();
        } else {
            alert('删除失败: ' + (data.error || '未知错误'));
        }
    } catch (err) {
        alert('删除失败: ' + err);
    }
}

async function editRecord(recordId, section) {
    const select = document.getElementById(`edit-cat-select-${recordId}`);
    const newCatName = select.value;

    if (!newCatName) {
        alert('请选择一只猫咪');
        return;
    }

    try {
        const response = await fetch(`/api/records/edit/${recordId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cat_name: newCatName
            })
        });
        const data = await response.json();

        if (data.success) {
            loadRecords();
        } else {
            alert('修改失败: ' + (data.error || '未知错误'));
        }
    } catch (err) {
        alert('修改失败: ' + err);
    }
}

function loadRecords() {
    fetch('/api/records/today?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                updateRecords('todayRecords', 'today', data.today);
                updateRecords('yesterdayRecords', 'yesterday', data.yesterday);
            }
        })
        .catch(err => console.error('Failed to load records:', err));
}

document.getElementById('stopBtn').addEventListener('click', function() {
    if (!confirm('确定要停止系统服务吗？')) return;

    this.disabled = true;
    this.textContent = '⏳ 正在停止...';

    fetch('/api/stop', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'stopping') {
                alert('系统正在停止，请稍候...');
                setTimeout(() => window.location.reload(), 3000);
            } else {
                alert('停止失败: ' + data.message);
                this.disabled = false;
                this.textContent = '🛑 停止服务';
            }
        })
        .catch(err => {
            alert('请求失败: ' + err);
            this.disabled = false;
            this.textContent = '🛑 停止服务';
        });
});

document.getElementById('restartBtn').addEventListener('click', function() {
    if (!confirm('确定要重启系统服务吗？')) return;

    this.disabled = true;
    this.textContent = '⏳ 正在重启...';

    fetch('/api/restart', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'restarting') {
                alert('系统正在重启，请稍候...');
                setTimeout(() => window.location.reload(), 5000);
            } else {
                alert('重启失败: ' + data.message);
                this.disabled = false;
                this.textContent = '🔄 重启服务';
            }
        })
        .catch(err => {
            alert('请求失败: ' + err);
            this.disabled = false;
            this.textContent = '🔄 重启服务';
        });
});

// Periodic polling
setInterval(() => {
    fetch('/api/status')
        .then(r => r.json())
        .then(data => updateStatus(data.running));
}, 5000);

setInterval(loadRecords, 30000);

// Initial load
loadRecords();
loadNotifications();

// ==================== Notification Features ====================

function openNotifications() {
    const modal = document.getElementById('notificationModal');
    modal.classList.add('active');
    unreadNotifications = false;
    updateNotificationBadge();
}

function closeNotifications() {
    const modal = document.getElementById('notificationModal');
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 200);
}

// Click outside modal to close
document.getElementById('notificationModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeNotifications();
    }
});

// ESC key to close
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeNotifications();
    }
});

function updateNotificationBadge() {
    const badge = document.getElementById('notificationBadge');
    if (notificationCount > 0 && unreadNotifications) {
        badge.textContent = notificationCount > 99 ? '99+' : notificationCount;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

async function loadNotifications() {
    try {
        const response = await fetch('/api/records/unidentified?t=' + Date.now());
        const data = await response.json();

        if (data.success) {
            notificationCount = data.count;
            updateNotificationBadge();
            renderNotifications(data.photos);
        }
    } catch (err) {
        console.error('Failed to load notifications:', err);
    }
}

function renderNotifications(photos) {
    const content = document.getElementById('notificationContent');

    if (!photos || photos.length === 0) {
        content.innerHTML = `
            <div class="notification-empty">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                </svg>
                <p>🎉 所有照片都已识别完毕</p>
            </div>
        `;
        return;
    }

    // Sort by filename (newest first), filename format: YYYYMMDD_HHMMSS.jpg
    const sortedPhotos = [...photos].sort((a, b) => {
        return b.filename.localeCompare(a.filename);
    });

    content.innerHTML = `
        <div class="notification-list">
            ${sortedPhotos.map(photo => {
                // Extract relative path from absolute path
                // Path format: D:\path\photo\YYYY-MM-DD\Unidentified\file.jpg
                // Extract: YYYY-MM-DD/Unidentified/file.jpg
                let relativePath = '';
                const parts = photo.path.split(/[/\\]/);
                const photoIndex = parts.indexOf('photo');
                if (photoIndex !== -1 && photoIndex + 3 < parts.length) {
                    const date = parts[photoIndex + 1];
                    const unidentified = parts[photoIndex + 2];
                    const filename = parts[photoIndex + 3];
                    relativePath = `${date}/${unidentified}/${filename}`;
                }
                const photoUrl = `/static/photo/${relativePath}`;

                // Extract time from filename: YYYYMMDD_HHMMSS.jpg -> HH:MM:SS
                const timeMatch = photo.filename.match(/_(\d{2})(\d{2})(\d{2})/);
                const timeStr = timeMatch ? `${timeMatch[1]}:${timeMatch[2]}:${timeMatch[3]}` : '';

                const deleteClass = deleteMode.notification ? '' : 'hidden';
                const editClass = editMode.notification ? 'visible' : '';
                return `
                    <div class="notification-item">
                        <span class="notification-item-time">${photo.date} ${timeStr}</span>
                        <span class="notification-item-name">未识别</span>
                        <img src="${photoUrl}" class="notification-item-img"
                             onclick="window.open('${photoUrl}', '_blank')"
                             onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQiIGhlaWdodD0iMzYiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjM2IiBmaWxsPSIjZWVlIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiPjwvdGV4dD48L3N2Zz4='"
                             alt="照片">
                        <div class="identify-controls ${editClass}">
                            <select class="cat-select" id="cat-select-${photo.filename}">
                                <option value="">选择猫咪</option>
                                <option value="小巫">小巫</option>
                                <option value="猪猪">猪猪</option>
                                <option value="汪三">汪三</option>
                                <option value="猪妞">猪妞</option>
                            </select>
                            <button class="confirm-btn" onclick='manualIdentify("${relativePath}", "${photo.filename}")'>确认</button>
                        </div>
                        <button class="delete-btn ${deleteClass}" onclick='deleteUnidentifiedPhoto("${relativePath}")'>✕</button>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

async function deleteUnidentifiedPhoto(photoPath) {
    if (!confirm('确定要删除这张未识别的照片吗？')) return;

    try {
        const response = await fetch('/api/records/unidentified/delete', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ photo_path: photoPath })
        });
        const data = await response.json();

        if (data.success) {
            loadNotifications();
        } else {
            alert('删除失败: ' + (data.error || '未知错误'));
        }
    } catch (err) {
        alert('删除失败: ' + err);
    }
}

async function manualIdentify(photoPath, filename) {
    const select = document.getElementById(`cat-select-${filename}`);
    const catName = select.value;

    if (!catName) {
        alert('请选择一只猫咪');
        return;
    }

    if (!confirm(`确定要将此照片识别为 ${catName} 吗？`)) return;

    try {
        const response = await fetch('/api/records/manual-add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                photo_path: photoPath,
                cat_name: catName
            })
        });
        const data = await response.json();

        if (data.success) {
            loadNotifications();
            loadRecords();
        } else {
            alert('入库失败: ' + (data.error || '未知错误'));
        }
    } catch (err) {
        alert('入库失败: ' + err);
    }
}
