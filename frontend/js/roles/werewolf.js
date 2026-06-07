// ==================== 狼人角色模块 ====================
(function() {
    'use strict';

    /**
     * 角色揭示时的额外信息 — 显示狼人队友
     */
    function getRoleRevealExtra(gameState) {
        const wolves = Object.entries(gameState.player_roles)
            .filter(function(entry) { return entry[1] === '狼人' && parseInt(entry[0]) !== 1; })
            .map(function(entry) {
                var pid = entry[0];
                var name = gameState.player_names[parseInt(pid)] || ('玩家' + pid);
                return name + ' (' + pid + '号)';
            });

        if (wolves.length === 0) return '';

        return '<div style="margin-top: 20px; padding: 15px; background: rgba(239, 68, 68, 0.2); border-radius: 10px; border: 1px solid rgba(239, 68, 68, 0.3);">' +
            '<div style="font-size: 18px; color: #ef4444; margin-bottom: 10px; font-weight: bold;">🐺 你的狼人队友：</div>' +
            '<div style="color: #fca5a5; font-size: 16px;">' + wolves.join('、') + '</div>' +
            '<div style="color: #fca5a5; font-size: 14px; margin-top: 8px;">夜晚你们一起选择击杀目标，白天不要投票给队友！</div>' +
            '</div>';
    }

    /**
     * 渲染夜晚行动区域 — 击杀目标选择器
     */
    function renderNightActions(gameState) {
        // 过滤：排除自己(1号)和所有狼人队友，严禁击杀队友
        var alivePlayers = gameState.alive_players.filter(function(p) {
            return p !== 1 && gameState.player_roles[p] !== '狼人';
        });

        var hint = '';
        if (alivePlayers.length === 0) {
            hint = '<p style="color:#fbbf24;font-size:13px;margin-top:8px;">⚠️ 没有可选的非狼人目标，今晚无法击杀</p>';
        }

        var html = '<div class="night-action-box">' +
            '<h4>🐺 狼人击杀</h4>' +
            '<p style="color:#f87171;font-size:12px;margin-bottom:10px;">🚫 禁止击杀狼人队友</p>' +
            '<select class="action-input" id="wolf-target">' +
            '<option value="">选择击杀目标</option>';
        alivePlayers.forEach(function(p) {
            html += '<option value="' + p + '">' + gameState.player_names[p] + ' (' + p + '号)</option>';
        });
        html += '</select>' + hint + '</div>' +
            '<button class="action-btn" onclick="executeNightAction()">执行夜晚操作</button>';

        return html;
    }

    /**
     * 从 DOM 收集夜晚操作参数
     */
    function collectNightParams() {
        var targetEl = document.getElementById('wolf-target');
        var target = targetEl ? targetEl.value : null;
        if (!target) return { error: '请选择击杀目标' };
        return { user_werewolf_target: parseInt(target) };
    }

    /**
     * 重置状态
     */
    function resetState() {
        // 狼人无额外状态需要重置
    }

    /**
     * 判断玩家列表中某角色的身份是否应对人类玩家可见
     * 狼人可以看到队友的真实身份，防止忘记队友是几号
     */
    function shouldShowPlayerRole(pid, role, gameState) {
        return role === '狼人';
    }

    /**
     * 返回当前角色不能投票/击杀的玩家 ID 列表
     * 狼人：禁止投队友
     */
    function getForbiddenTargets(gameState) {
        var teammates = [];
        Object.keys(gameState.player_roles).forEach(function(pid) {
            if (parseInt(pid) !== 1 && gameState.player_roles[pid] === '狼人') {
                teammates.push(parseInt(pid));
            }
        });
        return teammates;
    }

    // 挂载到全局
    window.RoleActions = window.RoleActions || {};
    window.RoleActions['狼人'] = {
        name: '狼人',
        getRoleRevealExtra: getRoleRevealExtra,
        renderNightActions: renderNightActions,
        collectNightParams: collectNightParams,
        resetState: resetState,
        shouldShowPlayerRole: shouldShowPlayerRole,
        getForbiddenTargets: getForbiddenTargets,
        autoTriggerWolfAfterVote: false,
    };
})();
