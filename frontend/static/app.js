/* AI SQL Assistant - conversation UI, agent telemetry and result rendering. */
const $ = (id) => document.getElementById(id);
const AGENT_LABELS = {
    conversation_router: 'Conversation Router',
    planner: 'Planner Agent',
    schema_analyzer: 'Schema Analyzer',
    sql_generator: 'SQL Generator',
    sql_validator: 'SQL Validator',
    sql_executor: 'SQL Executor',
    self_correction: 'Self-Correction Agent',
    result_interpreter: 'Result Interpreter',
    response_generator: 'Response Generator',
};
const STORAGE_KEY = 'medquery_conversations_v2';
const CURRENT_KEY = 'medquery_current_conversation';
const responseCache = new Map();
let charts = [];

function uid() {
    return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`;
}

function loadConversations() {
    try {
        const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch { /* use a clean conversation */ }
    return [{ id: uid(), title: 'Cuộc hội thoại mới', messages: [], updatedAt: Date.now() }];
}

let conversations = loadConversations();
let currentId = localStorage.getItem(CURRENT_KEY) || conversations[0].id;
if (!conversations.some((item) => item.id === currentId)) currentId = conversations[0].id;

function currentConversation() {
    return conversations.find((item) => item.id === currentId);
}

function persist() {
    const compact = conversations.slice(0, 20).map((conversation) => ({
        ...conversation,
        messages: conversation.messages.slice(-20).map((message) => {
            if (message.role !== 'assistant' || !message.payload) return message;
            return {
                ...message,
                payload: {
                    ...message.payload,
                    data: (message.payload.data || []).slice(0, 50),
                },
            };
        }),
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(compact));
    localStorage.setItem(CURRENT_KEY, currentId);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('sqla_theme', theme);
    const dark = theme === 'dark';
    $('themeIcon').textContent = dark ? 'D' : 'L';
    $('themeText').textContent = dark ? 'Chế độ tối' : 'Chế độ sáng';
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function toggleSidebar(open) {
    $('sidebar').classList.toggle('open', open);
    $('overlay').classList.toggle('show', open);
}

function renderHistory() {
    const list = $('historyList');
    list.innerHTML = '';
    conversations
        .slice()
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .forEach((conversation) => {
            const button = document.createElement('button');
            button.className = `history-item${conversation.id === currentId ? ' active' : ''}`;
            button.textContent = conversation.title;
            button.title = conversation.title;
            button.addEventListener('click', () => openConversation(conversation.id));
            list.appendChild(button);
        });
}

function openConversation(id) {
    if (!conversations.some((item) => item.id === id)) return;
    currentId = id;
    persist();
    renderHistory();
    renderConversation();
    toggleSidebar(false);
}

function newConversation() {
    const conversation = {
        id: uid(),
        title: 'Cuộc hội thoại mới',
        messages: [],
        updatedAt: Date.now(),
    };
    conversations.unshift(conversation);
    currentId = conversation.id;
    persist();
    renderHistory();
    renderConversation();
    toggleSidebar(false);
    toast('Đã tạo cuộc hội thoại mới', 'info');
}

function emptyStateNode() {
    const div = document.createElement('div');
    div.className = 'empty-state';
    div.id = 'emptyState';
    div.innerHTML = `
        <div class="empty-icon">AI</div>
        <h2>Truy vấn dữ liệu bằng ngôn ngữ tự nhiên</h2>
        <p>Planner lập kế hoạch, các agent gọi tool để đọc schema, sinh và kiểm tra SQL,
           thực thi có timeout, rồi tự sửa nếu phát hiện lỗi.</p>
        <div class="suggestions">
            <button class="chip" onclick="askExample('Top 10 pizza theo doanh thu')">Top 10 pizza theo doanh thu</button>
            <button class="chip" onclick="askExample('Tổng số đơn và doanh thu theo thành phố')">Doanh thu theo thành phố</button>
            <button class="chip" onclick="askExample('Thời gian giao hàng trung bình theo chi nhánh')">Thời gian giao trung bình</button>
        </div>`;
    return div;
}

function renderConversation() {
    charts.forEach((chart) => chart.destroy());
    charts = [];
    responseCache.clear();
    const chat = $('chat');
    chat.innerHTML = '';
    const conversation = currentConversation();
    if (!conversation || !conversation.messages.length) {
        chat.appendChild(emptyStateNode());
        return;
    }
    conversation.messages.forEach((message) => {
        if (message.role === 'user') addUserBubble(message.content);
        if (message.role === 'assistant') addAssistantResponse(message.payload);
        if (message.role === 'error') addErrorCard(message.content, message.question);
    });
    scrollChat();
}

function autoGrow(element) {
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
}

function onKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendQuestion();
    }
}

function askExample(question) {
    $('questionInput').value = question;
    sendQuestion();
}

async function sendQuestion() {
    const input = $('questionInput');
    const question = input.value.trim();
    if (!question) {
        toast('Hãy nhập câu hỏi trước khi gửi', 'info');
        return;
    }

    const conversation = currentConversation();
    conversation.messages.push({ role: 'user', content: question });
    if (conversation.messages.filter((message) => message.role === 'user').length === 1) {
        conversation.title = question.slice(0, 55);
    }
    conversation.updatedAt = Date.now();
    persist();
    renderHistory();
    renderConversation();

    input.value = '';
    autoGrow(input);
    $('sendBtn').disabled = true;
    $('metricAgent').textContent = 'Đang lập kế hoạch';
    const thinking = addThinking();

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Conversation-ID': conversation.id,
            },
            body: JSON.stringify({ question, conversation_id: conversation.id }),
        });
        const data = await response.json();
        thinking.remove();

        if (!response.ok && !data.steps) {
            conversation.messages.push({
                role: 'error',
                content: data.error || 'Yêu cầu thất bại.',
                question,
            });
            toast(data.error || 'Truy vấn thất bại', 'error');
        } else {
            conversation.messages.push({ role: 'assistant', payload: data });
            toast(
                data.success ? `Hoàn tất, ${data.total_rows} dòng` : 'Agent đã dừng an toàn sau khi hết lượt thử',
                data.success ? 'success' : 'error',
            );
        }
        conversation.updatedAt = Date.now();
        persist();
        renderConversation();
        refreshStats();
    } catch (error) {
        thinking.remove();
        conversation.messages.push({
            role: 'error',
            content: `Không kết nối được máy chủ: ${error.message}`,
            question,
        });
        persist();
        renderConversation();
        toast('Lỗi kết nối máy chủ', 'error');
    } finally {
        $('sendBtn').disabled = false;
        $('metricAgent').textContent = 'Sẵn sàng';
        scrollChat();
    }
}

function chatEl() { return $('chat'); }
function scrollChat() {
    const chat = chatEl();
    chat.scrollTop = chat.scrollHeight;
}

function addUserBubble(text) {
    const message = document.createElement('div');
    message.className = 'msg user';
    message.innerHTML = `<div class="bubble-user">${escapeHtml(text)}</div>`;
    chatEl().appendChild(message);
}

function addThinking() {
    const message = document.createElement('div');
    message.className = 'msg assistant';
    message.innerHTML = `<div class="card"><div class="card-body">
        <div class="thinking"><span class="spinner"></span>
        <span>Planner và các agent đang phối hợp<span class="dots"><span>.</span><span>.</span><span>.</span></span></span></div>
    </div></div>`;
    chatEl().appendChild(message);
    scrollChat();
    return message;
}

function addAssistantResponse(data) {
    if (!data) return;
    const message = document.createElement('div');
    message.className = 'msg assistant';
    const cacheKey = uid();
    responseCache.set(cacheKey, data);
    let html = '';

    if (data.steps?.length) {
        html += `<div class="card"><div class="card-head"><span class="ico">A</span>Trạng thái Agent
            <span class="card-meta">${data.execution_ms || 0} ms</span></div>
            <div class="card-body"><div class="timeline">${data.steps.map(stepRow).join('')}</div></div></div>`;
    }

    if (data.task_status?.length || data.plan?.length) {
        const tasks = data.task_status?.length
            ? data.task_status
            : data.plan.map((task, index) => ({ index: index + 1, task, status: 'done' }));
        html += `<div class="card"><div class="card-head"><span class="ico">P</span>Kế hoạch Plan-and-Execute</div>
            <div class="card-body"><div class="plan-list">${tasks.map((task) =>
                `<div class="plan-row ${task.status}"><span class="n">${task.index}</span>
                 <span>${escapeHtml(task.task)}</span><small>${escapeHtml(task.status)}</small></div>`).join('')}</div></div></div>`;
    }

    if (data.summary) {
        html += `<div class="card"><div class="card-head"><span class="ico">I</span>Diễn giải kết quả</div>
            <div class="card-body"><div class="summary-text">${escapeHtml(data.summary)}</div></div></div>`;
    }

    if (data.sql) {
        html += `<div class="card sql-card"><div class="card-head"><span class="ico">SQL</span>SQL đã thực thi
            ${data.retries ? `<span class="card-meta">Tự sửa ${data.retries} lần</span>` : ''}
            <div class="card-actions"><button class="mini-action" onclick="copySQLFromButton(this)">Sao chép</button></div></div>
            <div class="card-body"><div class="sql-code">${highlightSQL(data.sql)}</div></div></div>`;
    }

    if (data.retry_events?.length) {
        html += `<div class="card retry-card"><div class="card-head"><span class="ico">R</span>Feedback Loop</div>
            <div class="card-body"><div class="timeline">${data.retry_events.map((event) =>
                `<div class="tl-item retry"><span class="tl-badge">↻</span><div class="tl-main">
                <div class="tl-name">Lần ${event.attempt}: ${escapeHtml(event.analysis)}</div>
                <div class="tl-detail">${escapeHtml(event.error)}</div></div></div>`).join('')}</div></div></div>`;
    }

    if (data.data?.length) {
        const columns = Object.keys(data.data[0]);
        html += `<div class="card"><div class="card-head"><span class="ico">T</span>Kết quả (${data.total_rows} dòng)
            <div class="card-actions"><button class="mini-action" onclick="exportCSV('${cacheKey}')">Xuất CSV</button></div></div>
            <div class="card-body"><div class="table-wrap"><table class="data"><thead><tr>
            ${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>
            ${data.data.map((row) => `<tr>${columns.map((column) => `<td>${fmtCell(row[column])}</td>`).join('')}</tr>`).join('')}
            </tbody></table></div></div></div>`;
    } else if (data.success && data.sql) {
        html += `<div class="card"><div class="card-body result-empty">
            Truy vấn hợp lệ nhưng không có dòng dữ liệu phù hợp.</div></div>`;
    }

    let chartId = null;
    if (data.chart) {
        chartId = `chart_${uid()}`;
        html += `<div class="card"><div class="card-head"><span class="ico">C</span>Trực quan hóa</div>
            <div class="card-body"><div class="chart-box"><canvas id="${chartId}"></canvas></div></div></div>`;
    }

    if (!data.success && data.error) {
        html += `<div class="card error-card"><div class="card-head"><span class="ico">!</span>Graceful fallback</div>
            <div class="card-body">${escapeHtml(data.error)}</div></div>`;
    }

    message.innerHTML = html;
    chatEl().appendChild(message);
    if (chartId) setTimeout(() => renderChart(chartId, data.chart), 30);
}

function stepRow(step) {
    const icon = { done: '✓', error: '×', retry: '↻', running: '…' }[step.status] || '•';
    return `<div class="tl-item ${escapeHtml(step.status)}">
        <span class="tl-badge">${icon}</span>
        <div class="tl-main"><div class="tl-name">${escapeHtml(AGENT_LABELS[step.agent] || step.agent)}</div>
        ${step.detail ? `<div class="tl-detail">${escapeHtml(step.detail)}</div>` : ''}</div>
        ${step.duration_ms ? `<span class="tl-time">${step.duration_ms}ms</span>` : ''}</div>`;
}

function addErrorCard(message, question) {
    const element = document.createElement('div');
    element.className = 'msg assistant';
    element.innerHTML = `<div class="card error-card"><div class="card-head"><span class="ico">!</span>Lỗi kết nối</div>
        <div class="card-body">${escapeHtml(message)}
        <div><button class="btn-retry" data-question="${escapeHtml(question)}">Thử lại</button></div></div></div>`;
    element.querySelector('.btn-retry').addEventListener('click', () => askExample(question));
    chatEl().appendChild(element);
}

async function copySQLFromButton(button) {
    const text = button.closest('.card').querySelector('.sql-code')?.innerText || '';
    try {
        await navigator.clipboard.writeText(text);
        toast('Đã sao chép SQL', 'success');
    } catch {
        toast('Không thể sao chép SQL', 'error');
    }
}

function exportCSV(cacheKey) {
    const data = responseCache.get(cacheKey)?.data || [];
    if (!data.length) return;
    const columns = Object.keys(data[0]);
    const quote = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const csv = [columns.map(quote).join(','), ...data.map((row) => columns.map((column) => quote(row[column])).join(','))].join('\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }));
    link.download = `sql-result-${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
}

function renderChart(canvasId, chart) {
    const canvas = $(canvasId);
    if (!canvas || !chart?.data) return;
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    const instance = new Chart(canvas, {
        type: chart.type || 'bar',
        data: {
            labels: chart.data[chart.x_col],
            datasets: [{
                label: chart.y_col,
                data: chart.data[chart.y_col],
                backgroundColor: 'rgba(14,165,168,.72)',
                borderColor: '#0ea5a8',
                borderWidth: 1,
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: dark ? '#9aa7bd' : '#51607a' } } },
            scales: {
                x: { ticks: { color: dark ? '#9aa7bd' : '#51607a' }, grid: { display: false } },
                y: { ticks: { color: dark ? '#9aa7bd' : '#51607a' }, grid: { color: dark ? 'rgba(148,163,184,.12)' : 'rgba(15,23,42,.08)' } },
            },
        },
    });
    charts.push(instance);
}

async function openSchema() {
    toggleSidebar(false);
    $('schemaModal').classList.add('open');
    $('schemaPre').textContent = 'Đang tải...';
    try {
        const response = await fetch('/api/schema');
        const data = await response.json();
        $('schemaPre').textContent = data.schema || data.error || '(trống)';
    } catch (error) {
        $('schemaPre').textContent = `Không tải được schema: ${error.message}`;
    }
}

function closeSchema() { $('schemaModal').classList.remove('open'); }

function toast(message, type = 'info') {
    const element = document.createElement('div');
    element.className = `toast ${type}`;
    element.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '!' : 'i'}</span><span>${escapeHtml(message)}</span>`;
    $('toastWrap').appendChild(element);
    setTimeout(() => {
        element.classList.add('hide');
        setTimeout(() => element.remove(), 300);
    }, 3200);
}

async function checkHealth() {
    const chip = $('statusChip');
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        chip.className = `status-chip ${data.database_found ? 'ok' : 'bad'}`;
        $('statusText').textContent = data.database_found ? data.database : 'Thiếu CSDL';
        if (!data.llm_configured) toast('Chưa cấu hình GEMINI_API_KEY', 'info');
    } catch {
        chip.className = 'status-chip bad';
        $('statusText').textContent = 'Mất kết nối';
    }
}

async function refreshStats() {
    try {
        const data = await fetch('/api/stats').then((response) => response.json());
        $('metricQueries').textContent = data.total_queries;
        $('metricSuccess').textContent = `${data.success_rate}%`;
        $('metricLatency').textContent = `${data.average_execution_ms} ms`;
    } catch { /* health indicator already reports connection errors */ }
}

async function loadTools() {
    try {
        const data = await fetch('/api/tools').then((response) => response.json());
        $('toolList').innerHTML = data.tools
            .map((tool) => `<span class="tool-pill" title="${escapeHtml(tool.description)}">${escapeHtml(tool.name)}</span>`)
            .join('');
    } catch { $('toolList').innerHTML = ''; }
}

function escapeHtml(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, (character) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[character]));
}

function fmtCell(value) {
    if (value === null || value === undefined) return '<span class="cell-null">null</span>';
    if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
    return escapeHtml(String(value));
}

function highlightSQL(sql) {
    let html = escapeHtml(sql);
    html = html.replace(/\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|ORDER|GROUP|BY|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AS|DISTINCT|COUNT|SUM|AVG|MIN|MAX|UPPER|LOWER|ROUND|COALESCE|CAST|CASE|WHEN|THEN|ELSE|END|BETWEEN|LIKE|EXISTS|UNION|ALL|WITH|ASC|DESC)\b/gi, '<span class="kw">$1</span>');
    html = html.replace(/&#039;([^&]*)&#039;/g, '<span class="str">&#039;$1&#039;</span>');
    return html;
}

applyTheme(localStorage.getItem('sqla_theme') || 'dark');
renderHistory();
renderConversation();
checkHealth();
refreshStats();
loadTools();
