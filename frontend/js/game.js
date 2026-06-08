// ==================== 角色模块（由 roles/*.js 挂载到 window.RoleActions） ====================
// 角色模块通过 window.RoleActions['狼人'/'预言家'/'女巫'/'村民'] 访问

function getCurrentRoleActions() {
    var actions = window.RoleActions || {};
    return actions[currentRole] || actions['村民'] || {};
}

// ==================== 星空背景 ====================
function createStars() {
    const stars = document.getElementById('stars');
    for (let i = 0; i < 120; i++) {
        const star = document.createElement('div');
        star.className = 'star';
        star.style.left = Math.random() * 100 + '%';
        star.style.top = Math.random() * 100 + '%';
        star.style.animationDelay = Math.random() * 2 + 's';
        star.style.width = (Math.random() * 2 + 1) + 'px';
        star.style.height = star.style.width;
        stars.appendChild(star);
    }
}

// ==================== 全局状态 ====================
let gameId = null;
let currentRole = '';
let selectedVoteTarget = null;
let gameState = null;
let chosenRole = null;
let numPlayers = 6;
let roleConfig = null;
let autoPlayTimer = null;   // 观战模式自动推进定时器
let votingInProgress = false;
let voteProgressLog = [];
let isDisplayingMessages = false;  // 是否正在逐条播放系统消息
let nightFlowRunning = false;     // 夜晚引导 SSE 是否正在运行
let nightFlowReady = false;       // 引导已播完，可以展示操作 UI
let nightResumePhase = null;      // 续播阶段：null/seer/witch
let dayIntroRunning = false;      // 防止 startDayIntro 被重复调用
let pendingHumanPosition = 0;     // 人类玩家在发言顺序中的位置（用于续播）
let tieBreakState = { active: false, round: 0, candidates: [] };
let votedOutPlayers = {};         // 被投票出局的玩家 ID → true，其身份公开可见
// 预言家查验结果存 window.checkedRoles，seer.js 的 handleDoneEvent 写入

function isSpectator() {
    return gameState && !gameState.alive_players.includes(1);
}

// ==================== 角色 Emoji 映射 ====================
const ROLE_EMOJI = {
    '狼人': '\u{1F43A}',
    '预言家': '\u{1F52E}',
    '女巫': '\u{1F9D9}',
    '村民': '\u{1F464}'
};

const ROLE_DESC = {
    '狼人': '每晚可以杀死一名玩家',
    '预言家': '每晚可以查验一名玩家的身份',
    '女巫': '拥有一瓶解药和一瓶毒药',
    '村民': '没有特殊技能，通过投票消灭狼人'
};

const PHASE_TEXT = {
    waiting: '⏳ 等待开始',
    night: '\u{1F319} 夜晚',
    day: '☀️ 白天',
    vote: '\u{1F5F3}️ 投票',
    ended: '\u{1F3C6} 游戏结束'
};

function getRoleEmoji(role) {
    return ROLE_EMOJI[role] || '\u{1F464}';
}

function getPhaseText(phase) {
    return PHASE_TEXT[phase] || phase;
}

// ==================== 初始化 ====================
createStars();

// ==================== 玩家/角色选择 ====================
function selectPlayers(num) {
    numPlayers = num;
    const buttons = document.querySelectorAll('.player-btn');
    buttons.forEach(btn => {
        btn.style.border = '2px solid rgba(139, 92, 246, 0.3)';
        btn.style.background = 'rgba(255, 255, 255, 0.05)';
    });
    const selectedBtn = Array.from(buttons).find(btn => btn.textContent.includes(num + '人'));
    if (selectedBtn) {
        selectedBtn.style.border = '2px solid #8b5cf6';
        selectedBtn.style.background = 'rgba(139, 92, 246, 0.3)';
    }
    fetchRoleConfig(num);
}

async function fetchRoleConfig(num) {
    try {
        const res = await fetch(`/api/game/role-config/${num}`);
        const data = await res.json();
        roleConfig = data;

        const display = document.getElementById('role-config-display');
        display.innerHTML = `
            <div>角色配置: ${data.role_count['狼人']}狼人 ${data.role_count['预言家']}预言家 ${data.role_count['女巫']}女巫 ${data.role_count['村民']}村民</div>
        `;

        const roleSelection = document.getElementById('role-selection');
        const availableRoles = document.getElementById('available-roles');
        roleSelection.style.display = 'block';

        const uniqueRoles = [...new Set(data.roles)];
        availableRoles.innerHTML = uniqueRoles.map(role => `
            <button class="role-btn" onclick="selectRole('${role}')">${getRoleEmoji(role)} ${role}</button>
        `).join('') + '<button class="role-btn random" onclick="selectRole(null)">\u{1F3B2} 随机</button>';

    } catch (error) {
        console.error('获取角色配置失败:', error);
    }
}

function selectRole(role) {
    chosenRole = role;
    const buttons = document.querySelectorAll('.role-btn');
    buttons.forEach(btn => {
        btn.style.border = '2px solid rgba(139, 92, 246, 0.3)';
        btn.style.background = 'rgba(255, 255, 255, 0.05)';
    });

    if (role) {
        const selectedBtn = Array.from(buttons).find(btn => btn.textContent.includes(role));
        if (selectedBtn) {
            selectedBtn.style.border = '2px solid #8b5cf6';
            selectedBtn.style.background = 'rgba(139, 92, 246, 0.3)';
        }
    } else {
        const randomBtn = document.querySelector('.role-btn.random');
        if (randomBtn) {
            randomBtn.style.border = '2px solid #fbbf24';
            randomBtn.style.background = 'rgba(251, 191, 36, 0.2)';
        }
    }

    document.getElementById('start-btn').disabled = false;
}

// ==================== 游戏流程 ====================
async function startGame() {
    // 清除观战自动推进定时器
    if (autoPlayTimer) { clearTimeout(autoPlayTimer); autoPlayTimer = null; }
    votingInProgress = false;
    voteProgressLog = [];
    messageQueue = [];
    messageQueueTimer = null;
    messageQueueCallback = null;
    isDisplayingMessages = false;
    nightFlowRunning = false;
    nightFlowReady = false;
    nightResumePhase = null;
    dayIntroRunning = false;
    pendingHumanPosition = 0;
    votedOutPlayers = {};
    window.checkedRoles = {};

    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('game-container').style.display = 'block';
    document.getElementById('game-over-overlay').style.display = 'none';

    const res = await fetch('/api/game/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            num_players: numPlayers,
            human_player_id: 1,
            human_role: chosenRole
        })
    });
    const data = await res.json();
    gameId = data.game_id;

    // JSON 序列化后 dict key 变为字符串，所以用 data.player_roles["1"]
    currentRole = data.player_roles && data.player_roles["1"];
    gameState = data;

    showRoleReveal(currentRole || '村民', function() {
        renderState(data);
        renderSpeeches(data.history);
    });
}

function showRoleReveal(role, onDismiss) {
    const overlay = document.createElement('div');
    overlay.id = 'role-reveal-overlay';
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0, 0, 0, 0.95);
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        z-index: 1000; animation: fadeIn 0.5s ease-in;
    `;

    // 获取当前角色的额外揭示信息（如狼人队友）
    const actions = window.RoleActions || {};
    const roleActions = actions[role] || actions['村民'] || {};
    const extraHtml = roleActions.getRoleRevealExtra ? roleActions.getRoleRevealExtra(gameState) : '';

    overlay.innerHTML = `
        <div style="text-align: center; animation: zoomIn 0.5s ease-out;">
            <div style="font-size: 80px; margin-bottom: 20px;">${getRoleEmoji(role)}</div>
            <div style="font-size: 36px; color: #c084fc; margin-bottom: 10px; font-weight: bold;">你的身份是</div>
            <div style="font-size: 48px; color: #fbbf24; margin-bottom: 20px; font-weight: bold; text-shadow: 0 0 20px rgba(251, 191, 36, 0.5);">${role}</div>
            <div style="font-size: 18px; color: #9ca3af; margin-bottom: 20px; max-width: 400px;">${ROLE_DESC[role] || ''}</div>
            ${extraHtml}
            <button id="role-confirm-btn" style="
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                color: white; border: none; padding: 15px 50px; font-size: 20px;
                border-radius: 10px; cursor: pointer; transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(139, 92, 246, 0.4); margin-top: 30px;
            ">开始游戏</button>
        </div>
        <style>
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            @keyframes zoomIn { from { transform: scale(0.5); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        </style>
    `;

    document.body.appendChild(overlay);
    document.getElementById('role-confirm-btn').addEventListener('click', () => {
        overlay.style.animation = 'fadeIn 0.3s ease-out reverse';
        setTimeout(() => {
            overlay.remove();
            if (onDismiss) onDismiss();
        }, 300);
    });
}

// ==================== 预言家查验结果弹窗 ====================
function showSeerResult(targetPid, targetRole) {
    var name = (gameState && gameState.player_names && gameState.player_names[targetPid]) || ('玩家' + targetPid);
    var emoji = getRoleEmoji(targetRole);
    var isGood = targetRole === '村民' || targetRole === '预言家' || targetRole === '女巫';
    var badgeColor = isGood ? '#4ade80' : '#ef4444';
    var badgeText = isGood ? '好人阵营' : '狼人阵营';

    var modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
        'background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;' +
        'z-index:1001;animation:fadeIn 0.3s ease-in;';
    modal.innerHTML = '<div style="text-align:center;animation:zoomIn 0.3s ease-out;' +
        'background:linear-gradient(135deg,#1e1b4b 0%,#312e81 50%,#1e1b4b 100%);' +
        'border:1px solid rgba(139,92,246,0.5);border-radius:20px;padding:40px 50px;' +
        'box-shadow:0 0 40px rgba(139,92,246,0.3);max-width:420px;">' +
        '<div style="font-size:64px;margin-bottom:15px;">' + emoji + '</div>' +
        '<div style="font-size:20px;color:#c084fc;margin-bottom:5px;">🔮 预言家查验结果</div>' +
        '<div style="font-size:32px;color:#fbbf24;font-weight:bold;margin-bottom:10px;">' + name + ' (' + targetPid + '号)</div>' +
        '<div style="display:inline-block;padding:6px 20px;border-radius:20px;' +
        'font-size:18px;font-weight:bold;background:' + badgeColor + '22;color:' + badgeColor + ';' +
        'border:1px solid ' + badgeColor + '44;margin-bottom:20px;">' + targetRole + ' · ' + badgeText + '</div>' +
        '<div><button style="background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border:none;' +
        'padding:12px 40px;font-size:16px;border-radius:10px;cursor:pointer;' +
        'box-shadow:0 4px 15px rgba(139,92,246,0.4);">我知道了</button></div></div>';

    document.body.appendChild(modal);
    modal.querySelector('button').addEventListener('click', function() {
        modal.style.animation = 'fadeIn 0.2s ease-out reverse';
        setTimeout(function() { modal.remove(); }, 200);
    });
    // 点击背景也可关闭
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.animation = 'fadeIn 0.2s ease-out reverse';
            setTimeout(function() { modal.remove(); }, 200);
        }
    });
}

// ==================== 状态渲染 ====================
function scheduleAutoPlay(phase) {
    if (autoPlayTimer) clearTimeout(autoPlayTimer);
    if (phase === 'ended') return;
    autoPlayTimer = setTimeout(() => {
        autoPlayTimer = null;
        if (!isSpectator()) return;
        if (phase === 'night') executeNightAction();
        else if (phase === 'day') executeDayAction();
        else if (phase === 'vote') executeVoteAction(true);
    }, 2500);
}

async function refreshState() {
    if (!gameId) return;
    const res = await fetch(`/api/game/state/${gameId}`);
    const data = await res.json();

    if (data.error) {
        console.error('获取状态失败:', data.error);
        return;
    }

    gameState = data;
    renderState(data);
    // 注意：不调 renderSpeeches，SSE 流已实时逐条显示所有消息，避免重复

    // 观战模式：自动推进游戏
    if (isSpectator() && data.phase !== 'ended') {
        scheduleAutoPlay(data.phase);
    }
}

function renderState(state) {
    document.getElementById('day-num').textContent = state.day;

    const phaseDisplay = document.getElementById('phase-display');
    phaseDisplay.className = `phase-badge phase-${state.phase}`;
    phaseDisplay.textContent = getPhaseText(state.phase);

    document.getElementById('winner-area').innerHTML = state.winner
        ? `<div class="winner-display">\u{1F3C6} ${state.winner}获胜!</div>`
        : '';

    renderPlayers(state);
    renderActionArea(state);
}

function renderPlayers(state) {
    const spectating = isSpectator();
    const roleActions = getCurrentRoleActions();
    let html = '';
    const sortedPids = Object.keys(state.player_names).map(Number).sort((a, b) => a - b);

    for (const pid of sortedPids) {
        const name = state.player_names[pid];
        const isAlive = state.alive_players.includes(pid);
        const role = state.player_roles[pid];
        const isHuman = pid === 1;
        // 预言家查验结果只有预言家自己能看见
        var isSeer = currentRole === '预言家';
        var seerChecks = (isSeer && window.checkedRoles) ? window.checkedRoles : {};
        const checkedRole = seerChecks[pid];
        // 身份可见条件：自己、观战、被投票出局、角色模块允许、预言家查验(仅预言家本人可见)
        const roleVisible = isHuman || spectating || votedOutPlayers[pid] ||
            (isSeer && checkedRole) ||
            (roleActions.shouldShowPlayerRole && roleActions.shouldShowPlayerRole(pid, role, state));
        const showRole = roleVisible;
        const displayRole = checkedRole || role;  // 查验过的用查验结果，否则用真实角色
        const votedOut = votedOutPlayers[pid];
        const statusClass = isAlive ? 'status-alive' : (votedOut ? 'status-voted-out' : 'status-dead');
        const statusText = isAlive ? '存活' : (votedOut ? '已出局' : '死亡');
        const votedOutClass = votedOut ? 'voted-out' : '';

        html += `
            <div class="player-item ${isAlive ? 'alive' : 'dead'} ${isHuman ? 'human' : ''} ${votedOutClass}">
                <div class="player-avatar">${getRoleEmoji(showRole ? displayRole : '村民')}</div>
                <div class="player-info">
                    <div class="player-name">${name} (${pid}号)${isHuman ? ' <span style="color:#3b82f6">(你)</span>' : ''}${checkedRole ? ' <span style="font-size:10px;color:#60a5fa;">🔍</span>' : ''}</div>
                    <div class="player-role">${showRole ? displayRole : '???'}${votedOut ? ' <span style="font-size:10px;color:#fbbf24;">(已翻牌)</span>' : (checkedRole ? ' <span style="font-size:10px;color:#60a5fa;">(已查验)</span>' : '')}</div>
                </div>
                <div class="player-status ${statusClass}">
                    ${statusText}
                </div>
            </div>
        `;
    }
    document.getElementById('player-list').innerHTML = html;
}

function renderSpeeches(history) {
    const spectating = isSpectator();
    let html = '';

    for (const event of history) {
        const content = event.content || '';

        // 私密事件 — 观战模式下显示
        if (event.type === 'kill' || event.type === 'check' ||
            event.type === 'poison' || event.type === 'save') {
            if (!spectating) continue;
            let cls = 'death';
            if (event.type === 'check') cls = 'seer';
            else if (event.type === 'save') cls = 'peace';
            else if (event.type === 'poison') cls = 'witch';
            html += `<div class="speech-system ${cls}">🔍 ${content}</div>`;
            continue;
        }

        // 游戏开始事件不显示
        if (event.type === 'start') {
            continue;
        }

        // 系统提示 — 嵌入式法官消息
        if (event.type === 'system') {
            let cls = '';
            if (content.includes('夜晚到来') || content.includes('请闭眼') || content.includes('天夜晚'))
                cls = 'night';
            else if (content.includes('狼人请睁眼') || content.includes('狼人'))
                cls = 'wolf';
            else if (content.includes('预言家'))
                cls = 'seer';
            else if (content.includes('女巫'))
                cls = 'witch';
            else if (content.includes('天亮') || content.includes('天到来') || content.includes('请睁眼'))
                cls = 'day';
            else if (content.includes('投票') || content.includes('平票'))
                cls = 'vote';
            else if (content.includes('死亡') || content.includes('出局'))
                cls = 'death';
            else if (content.includes('平安夜'))
                cls = 'peace';
            else if (content.includes('胜利'))
                cls = 'win';
            else
                cls = 'day';
            html += `<div class="speech-system ${cls}">${content}</div>`;
            continue;
        }

        // 发言 — 聊天气泡
        if (event.type === 'speak') {
            const speakerName = gameState?.player_names?.[event.player_id] || `玩家${event.player_id}`;
            const isSelf = event.player_id === 1;
            const label = isSelf ? `${speakerName}（你）` : `${speakerName}`;
            html += `
                <div class="speech-bubble ${isSelf ? 'self' : 'other'}">
                    <div class="bubble-header">${label}</div>
                    <div class="bubble-body">${content.replace(/\n/g, '<br>')}</div>
                </div>`;
            continue;
        }

        // 淘汰 / 投票结果 — 嵌入式系统消息
        if (event.type === 'eliminate') {
            html += `<div class="speech-system death">⚰️ ${event.target || event.player_id}号玩家被投票出局</div>`;
            continue;
        }

        if (event.type === 'vote') {
            html += `<div class="speech-system">🗳️ ${content.replace(/\n/g, '<br>')}</div>`;
            continue;
        }

        if (event.type === 'vote_summary') {
            html += `<div class="speech-system vote">📊 ${content.replace(/\n/g, '<br>')}</div>`;
            continue;
        }
    }

    document.getElementById('speech-content').innerHTML = html;
    const container = document.getElementById('speech-content');
    container.scrollTop = container.scrollHeight;
}

// ==================== 操作区域 ====================
function renderActionArea(state) {
    const actionTitle = document.getElementById('action-title');
    const actionContent = document.getElementById('action-content');

    // —— 观战模式：人类已淘汰，禁止操作，自动推进 ——
    if (isSpectator() && state.phase !== 'ended') {
        const phaseLabel = state.phase === 'night' ? '夜晚阶段' :
                           state.phase === 'day' ? '发言阶段' : '投票阶段';
        actionTitle.textContent = '\u{1F441}️ 观战模式';
        actionContent.innerHTML = `
            <div style="text-align: center; padding: 30px;">
                <div style="font-size: 48px; margin-bottom: 15px;">\u{1F480}</div>
                <div style="font-size: 18px; color: #ef4444; font-weight: bold; margin-bottom: 10px;">你已被淘汰</div>
                <div style="color: #9ca3af; font-size: 14px; margin-bottom: 5px;">当前：${phaseLabel}</div>
                <div style="color: #6b7280; font-size: 13px;">AI 玩家将自动继续游戏，你可以观战</div>
                <div class="loading-spinner" style="margin-top: 20px;"></div>
            </div>
        `;
        return;
    }

    if (state.phase === 'night') {
        // 狼人/预言家/女巫统一：先播引导消息 → 到对应阶段暂停 → 再出击杀/查验/药水 UI
        if (!nightFlowRunning && !nightFlowReady) {
            actionTitle.textContent = '\u{1F319} 夜晚';
            actionContent.innerHTML = '<div style="text-align:center;padding:25px;"><div class="loading-spinner"></div><div style="color:#c084fc;margin-top:15px;">夜晚降临...</div></div>';
            startNightFlow();
        } else {
            actionTitle.textContent = '\u{1F319} 夜晚行动';
            var nightHTML = getCurrentRoleActions().renderNightActions(state);
            actionContent.innerHTML = nightHTML || '<div style="text-align:center;padding:30px;color:#9ca3af;">⏳ 等待夜晚阶段...</div>';
        }
    } else if (state.phase === 'day') {
        // 首次进入白天 → 先播其他玩家发言，轮到人类再出输入框
        if (!dayIntroRunning && pendingHumanPosition === 0) {
            actionTitle.textContent = '\u{1F4AC} 发言阶段';
            actionContent.innerHTML = '<div style="text-align:center;padding:25px;"><div class="loading-spinner"></div><div style="color:#c084fc;margin-top:15px;">其他玩家正在发言...</div></div>';
            startDayIntro();
        } else if (pendingHumanPosition > 0) {
            // 轮到人类玩家发言 → 显示输入框
            actionTitle.textContent = '\u{1F4AC} 轮到你发言';
            actionContent.innerHTML = renderDayActions(state);
        } else {
            // 等待中或AI发言结束后 → 不显示输入框
            actionTitle.textContent = '\u{1F4AC} 发言阶段';
            actionContent.innerHTML = '<div style="text-align:center;padding:25px;"><div class="loading-spinner"></div><div style="color:#c084fc;margin-top:15px;">其他玩家正在发言...</div></div>';
        }
    } else if (state.phase === 'vote') {
        actionTitle.textContent = '\u{1F5F3}️ 投票';
        actionContent.innerHTML = renderVoteActions(state);
    } else if (state.phase === 'ended') {
        actionTitle.textContent = '\u{1F3C6} 游戏结束';
        actionContent.innerHTML = `
            <div style="text-align: center;">
                <div style="font-size: 24px; color: #fbbf24; margin-bottom: 20px;">${state.winner}获胜!</div>
                <button class="action-btn" onclick="startGame()">再来一局</button>
            </div>
        `;
        showGameOver(state);
    }
}

// ==================== 实时追加发言气泡 / 系统消息 ====================
function getSystemClass(content) {
    if (content.includes('夜晚到来') || content.includes('请闭眼') || content.includes('天夜晚')) return 'night';
    if (content.includes('狼人请睁眼') || content.includes('狼人')) return 'wolf';
    if (content.includes('预言家')) return 'seer';
    if (content.includes('女巫')) return 'witch';
    if (content.includes('天亮') || content.includes('天到来') || content.includes('请睁眼')) return 'day';
    if (content.includes('投票') || content.includes('平票')) return 'vote';
    if (content.includes('死亡') || content.includes('出局')) return 'death';
    if (content.includes('平安夜')) return 'peace';
    if (content.includes('胜利')) return 'win';
    return 'day';
}

function appendSystemMessage(content) {
    const container = document.getElementById('speech-content');
    const cls = getSystemClass(content);
    const div = document.createElement('div');
    div.className = `speech-system ${cls}`;
    div.textContent = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function appendSpeechBubble(speech) {
    const container = document.getElementById('speech-content');
    const isSelf = speech.player_id === 1;
    const speakerName = speech.name || `玩家${speech.player_id}`;
    const label = isSelf ? `${speakerName}（你）` : `${speakerName}`;
    const content = (speech.content || '').replace(/\n/g, '<br>');

    const bubble = document.createElement('div');
    bubble.className = `speech-bubble ${isSelf ? 'self' : 'other'}`;
    bubble.innerHTML = `
        <div class="bubble-header">${label}</div>
        <div class="bubble-body">${content}</div>
    `;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

// ==================== 投票结果可视化面板 ====================
function appendVoteSummaryPanel(data) {
    var container = document.getElementById('speech-content');
    if (!data || !data.voters) return;

    var voters = data.voters || [];
    var results = data.results || [];

    // Build voter chips
    var voterHTML = '';
    for (var i = 0; i < voters.length; i++) {
        var v = voters[i];
        var isSelf = v.id === 1;
        var cls = 'vote-chip';
        if (isSelf) cls += ' self';
        if (v.is_abstain) cls += ' abstain';

        if (v.is_abstain) {
            voterHTML += '<span class="' + cls + '">' + v.name + '(' + v.id + '号) → 弃权</span>';
        } else {
            voterHTML += '<span class="' + cls + '">' + v.name + '(' + v.id + '号) → ' + v.target_name + '(' + v.target + '号)</span>';
        }
    }

    // Build result bars
    var maxCount = 0;
    for (var j = 0; j < results.length; j++) {
        if (results[j].count > maxCount) maxCount = results[j].count;
    }

    var resultHTML = '';
    for (var k = 0; k < results.length; k++) {
        var r = results[k];
        var pct = maxCount > 0 ? Math.round(r.count / maxCount * 100) : 100;
        var isTop = r.count === maxCount && maxCount > 0;
        var barCls = isTop ? 'vote-bar-fill top' : 'vote-bar-fill';
        resultHTML +=
            '<div class="vote-result-row">' +
            '<div class="vote-result-label">' + r.name + '(' + r.id + '号)</div>' +
            '<div class="vote-bar-track"><div class="' + barCls + '" style="width:' + pct + '%"></div></div>' +
            '<div class="vote-result-count">' + r.count + '票</div>' +
            '</div>';
    }

    if (results.length === 0) {
        resultHTML = '<div class="vote-no-result">本轮无人投票</div>';
    }

    var panel = document.createElement('div');
    panel.className = 'vote-summary-panel';
    panel.innerHTML =
        '<div class="vote-summary-header">📊 投票结果</div>' +
        '<div class="vote-summary-voters">' + voterHTML + '</div>' +
        '<div class="vote-summary-results">' + resultHTML + '</div>';

    container.appendChild(panel);
    container.scrollTop = container.scrollHeight;
}

// ==================== SSE 事件队列 — 按后端顺序逐条显示 ====================
let eventQueue = [];             // 待显示的事件队列
let eventQueueTimer = null;      // 当前定时器
let eventQueueCallback = null;   // 队列清空后的回调（用于 done 事件）

function enqueueEvent(event) {
    eventQueue.push(event);
    if (!eventQueueTimer) {
        processEventQueue();
    }
}

function processEventQueue() {
    if (eventQueue.length === 0) {
        eventQueueTimer = null;
        isDisplayingMessages = false;
        if (eventQueueCallback) {
            const cb = eventQueueCallback;
            eventQueueCallback = null;
            cb();
        }
        return;
    }

    isDisplayingMessages = true;

    const event = eventQueue.shift();
    if (event.type === 'system' || event.type === 'result') {
        appendSystemMessage(event.content);
    } else if (event.type === 'speech' || event.type === 'tie_speech') {
        appendSpeechBubble(event);
    } else if (event.type === 'vote') {
        appendSystemMessage(event.content);
    } else if (event.type === 'vote_summary') {
        appendVoteSummaryPanel(event.data);
    }

    eventQueueTimer = setTimeout(processEventQueue, 1000);
}

function enqueueMessage(content) {
    enqueueEvent({ type: 'system', content });
}

function onStreamComplete(callback) {
    if (eventQueueTimer || eventQueue.length > 0) {
        eventQueueCallback = callback;
    } else {
        callback();
    }
}

// ==================== 白天发言 ====================
function renderDayActions(state) {
    const speakingOrder = state.speaking_order || [];
    const firstSpeaker = speakingOrder.length > 0 ? speakingOrder[0] : null;

    let orderHtml = '';
    if (speakingOrder.length > 0) {
        orderHtml = `
            <div style="margin-bottom: 20px; padding: 15px; background: rgba(255, 255, 255, 0.05); border-radius: 10px;">
                <div style="font-size: 14px; color: #a78bfa; margin-bottom: 10px;">\u{1F4E2} 发言顺序</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                    ${speakingOrder.map(pid => {
                        const name = state.player_names[pid] || `玩家${pid}`;
                        const isHuman = pid === 1;
                        return `<span style="padding: 6px 12px; border-radius: 20px; font-size: 12px;
                            background: ${isHuman ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.1)'};
                            color: ${isHuman ? '#60a5fa' : '#9ca3af'}; border: 1px solid transparent;">
                            ${isHuman ? '\u{1F3AD} ' : ''}${name} (${pid}号)</span>`;
                    }).join('')}
                </div>
            </div>
        `;
    }

    let hint = '';
    if (firstSpeaker === 1) {
        hint = '<div style="color: #3b82f6; margin-bottom: 10px; font-weight: bold;">\u{1F3A4} 你是第一个发言，请发表你的看法</div>';
    } else if (firstSpeaker !== null) {
        const firstName = state.player_names[firstSpeaker] || `玩家${firstSpeaker}`;
        hint = `<div style="color: #fbbf24; margin-bottom: 10px;">\u{1F4E2} ${firstName} 将首先发言，输入你的发言后点击发送即可</div>`;
    }

    return `
        ${orderHtml}
        ${hint}
        <textarea class="action-input" id="speak-content" rows="4" placeholder="输入你的发言..."></textarea>
        <button class="action-btn" onclick="executeDayAction()">\u{1F4E8} 发送发言</button>
    `;
}

// ==================== 投票 ====================
function renderVoteActions(state) {
    const alivePlayers = state.alive_players;

    if (votingInProgress || (tieBreakState.active && !tieBreakState.waitingForInput)) {
        let progressHtml = '';
        for (const entry of voteProgressLog) {
            const icon = entry.is_abstain ? '○' : '✓';
            const action = entry.is_abstain ? '弃权' : `投给了 ${entry.target} 号`;
            progressHtml += `
                <div style="padding: 6px 0; color: #9ca3af; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    ${icon} ${entry.name}（${entry.player_id}号）${action}
                </div>`;
        }

        const tieHint = tieBreakState.active ? `
            <div style="color: #facc15; margin-top: 10px; font-size: 14px;">
                ⚖️ 第 ${tieBreakState.round} 轮平票重投候选: ${tieBreakState.candidates.map(c => c + '号').join('、')}
            </div>` : '';

        return `
            <div style="text-align: center; padding: 30px 0;">
                <div class="loading-spinner"></div>
                <div style="color: #c084fc; margin: 15px 0; font-size: 16px;">🤖 AI 玩家正在投票...</div>
                <div style="color: #6b7280; font-size: 13px;">并行处理中，请稍候</div>
                ${tieHint}
                ${progressHtml ? `
                    <div style="margin-top: 20px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; text-align: left; max-height: 200px; overflow-y: auto;">
                        ${progressHtml}
                    </div>` : ''}
            </div>
        `;
    }

    // 获取当前角色禁止投票的目标（如狼人不能投队友），平票/正常投票统一应用
    const roleActions = getCurrentRoleActions();
    const forbiddenTargets = (roleActions.getForbiddenTargets && roleActions.getForbiddenTargets(state)) || [];
    const forbiddenSet = {};
    forbiddenTargets.forEach(function(id) { forbiddenSet[id] = true; });

    // 平票重投：展示候选人 + PK 发言输入框
    if (tieBreakState && tieBreakState.active) {
        const allCandidates = tieBreakState.candidates || [];
        // 排除禁止投票的目标（如狼人队友）
        const candidates = allCandidates.filter(function(p) { return !forbiddenSet[p]; });
        const candidateSet = {};
        candidates.forEach(function(c) { candidateSet[c] = true; });

        if (candidates.length === 0) {
            return '<div style="text-align:center;padding:30px;color:#f87171;">⚠️ 所有平票候选人均为禁止投票目标，请等待系统处理...</div>';
        }

        const hint = '<div style="color:#facc15;font-size:14px;margin-bottom:10px;">⚖️ 第 ' + tieBreakState.round + ' 轮平票重投候选: ' + candidates.map(function(c) { return c + '号'; }).join('、') + '</div>';

        var tieVoteHtml = '';
        for (var i = 0; i < candidates.length; i++) {
            var p = candidates[i];
            tieVoteHtml += '<button class="vote-target-btn ' + (selectedVoteTarget === p ? 'selected' : '') + '" onclick="selectVoteTarget(' + p + ')"><div>' + state.player_names[p] + '</div><div style="font-size:12px;opacity:0.7;">' + p + '号</div></button>';
        }

        return hint + '<div class="vote-panel">' + tieVoteHtml + '</div>' +
            '<div style="margin-top:12px;">' +
            '<div style="color:#f87171;font-size:12px;margin-bottom:5px;">⚠️ 你是平票候选人，必须输入PK发言</div>' +
            '<textarea class="action-input" id="tie-speech-content" rows="4" placeholder="输入你的PK发言（必填）..."></textarea>' +
            '</div>' +
            '<div style="display:flex;gap:10px;margin-top:12px;">' +
            '<button class="action-btn" onclick="submitTieSpeechAndVote()">提交发言并重投</button>' +
            '</div>';
    }

    var voteHint = '';
    if (forbiddenTargets.length > 0) {
        voteHint = '<div style="color:#f87171;font-size:12px;margin-bottom:10px;">🚫 你不能投票给队友</div>';
    }

    return `
        ${voteHint}
        <div class="vote-panel">
            ${alivePlayers.map(p => {
                const isForbidden = forbiddenSet[p];
                if (isForbidden) {
                    // 禁止投票的玩家：显示但不能点击
                    return `
                        <button class="vote-target-btn dead" disabled
                            style="opacity:0.35;cursor:not-allowed;border-color:rgba(239,68,68,0.3);background:rgba(239,68,68,0.08);">
                            <div>${state.player_names[p]}</div>
                            <div style="font-size:12px;opacity:0.7;">${p}号 🚫</div>
                        </button>`;
                }
                return `
                    <button class="vote-target-btn ${selectedVoteTarget === p ? 'selected' : ''}"
                        onclick="selectVoteTarget(${p})">
                        <div>${state.player_names[p]}</div>
                        <div style="font-size:12px;opacity:0.7;">${p}号</div>
                    </button>`;
            }).join('')}
        </div>
        <div style="display: flex; gap: 10px;">
            <button class="action-btn" ${selectedVoteTarget === null ? 'disabled' : ''} onclick="executeVoteAction()">确认投票</button>
            <button class="action-btn" style="background: rgba(255, 255, 255, 0.1);" onclick="executeVoteAction(true)">弃权</button>
        </div>
    `;
}

function selectVoteTarget(target) {
    selectedVoteTarget = selectedVoteTarget === target ? null : target;
    refreshState();
}

// 在平票PK环节提交发言并触发重投
function submitTieSpeechAndVote() {
    const speakEl = document.getElementById('tie-speech-content');
    const candidateSet = {};
    (tieBreakState.candidates || []).forEach(function(c) { candidateSet[c] = true; });

    // 必须输入 PK 发言
    const content = (speakEl && speakEl.value || '').trim();
    if (content.length === 0) {
        alert('你是平票候选人，必须输入PK发言才能提交');
        return;
    }

    // 必须选定重投目标
    if (selectedVoteTarget === null || !candidateSet[selectedVoteTarget]) {
        alert('请选择一个平票候选人作为重投目标');
        return;
    }

    // 发起重投（extra_speeches 会被后端插入到历史中）
    votingInProgress = true;
    voteProgressLog = [];
    tieBreakState.waitingForInput = false;
    renderActionArea(gameState);
    executeVoteAction(false, [{ player_id: 1, content: content }]);
}

// ==================== API 调用 ====================
async function executeWolfAction() {
    try {
        const res = await fetch('/api/game/execute-wolf-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId })
        });
        const data = await res.json();

        if (data.error) {
            alert('狼人AI行动失败: ' + data.error);
            return;
        }
        refreshState();
    } catch (error) {
        console.error('请求失败:', error);
        alert('请求失败: ' + error.message);
    }
}

// ==================== 夜晚引导（狼人两段式第一段） ====================
async function startNightFlow() {
    if (nightFlowRunning) return;
    nightFlowRunning = true;
    nightFlowReady = false;

    const params = { game_id: gameId };

    try {
        const res = await fetch('/api/game/night-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        if (!res.ok) {
            const err = await res.json();
            alert('夜晚开始失败: ' + (err.error || '未知错误'));
            nightFlowRunning = false;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'system') {
                            enqueueMessage(event.content);
                        } else if (event.type === 'seer_result') {
                            // 只有预言家能看到查验结果
                            if (currentRole === '预言家') {
                                window.checkedRoles = window.checkedRoles || {};
                                window.checkedRoles[event.checked] = event.checked_role;
                                if (gameState) renderState(gameState);
                                showSeerResult(event.checked, event.checked_role);
                            }
                        } else if (event.type === 'awaiting_wolf_target') {
                            // 狼人 → 展示击杀 UI，二段只跳 intro 不跳狼人逻辑
                            nightFlowReady = true;
                            nightFlowRunning = false;
                            nightResumePhase = null;
                            onStreamComplete(function() {
                                renderActionArea(gameState);
                            });
                            return;
                        } else if (event.type === 'awaiting_seer_target') {
                            // 预言家 → 展示查验 UI，后续续播跳过狼人
                            nightFlowReady = true;
                            nightFlowRunning = false;
                            nightResumePhase = 'seer';
                            onStreamComplete(function() {
                                renderActionArea(gameState);
                            });
                            return;
                        } else if (event.type === 'awaiting_witch_action') {
                            // 女巫 → 先刷新状态获取狼人击杀目标，再展示药水 UI
                            nightFlowReady = true;
                            nightFlowRunning = false;
                            nightResumePhase = 'witch';
                            onStreamComplete(function() {
                                refreshState();  // 刷新 gameState 以获取 werewolf_kill_target
                            });
                            return;
                        } else if (event.type === 'result') {
                            enqueueMessage(event.content);
                        } else if (event.type === 'done') {
                            // 不需要人类操作（村民/已死亡）→ 正常结束
                            nightFlowRunning = false;
                            nightFlowReady = false;
                            onStreamComplete(function() {
                                refreshState();
                            });
                        } else if (event.type === 'error') {
                            nightFlowRunning = false;
                            alert(event.message);
                        }
                    } catch (e) {
                        console.error('解析 SSE 事件失败:', e, jsonStr);
                    }
                }
            }
        }
    } catch (error) {
        nightFlowRunning = false;
        console.error('夜晚引导 SSE 异常:', error);
        alert('夜晚操作失败，请检查控制台');
    }
}

async function executeNightAction() {
    const params = { game_id: gameId };
    const spectating = isSpectator();
    const roleActions = getCurrentRoleActions();

    if (!spectating) {
        const roleParams = (roleActions.collectNightParams && roleActions.collectNightParams()) || {};
        if (roleParams.error) { alert(roleParams.error); return; }
        Object.assign(params, roleParams);
    }

    // 续播模式：跳过引导消息，必要时跳过已处理阶段
    if (nightFlowReady) {
        params.skip_intro = true;
        if (nightResumePhase) {
            params.resume_phase = nightResumePhase;
        }
    }

    // 禁用按钮防止重复提交
    const actionBtns = document.querySelectorAll('#action-content .action-btn');
    actionBtns.forEach(b => b.disabled = true);

    try {
        const res = await fetch('/api/game/night-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        if (!res.ok) {
            const err = await res.json();
            alert('夜晚操作失败: ' + (err.error || '未知错误'));
            actionBtns.forEach(b => b.disabled = false);
            return;
        }

        // 读取 SSE 流 — 系统消息随到随播，间隔 1 秒
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'system') {
                            enqueueMessage(event.content);
                        } else if (event.type === 'seer_result') {
                            // 只有预言家能看到查验结果
                            if (currentRole === '预言家') {
                                window.checkedRoles = window.checkedRoles || {};
                                window.checkedRoles[event.checked] = event.checked_role;
                                if (gameState) renderState(gameState);
                                showSeerResult(event.checked, event.checked_role);
                            }
                        } else if (event.type === 'result') {
                            enqueueMessage(event.content);
                        } else if (event.type === 'done') {
                            // 重置夜晚流程标记
                            nightFlowReady = false;
                            nightFlowRunning = false;
                            nightResumePhase = null;
                            // 等待队列清空后再刷新界面
                            onStreamComplete(function() {
                                if (roleActions.handleDoneEvent) {
                                    roleActions.handleDoneEvent(event);
                                }
                                if (roleActions.resetState) roleActions.resetState();
                                actionBtns.forEach(b => b.disabled = false);
                                refreshState().then(() => {
                                    if (event.game_over) {
                                        setTimeout(() => showGameOver(gameState), 500);
                                    }
                                });
                            });
                        } else if (event.type === 'error') {
                            alert(event.message);
                        }
                    } catch (e) {
                        console.error('解析 SSE 事件失败:', e, jsonStr);
                    }
                }
            }
        }
    } catch (error) {
        console.error('SSE 请求异常:', error);
        alert('夜晚操作失败，请检查控制台');
    }
}

// ==================== 白天引导（按顺序发言第一段） ====================
async function startDayIntro() {
    if (dayIntroRunning) return;
    dayIntroRunning = true;

    try {
        const res = await fetch('/api/game/day-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId })  // 不传 user_speak
        });

        if (!res.ok) {
            const err = await res.json();
            alert('发言阶段开始失败: ' + (err.error || '未知错误'));
            dayIntroRunning = false;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'system') {
                            enqueueMessage(event.content);
                        } else if (event.type === 'speech') {
                            appendSpeechBubble(event);
                        } else if (event.type === 'awaiting_human_speech') {
                            // 轮到人类玩家 → 保存位置信息，显示发言输入框
                            pendingHumanPosition = event.position || 0;
                            dayIntroRunning = false;
                            renderActionArea(gameState);
                            return;
                        } else if (event.type === 'done') {
                            // 人类不在发言顺序中（已死亡）→ 直接进入投票
                            pendingHumanPosition = 0;
                            dayIntroRunning = false;
                            refreshState();
                        } else if (event.type === 'error') {
                            dayIntroRunning = false;
                            alert(event.message);
                        }
                    } catch (e) {
                        console.error('解析 SSE 事件失败:', e, jsonStr);
                    }
                }
            }
        }
    } catch (error) {
        dayIntroRunning = false;
        console.error('白天引导 SSE 异常:', error);
    }
}

async function executeDayAction() {
    const spectating = isSpectator();
    const content = spectating ? '' : (document.getElementById('speak-content')?.value || '（跳过发言）');

    if (!gameId) { alert('游戏未初始化，请重新开始游戏'); return; }

    // 保存人类发言位置用于续播，然后清除（已提交发言）
    var humanPos = pendingHumanPosition;
    dayIntroRunning = true;
    pendingHumanPosition = 0;

    // 清空输入框并禁用按钮防止重复提交
    const speakEl = document.getElementById('speak-content');
    if (speakEl) speakEl.value = '';
    const sendBtn = document.querySelector('#action-content .action-btn');
    if (sendBtn && !spectating) sendBtn.disabled = true;

    try {
        const body = {
            game_id: gameId,
            user_speak: content || '',
            skip_intro: true,
            resume_from: humanPos,
        };
        const res = await fetch('/api/game/day-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const err = await res.json();
            alert('发言失败: ' + (err.error || '未知错误'));
            if (sendBtn) sendBtn.disabled = false;
            return;
        }

        // 读取 SSE 流 — 发言实时显示，系统消息随到随播
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'system' || event.type === 'result') {
                            enqueueEvent(event);
                        } else if (event.type === 'speech' || event.type === 'tie_speech') {
                            enqueueEvent(event);
                        } else if (event.type === 'done') {
                            pendingHumanPosition = 0;
                            dayIntroRunning = false;
                            onStreamComplete(function() {
                                refreshState();
                            });
                        } else if (event.type === 'error') {
                            dayIntroRunning = false;
                            alert(event.message);
                        }
                    } catch (e) {
                        console.error('解析 SSE 事件失败:', e, jsonStr);
                    }
                }
            }
        }
    } catch (error) {
        dayIntroRunning = false;
        console.error('SSE 请求异常:', error);
        alert('发言失败，请检查控制台');
    }
    if (sendBtn) sendBtn.disabled = false;
}

async function executeVoteAction(isAbstain = false, extra_speeches = null) {
    const userVote = isAbstain ? null : selectedVoteTarget;

    if (!isAbstain && userVote === null) {
        alert('请选择投票目标');
        return;
    }

    // 标记投票进行中，显示加载动画
    votingInProgress = true;
    voteProgressLog = [];
    selectedVoteTarget = null;
    renderActionArea(gameState);

    try {
        const body = { game_id: gameId, user_vote: userVote };
        if (extra_speeches && Array.isArray(extra_speeches) && extra_speeches.length > 0) {
            body.extra_speeches = extra_speeches;
        }

        const res = await fetch('/api/game/vote-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const err = await res.json();
            alert('投票失败: ' + (err.error || '未知错误'));
            votingInProgress = false;
            renderActionArea(gameState);
            return;
        }

        // 读取 SSE 流 — 投票进度实时显示，系统消息随到随播
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'vote_progress') {
                            // AI 投票进度 — 实时显示
                            voteProgressLog.push(event);
                            renderActionArea(gameState);
                        } else if (event.type === 'tie_break') {
                            // 平票 — 后端已发 system 消息，这里只更新状态
                            const candidates = event.candidates || [];
                            tieBreakState = { active: true, waitingForInput: false, round: event.round || 1, candidates };
                            voteProgressLog = [];
                            renderActionArea(gameState);
                        } else if (event.type === 'awaiting_tie_speech') {
                            // 人类在平票候选人中 → 后端已暂停，前端收流并展示重投UI
                            const candidates = event.candidates || [];
                            tieBreakState = { active: true, waitingForInput: true, round: event.round || 1, candidates };
                            votingInProgress = false;
                            enqueueEvent({ type: 'system', content: `✍️ 平票PK阶段，请输入你的发言并重新投票` });
                            voteProgressLog = [];
                            renderActionArea(gameState);
                            return;  // 后端已暂停，停止读流
                        } else if (event.type === 'tie_speech') {
                            // PK 发言 — 按顺序排队显示
                            enqueueEvent(event);
                        } else if (event.type === 'system' || event.type === 'result') {
                            // 系统消息 — 随到随播
                            enqueueEvent(event);
                        } else if (event.type === 'vote_summary') {
                            // 投票结果可视化面板
                            enqueueEvent(event);
                        } else if (event.type === 'done') {
                            // 等队列清空再处理投票结果
                            onStreamComplete(function() {
                                votingInProgress = false;
                                voteProgressLog = [];
                                tieBreakState = { active: false, round: 0, candidates: [] };

                                // 添加投票结果到历史显示
                                if (event.votes && Object.keys(event.votes).length > 0) {
                                    if (!gameState.history) gameState.history = [];
                                    for (const [target, count] of Object.entries(event.votes)) {
                                        gameState.history.push({
                                            type: 'vote',
                                            player_id: -1,
                                            content: `${target} 号获得 ${count} 票`,
                                            target: parseInt(target)
                                        });
                                    }
                                }
                                if (event.eliminated) {
                                    // 记录被投票出局的玩家，其身份公开可见
                                    votedOutPlayers[event.eliminated] = true;
                                    gameState.history.push({
                                        type: 'eliminate',
                                        player_id: -1,
                                        content: `${event.eliminated} 号被投票出局`,
                                        target: event.eliminated
                                    });
                                }

                                refreshState().then(() => {
                                    if (event.game_over && event.winner) {
                                        setTimeout(() => showGameOver(gameState), 500);
                                    } else if (gameState.phase === 'night' && !isSpectator()) {
                                        if (getCurrentRoleActions().autoTriggerWolfAfterVote) {
                                            executeWolfAction();
                                        }
                                    }
                                });
                            });
                        } else if (event.type === 'error') {
                            alert(event.message);
                            votingInProgress = false;
                            renderActionArea(gameState);
                        }
                    } catch (e) {
                        console.error('解析 SSE 事件失败:', e, jsonStr);
                    }
                }
            }
        }

        // 如果流结束但仍处于平票PK等待输入状态，确保交互区恢复可用
        if (tieBreakState.active) {
            votingInProgress = false;
            renderActionArea(gameState);
        }
    } catch (error) {
        console.error('投票 SSE 请求异常:', error);
        alert('投票失败，请检查控制台');
        votingInProgress = false;
        voteProgressLog = [];
        renderActionArea(gameState);
    }
}

// ==================== 游戏结束 ====================
function showGameOver(state) {
    document.getElementById('game-over-winner').textContent = `胜利者: ${state.winner}`;
    document.getElementById('game-over-role').textContent = `你的身份: ${currentRole}`;

    let rolesList = '<div style="margin-top: 20px; text-align: left;">';
    for (const [pid, name] of Object.entries(state.player_names)) {
        const role = state.player_roles[pid];
        rolesList += `<div style="padding: 5px 0;">${name} (${pid}号): ${role}</div>`;
    }
    rolesList += '</div>';
    document.getElementById('game-over-roles').innerHTML = rolesList;

    document.getElementById('game-over-overlay').style.display = 'flex';
}
