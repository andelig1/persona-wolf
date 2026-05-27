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
let witchAction = 'none';   // none / save / poison
let witchPoisonTarget = null;
let gameState = null;
let chosenRole = null;
let numPlayers = 6;
let roleConfig = null;
let autoPlayTimer = null;   // 观战模式自动推进定时器
let votingInProgress = false;
let voteProgressLog = [];

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

    showRoleReveal(currentRole || '村民');
    renderState(data);
    renderSpeeches(data.history);
}

function showRoleReveal(role) {
    const overlay = document.createElement('div');
    overlay.id = 'role-reveal-overlay';
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0, 0, 0, 0.95);
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        z-index: 1000; animation: fadeIn 0.5s ease-in;
    `;

    let wolfTeammatesHtml = '';
    if (role === '狼人' && gameState) {
        const wolves = Object.entries(gameState.player_roles)
            .filter(([pid, r]) => r === '狼人' && parseInt(pid) !== 1)
            .map(([pid]) => {
                const name = gameState.player_names[parseInt(pid)] || `玩家${pid}`;
                return `${name} (${pid}号)`;
            });

        if (wolves.length > 0) {
            wolfTeammatesHtml = `
                <div style="margin-top: 20px; padding: 15px; background: rgba(239, 68, 68, 0.2); border-radius: 10px; border: 1px solid rgba(239, 68, 68, 0.3);">
                    <div style="font-size: 18px; color: #ef4444; margin-bottom: 10px; font-weight: bold;">
                        \u{1F43A} 你的狼人队友：
                    </div>
                    <div style="color: #fca5a5; font-size: 16px;">
                        ${wolves.join('、')}
                    </div>
                    <div style="color: #fca5a5; font-size: 14px; margin-top: 8px;">
                        夜晚你们一起选择击杀目标，白天不要投票给队友！
                    </div>
                </div>
            `;
        }
    }

    overlay.innerHTML = `
        <div style="text-align: center; animation: zoomIn 0.5s ease-out;">
            <div style="font-size: 80px; margin-bottom: 20px;">${getRoleEmoji(role)}</div>
            <div style="font-size: 36px; color: #c084fc; margin-bottom: 10px; font-weight: bold;">你的身份是</div>
            <div style="font-size: 48px; color: #fbbf24; margin-bottom: 20px; font-weight: bold; text-shadow: 0 0 20px rgba(251, 191, 36, 0.5);">${role}</div>
            <div style="font-size: 18px; color: #9ca3af; margin-bottom: 20px; max-width: 400px;">${ROLE_DESC[role] || ''}</div>
            ${wolfTeammatesHtml}
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
        setTimeout(() => overlay.remove(), 300);
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
    renderSpeeches(data.history);

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
    let html = '';
    const sortedPids = Object.keys(state.player_names).map(Number).sort((a, b) => a - b);

    for (const pid of sortedPids) {
        const name = state.player_names[pid];
        const isAlive = state.alive_players.includes(pid);
        const role = state.player_roles[pid];
        const isHuman = pid === 1;
        const showRole = isHuman || spectating;

        html += `
            <div class="player-item ${isAlive ? 'alive' : 'dead'} ${isHuman ? 'human' : ''}">
                <div class="player-avatar">${getRoleEmoji(showRole ? role : '村民')}</div>
                <div class="player-info">
                    <div class="player-name">${name} (${pid}号)${isHuman ? ' <span style="color:#3b82f6">(你)</span>' : ''}</div>
                    <div class="player-role">${showRole ? role : '???'}</div>
                </div>
                <div class="player-status ${isAlive ? 'status-alive' : 'status-dead'}">
                    ${isAlive ? '存活' : '死亡'}
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
        actionTitle.textContent = '\u{1F319} 夜晚行动';
        actionContent.innerHTML = renderNightActions(state);
    } else if (state.phase === 'day') {
        actionTitle.textContent = '\u{1F4AC} 发言';
        actionContent.innerHTML = renderDayActions(state);
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

// ==================== 夜晚 ====================
function renderNightActions(state) {
    const alivePlayers = state.alive_players.filter(p => p !== 1);
    const wolfTarget = state.werewolf_kill_target;

    if (currentRole === '村民') {
        return `
            <div class="night-action-box" style="text-align: center;">
                <div style="font-size: 36px; margin-bottom: 15px;">\u{1F4A4}</div>
                <p style="color: #9ca3af;">平民夜晚没有特殊行动</p>
                <p style="color: #6b7280; font-size: 14px;">等待其他玩家行动...</p>
                <button class="action-btn" onclick="executeNightAction()" style="margin-top: 20px;">跳过夜晚</button>
            </div>
        `;
    }

    let html = '';

    if (currentRole === '狼人') {
        html += `
            <div class="night-action-box">
                <h4>\u{1F43A} 狼人击杀</h4>
                <select class="action-input" id="wolf-target">
                    <option value="">选择击杀目标</option>
                    ${alivePlayers.map(p => `<option value="${p}">${state.player_names[p]} (${p}号)</option>`).join('')}
                </select>
            </div>
        `;
    }

    if (currentRole === '预言家') {
        html += `
            <div class="night-action-box">
                <h4>\u{1F52E} 预言家查验</h4>
                <select class="action-input" id="seer-target">
                    <option value="">选择查验目标</option>
                    ${alivePlayers.map(p => `<option value="${p}">${state.player_names[p]} (${p}号)</option>`).join('')}
                </select>
            </div>
        `;
    }

    if (currentRole === '女巫') {
        if (wolfTarget === null || wolfTarget === undefined) {
            html += `
                <div class="night-action-box">
                    <h4>\u{1F9D9} 女巫操作</h4>
                    <div style="padding: 20px; text-align: center;">
                        <div style="font-size: 24px; margin-bottom: 10px;">\u{1F504}</div>
                        <p style="color: #fbbf24;">等待狼人选择击杀目标...</p>
                        <button class="action-btn" onclick="executeWolfAction()" style="margin-top: 10px;">触发狼人行动</button>
                    </div>
                </div>
            `;
        } else {
            const wolfTargetName = state.player_names[wolfTarget] || `玩家${wolfTarget}`;
            html += `
                <div class="night-action-box">
                    <h4>\u{1F9D9} 女巫操作</h4>
                    <div style="margin-bottom: 15px; padding: 10px; background: rgba(239, 68, 68, 0.15); border-radius: 8px;">
                        <span style="color: #ef4444;">⚠️ 狼人选择击杀: </span>
                        <span style="font-weight: bold;">${wolfTargetName} (${wolfTarget}号)</span>
                    </div>
                    <div style="margin-bottom: 10px; font-size: 12px; color: #9ca3af;">
                        你的药水: 解药${state.witch_has_save ? '✅' : '❌'} 毒药${state.witch_has_poison ? '✅' : '❌'}
                    </div>
                    <div class="witch-options">
                        <button class="witch-btn ${witchAction === 'save' ? 'active' : ''}" onclick="setWitchAction('save')" ${!state.witch_has_save ? 'disabled' : ''}>
                            ${witchAction === 'save' ? '✓ 救人' : '救人'}
                            ${!state.witch_has_save ? ' (已用)' : ''}
                        </button>
                        <button class="witch-btn ${witchAction === 'poison' ? 'active' : ''}" onclick="setWitchAction('poison')" ${!state.witch_has_poison ? 'disabled' : ''}>
                            ${witchAction === 'poison' ? '✓ 毒人' : '毒人'}
                            ${!state.witch_has_poison ? ' (已用)' : ''}
                        </button>
                        <button class="witch-btn ${witchAction === 'none' ? 'active' : ''}" onclick="setWitchAction('none')" style="background: rgba(74, 222, 128, 0.15); border-color: rgba(74, 222, 128, 0.5);">
                            ${witchAction === 'none' ? '✓ 不操作' : '不操作'}
                        </button>
                    </div>
                    ${witchPoisonTarget !== null ? `
                        <select class="action-input" id="witch-poison" onchange="updateWitchPoison(this)">
                            <option value="">选择毒杀目标</option>
                            ${alivePlayers.map(p => `<option value="${p}" ${witchPoisonTarget === p ? 'selected' : ''}>${state.player_names[p]} (${p}号)</option>`).join('')}
                        </select>
                    ` : ''}
                    <button class="action-btn" onclick="executeNightAction()" style="margin-top: 15px;">执行夜晚操作</button>
                </div>
            `;
        }
        return html;
    }

    html += '<button class="action-btn" onclick="executeNightAction()">执行夜晚操作</button>';
    return html;
}

function setWitchAction(action) {
    witchAction = action;
    if (action !== 'poison') witchPoisonTarget = null;
    refreshState();
}

function updateWitchPoison(selectElement) {
    witchPoisonTarget = selectElement.value ? parseInt(selectElement.value) : null;
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

    if (votingInProgress) {
        // 投票进行中 — 显示进度
        let progressHtml = '';
        for (const entry of voteProgressLog) {
            const icon = entry.is_abstain ? '○' : '✓';
            const action = entry.is_abstain ? '弃权' : `投给了 ${entry.target} 号`;
            progressHtml += `
                <div style="padding: 6px 0; color: #9ca3af; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    ${icon} ${entry.name}（${entry.player_id}号）${action}
                </div>`;
        }

        return `
            <div style="text-align: center; padding: 30px 0;">
                <div class="loading-spinner"></div>
                <div style="color: #c084fc; margin: 15px 0; font-size: 16px;">🤖 AI 玩家正在投票...</div>
                <div style="color: #6b7280; font-size: 13px;">并行处理中，请稍候</div>
                ${progressHtml ? `
                    <div style="margin-top: 20px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 10px; text-align: left; max-height: 200px; overflow-y: auto;">
                        ${progressHtml}
                    </div>` : ''}
            </div>
        `;
    }

    return `
        <div class="vote-panel">
            ${alivePlayers.map(p => `
                <button class="vote-target-btn ${selectedVoteTarget === p ? 'selected' : ''}"
                    onclick="selectVoteTarget(${p})">
                    <div>${state.player_names[p]}</div>
                    <div style="font-size: 12px; opacity: 0.7;">${p}号</div>
                </button>
            `).join('')}
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

async function executeNightAction() {
    const params = { game_id: gameId };
    const spectating = isSpectator();

    if (!spectating) {
        if (currentRole === '狼人') {
            const target = document.getElementById('wolf-target')?.value;
            if (!target) { alert('请选择击杀目标'); return; }
            params.user_werewolf_target = parseInt(target);
        }

        if (currentRole === '预言家') {
            const target = document.getElementById('seer-target')?.value;
            if (!target) { alert('请选择查验目标'); return; }
            params.user_seer_target = parseInt(target);
        }

        if (currentRole === '女巫') {
            params.user_witch_save = witchAction === 'save';
            if (witchAction === 'poison' && witchPoisonTarget !== null && witchPoisonTarget > 0) {
                params.user_witch_poison = witchPoisonTarget;
            }
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

        // 读取 SSE 流
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
                            appendSystemMessage(event.content);
                        } else if (event.type === 'result') {
                            appendSystemMessage(event.content);
                        } else if (event.type === 'done') {
                            // 预言家查验结果
                            if (currentRole === '预言家' && event.checked_role) {
                                alert(`预言家查验结果：\n${event.checked}号玩家的身份是：${event.checked_role}`);
                            }
                            // 刷新状态并更新界面
                            refreshState().then(() => {
                                if (event.game_over) {
                                    setTimeout(() => showGameOver(gameState), 500);
                                }
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

    witchAction = 'none';
    witchPoisonTarget = null;
    actionBtns.forEach(b => b.disabled = false);
}

async function executeDayAction() {
    const spectating = isSpectator();
    const content = spectating ? '' : (document.getElementById('speak-content')?.value || '（跳过发言）');

    if (!gameId) { alert('游戏未初始化，请重新开始游戏'); return; }

    // 清空输入框并禁用按钮防止重复提交
    const speakEl = document.getElementById('speak-content');
    if (speakEl) speakEl.value = '';
    const sendBtn = document.querySelector('#action-content .action-btn');
    if (sendBtn && !spectating) sendBtn.disabled = true;

    try {
        const res = await fetch('/api/game/day-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId, user_speak: content })
        });

        if (!res.ok) {
            const err = await res.json();
            alert('发言失败: ' + (err.error || '未知错误'));
            if (sendBtn) sendBtn.disabled = false;
            return;
        }

        // 读取 SSE 流
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';  // 保留未完整行

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.substring(6);
                    try {
                        const event = JSON.parse(jsonStr);

                        if (event.type === 'system') {
                            // 法官系统消息（天亮、死亡公告、投票环节）
                            appendSystemMessage(event.content);
                        } else if (event.type === 'speech') {
                            // 实时追加发言气泡
                            appendSpeechBubble(event);
                        } else if (event.type === 'done') {
                            // 发言完成，刷新状态进入投票
                            refreshState().then(() => {
                                renderActionArea(gameState);
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
        alert('发言失败，请检查控制台');
    }
    if (sendBtn) sendBtn.disabled = false;
}

async function executeVoteAction(isAbstain = false) {
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
        const res = await fetch('/api/game/vote-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId, user_vote: userVote })
        });

        if (!res.ok) {
            const err = await res.json();
            alert('投票失败: ' + (err.error || '未知错误'));
            votingInProgress = false;
            renderActionArea(gameState);
            return;
        }

        // 读取 SSE 流
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
                            // AI 投票进度
                            voteProgressLog.push(event);
                            renderActionArea(gameState);
                        } else if (event.type === 'tie_break') {
                            // 平票 PK — 实时显示系统消息
                            const candidates = (event.candidates || []).map(c => c + '号').join('、');
                            appendSystemMessage(`⚖️ 平票！${candidates}进入第${event.round}轮PK发言`);
                            // 清空投票进度，准备记录重投票
                            voteProgressLog = [];
                            renderActionArea(gameState);
                        } else if (event.type === 'tie_speech') {
                            // PK 发言 — 实时追加气泡
                            appendSpeechBubble(event);
                        } else if (event.type === 'system') {
                            // 系统消息（如重新投票提示）
                            appendSystemMessage(event.content);
                        } else if (event.type === 'done') {
                            // 投票完成
                            votingInProgress = false;
                            voteProgressLog = [];

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
                                gameState.history.push({
                                    type: 'eliminate',
                                    player_id: -1,
                                    content: `${event.eliminated} 号被投票出局`,
                                    target: event.eliminated
                                });
                            }

                            renderActionArea(gameState);
                            refreshState().then(() => {
                                if (event.game_over && event.winner) {
                                    setTimeout(() => showGameOver(gameState), 500);
                                } else if (gameState.phase === 'night' && !isSpectator()) {
                                    renderActionArea(gameState);
                                    if (currentRole !== '狼人' && currentRole !== '女巫') {
                                        executeWolfAction().then(() => renderActionArea(gameState));
                                    }
                                }
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
