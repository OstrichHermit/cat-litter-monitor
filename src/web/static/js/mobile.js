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
}

initTheme();

// Bind theme toggle button
const themeToggleBtn = document.getElementById('themeToggle');
if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', toggleTheme);
}

// ==================== Global State ====================
let ws = null;
let notificationCount = 0;
let unreadNotifications = false;
let todayRecordsData = [];
let yesterdayRecordsData = [];
window.currentNotificationPhotos = [];

// 编辑和删除模式状态
const editMode = {
    today: false,
    yesterday: false,
    notification: false
};

const deleteMode = {
    today: false,
    yesterday: false,
    notification: false
};

// ==================== WebSocket Connection ====================
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = protocol + '//' + window.location.host + '/ws';
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
            case 'connected':
                console.log('WebSocket connected event:', msg.data);
                break;
            case 'status_update':
                updateStatus(msg.data.running);
                break;
            case 'records_update':
                updateRecords(msg.data);
                break;
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting in 3s...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
    };
}

// ==================== Tab Navigation ====================
const navItems = document.querySelectorAll('.nav-item');
const tabPanels = document.querySelectorAll('.tab-panel');

navItems.forEach(item => {
    item.addEventListener('click', () => {
        const tabId = item.dataset.tab;

        // Update nav items
        navItems.forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');

        // Update tab panels
        tabPanels.forEach(panel => panel.classList.remove('active'));
        document.getElementById(`tab-${tabId}`).classList.add('active');

        // Load video only when monitor tab is active
        const videoFeed = document.getElementById('videoFeed');
        if (tabId === 'monitor') {
            videoFeed.src = '/video_feed?' + Date.now();
        } else {
            videoFeed.src = '';
        }
    });
});

// ==================== Stats Toggle ====================
function toggleStats(type) {
    const content = document.getElementById(`${type}Stats`);
    const toggle = document.getElementById(`${type}Toggle`);

    content.classList.toggle('collapsed');
    toggle.classList.toggle('collapsed');
}

// ==================== Status Update ====================
function updateStatus(running) {
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const stopBtn = document.getElementById('stopBtn');
    const restartBtn = document.getElementById('restartBtn');

    if (running) {
        statusDot.classList.add('running');
        statusText.textContent = '运行中';
        stopBtn.disabled = false;
        restartBtn.disabled = false;
    } else {
        statusDot.classList.remove('running');
        statusText.textContent = '已停止';
        stopBtn.disabled = true;
        restartBtn.disabled = true;
    }
}

// ==================== Records Update ====================
function updateRecords(data) {
    const todayContainer = document.getElementById('todayRecords');
    const yesterdayContainer = document.getElementById('yesterdayRecords');

    // 保存记录数据到全局变量
    todayRecordsData = data.today || [];
    yesterdayRecordsData = data.yesterday || [];

    // 计算统计数据
    const cats = ['小巫', '猪猪', '汪三', '猪妞'];
    const todayCounts = {};
    const yesterdayCounts = {};

    cats.forEach(cat => {
        todayCounts[cat] = todayRecordsData.filter(r => r.cat_name === cat).length;
        yesterdayCounts[cat] = yesterdayRecordsData.filter(r => r.cat_name === cat).length;
    });

    // 更新统计显示
    cats.forEach(cat => {
        const todayEl = document.getElementById(`today-${cat}`);
        const yesterdayEl = document.getElementById(`yesterday-${cat}`);
        if (todayEl) todayEl.textContent = todayCounts[cat];
        if (yesterdayEl) yesterdayEl.textContent = yesterdayCounts[cat];
    });

    // Update today records
    if (todayRecordsData.length > 0) {
        todayContainer.innerHTML = todayRecordsData.map(r => createRecordItem(r, 'today')).join('');
    } else {
        todayContainer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div>今日暂无记录</div>';
    }

    // Update yesterday records
    if (yesterdayRecordsData.length > 0) {
        yesterdayContainer.innerHTML = yesterdayRecordsData.map(r => createRecordItem(r, 'yesterday')).join('');
    } else {
        yesterdayContainer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div>昨日暂无记录</div>';
    }

    // 更新显示状态
    updateRecordItemsDisplay('today');
    updateRecordItemsDisplay('yesterday');
}

function createRecordItem(record, section) {
    const photoPath = record.photo_path.replace(/^photo\//, '');
    const photoUrl = `/static/photo/${photoPath}`;
    return `
        <div class="record-item" data-record-id="${record.id}" data-section="${section}">
            <div class="record-info">
                <span class="record-time">${record.record_time}</span>
                <span class="record-cat">${record.cat_name}</span>
            </div>
            <img src="${photoUrl}" class="record-thumb" alt="照片" onclick="viewImage('${photoUrl}', event)">

            <!-- Edit Controls -->
            <div class="edit-controls">
                <select class="cat-select" id="cat-select-${record.id}">
                    <option value="">选择</option>
                    <option value="小巫">小巫</option>
                    <option value="猪猪">猪猪</option>
                    <option value="汪三">汪三</option>
                    <option value="猪妞">猪妞</option>
                </select>
                <button class="confirm-btn" onclick="editRecord(${record.id}, '${section}', event)">确认</button>
            </div>

            <!-- Delete Button -->
            <button class="delete-btn" onclick="deleteRecord(${record.id}, '${section}', event)">✕</button>
        </div>
    `;
}

function viewImage(url, event) {
    if (event) event.stopPropagation();
    openLightbox(url);
}

// ==================== Record Actions ====================

// 切换编辑模式
function toggleEditMode(section) {
    editMode[section] = !editMode[section];
    const toggleEl = document.getElementById(`${section}EditToggle`);
    toggleEl.classList.toggle('active', editMode[section]);

    if (section === 'notification') {
        updateNotificationItemsDisplay();
    } else {
        updateRecordItemsDisplay(section);
    }
}

// 切换删除模式
function toggleDeleteMode(section) {
    deleteMode[section] = !deleteMode[section];
    const toggleEl = document.getElementById(`${section}DeleteToggle`);
    toggleEl.classList.toggle('active', deleteMode[section]);
    toggleEl.classList.toggle('delete-active', deleteMode[section]);

    if (section === 'notification') {
        updateNotificationItemsDisplay();
    } else {
        updateRecordItemsDisplay(section);
    }
}

// 更新记录项显示状态
function updateRecordItemsDisplay(section) {
    const container = document.getElementById(`${section}Records`);
    const items = container.querySelectorAll('.record-item');

    items.forEach(item => {
        item.classList.toggle('show-edit', editMode[section]);
        item.classList.toggle('show-delete', deleteMode[section]);
    });
}

// 更新通知项显示状态
function updateNotificationItemsDisplay() {
    const container = document.getElementById('notificationContent');
    const items = container.querySelectorAll('.notification-item');

    items.forEach(item => {
        item.classList.toggle('show-edit', editMode.notification);
        item.classList.toggle('show-delete', deleteMode.notification);
    });
}

// 编辑记录
async function editRecord(recordId, section, event) {
    event.stopPropagation();

    const newCatName = document.getElementById(`cat-select-${recordId}`).value;

    if (!newCatName) {
        alert('请选择猫咪');
        return;
    }

    try {
        const response = await fetch(`/api/records/edit/${recordId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cat_name: newCatName })
        });

        const data = await response.json();

        if (data.success) {
            loadRecords();
        } else {
            alert('修改失败：' + data.error);
        }
    } catch (err) {
        alert('请求失败：' + err);
    }
}

// 删除记录
async function deleteRecord(recordId, section, event) {
    event.stopPropagation();

    if (!confirm('确定要删除这条记录吗？')) return;

    try {
        const response = await fetch(`/api/records/delete/${recordId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            loadRecords();
        } else {
            alert('删除失败：' + data.error);
        }
    } catch (err) {
        alert('请求失败：' + err);
    }
}

// 手动添加记录（将未识别照片入库）
async function manualAddRecord(photoRelPath, event) {
    if (event) event.stopPropagation();

    const catSelect = document.getElementById(`notify-cat-${photoRelPath.split('/').pop()}`);
    if (!catSelect) {
        alert('未找到选择框');
        return;
    }

    const catName = catSelect.value;
    if (!catName) {
        alert('请选择猫咪');
        return;
    }

    try {
        const response = await fetch('/api/records/manual-add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                photo_path: photoRelPath,
                cat_name: catName
            })
        });

        const data = await response.json();

        if (data.success) {
            loadNotifications();
            loadRecords();
        } else {
            alert('添加失败：' + data.error);
        }
    } catch (err) {
        alert('请求失败：' + err);
    }
}

// 删除未识别照片
async function deleteUnidentifiedPhoto(photoRelPath, event) {
    if (event) event.stopPropagation();

    if (!confirm('确定要删除这张照片吗？')) return;

    try {
        const response = await fetch('/api/records/unidentified/delete', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ photo_path: photoRelPath })
        });

        const data = await response.json();

        if (data.success) {
            loadNotifications();
        } else {
            alert('删除失败：' + data.error);
        }
    } catch (err) {
        alert('请求失败：' + err);
    }
}

// ==================== Load Records ====================
function loadRecords() {
    fetch('/api/records/today?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                updateRecords(data);
            }
        })
        .catch(err => console.error('Failed to load records:', err));
}

// ==================== Control Buttons ====================
document.getElementById('stopBtn').addEventListener('click', function() {
    if (!confirm('确定要停止系统服务吗？')) return;

    this.disabled = true;
    this.textContent = '⏳ 停止中...';

    fetch('/api/stop', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'stopping') {
                alert('系统正在停止，请稍候...');
                setTimeout(() => window.location.reload(), 3000);
            } else {
                alert('停止失败: ' + data.message);
                this.disabled = false;
                this.textContent = '🛑 停止';
            }
        })
        .catch(err => {
            alert('请求失败: ' + err);
            this.disabled = false;
            this.textContent = '🛑 停止';
        });
});

document.getElementById('restartBtn').addEventListener('click', function() {
    if (!confirm('确定要重启系统服务吗？')) return;

    this.disabled = true;
    this.textContent = '⏳ 重启中...';

    fetch('/api/restart', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'restarting') {
                alert('系统正在重启，请稍候...');
                setTimeout(() => window.location.reload(), 5000);
            } else {
                alert('重启失败: ' + data.message);
                this.disabled = false;
                this.textContent = '🔄 重启';
            }
        })
        .catch(err => {
            alert('请求失败: ' + err);
            this.disabled = false;
            this.textContent = '🔄 重启';
        });
});

// ==================== Notifications ====================
function updateNotificationBadge() {
    const badge = document.getElementById('notificationBadge');
    if (notificationCount > 0 && unreadNotifications) {
        badge.textContent = notificationCount > 99 ? '99+' : notificationCount;
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

function loadNotifications() {
    fetch('/api/records/unidentified?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                notificationCount = data.count;
                updateNotificationBadge();
                window.currentNotificationPhotos = data.photos;
                renderNotifications(data.photos);
            }
        })
        .catch(err => console.error('Failed to load notifications:', err));
}

function renderNotifications(photos) {
    const content = document.getElementById('notificationContent');

    if (!photos || photos.length === 0) {
        content.innerHTML = `
            <div class="notification-empty">
                <div class="notification-empty-icon">🎉</div>
                <p>所有照片都已处理完毕</p>
            </div>
        `;
        return;
    }

    const sortedPhotos = [...photos].sort((a, b) => {
        return b.filename.localeCompare(a.filename);
    });

    content.innerHTML = `
        <div class="notification-list">
            ${sortedPhotos.map(photo => {
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
                const timeMatch = photo.filename.match(/_(\d{2})(\d{2})/);
                const timeStr = timeMatch ? `${timeMatch[1]}:${timeMatch[2]}` : '';
                const displayName = photo.type === 'unidentifiable' ? '无法识别' : '未识别';

                return `
                    <div class="notification-item" data-photo-path="${relativePath}">
                        <div class="notification-info">
                            <span class="notification-time">${timeStr}</span>
                            <span class="notification-name ${photo.type === 'unidentifiable' ? 'unidentifiable' : ''}">${displayName}</span>
                        </div>
                        <img src="${photoUrl}" class="notification-img" alt="照片" onclick="viewImage('${photoUrl}', event)">

                        <!-- Edit Controls -->
                        <div class="edit-controls">
                            <select class="cat-select" id="notify-cat-${photo.filename}">
                                <option value="">选择</option>
                                <option value="小巫">小巫</option>
                                <option value="猪猪">猪猪</option>
                                <option value="汪三">汪三</option>
                                <option value="猪妞">猪妞</option>
                            </select>
                            <button class="confirm-btn" onclick="manualAddRecord('${relativePath}', event)">确认</button>
                        </div>

                        <!-- Delete Button -->
                        <button class="delete-btn" onclick="deleteUnidentifiedPhoto('${relativePath}', event)">✕</button>

                    </div>
                `;
            }).join('')}
        </div>
    `;

    // 渲染后应用当前显示状态
    setTimeout(() => updateNotificationItemsDisplay(), 0);
}

// Notification modal
document.getElementById('notificationBtn').addEventListener('click', () => {
    document.getElementById('notificationModal').classList.add('active');
    unreadNotifications = false;
    updateNotificationBadge();
});

document.getElementById('modalClose').addEventListener('click', () => {
    document.getElementById('notificationModal').classList.remove('active');
});

document.getElementById('notificationModal').addEventListener('click', (e) => {
    if (e.target.id === 'notificationModal') {
        document.getElementById('notificationModal').classList.remove('active');
    }
});

// ==================== Polling ====================
setInterval(() => {
    fetch('/api/status')
        .then(r => r.json())
        .then(data => updateStatus(data.running))
        .catch(err => console.error('Failed to fetch status:', err));
}, 5000);

setInterval(loadRecords, 30000);
setInterval(loadNotifications, 30000);

// ==================== Initialize ====================
connectWebSocket();
loadRecords();
loadNotifications();
fetch('/api/status')
    .then(r => r.json())
    .then(data => updateStatus(data.running));

// ==================== Photo Lightbox ====================
function openLightbox(url) {
    const lightbox = document.getElementById('photoLightbox');
    const img = document.getElementById('lightboxImg');
    img.src = url;
    lightbox.classList.add('active');
}

function closeLightbox() {
    const lightbox = document.getElementById('photoLightbox');
    lightbox.classList.add('closing');
    setTimeout(() => {
        lightbox.classList.remove('active', 'closing');
    }, 200);
}

async function markUnidentifiable(photoRelPath, event) {
    if (event) event.stopPropagation();
    if (!confirm('确定要将此照片标记为无法识别吗？')) return;

    try {
        const response = await fetch('/api/records/mark-unidentifiable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ photo_path: photoRelPath })
        });
        const data = await response.json();
        if (data.success) {
            loadNotifications();
        } else {
            alert('标记失败：' + data.error);
        }
    } catch (err) {
        alert('请求失败：' + err);
    }
}
