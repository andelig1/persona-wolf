// ==================== 预言家角色模块 ====================
(function() {
    'use strict';

    /**
     * 角色揭示时的额外信息 — 预言家无额外信息
     */
    function getRoleRevealExtra(gameState) {
        return '';
    }

    /**
     * 渲染夜晚行动区域 — 查验目标选择器
     */
    function renderNightActions(gameState) {
        var alivePlayers = gameState.alive_players.filter(function(p) { return p !== 1; });

        var html = '<div class="night-action-box">' +
            '<h4>🔮 预言家查验</h4>' +
            '<select class="action-input" id="seer-target">' +
            '<option value="">选择查验目标</option>';
        alivePlayers.forEach(function(p) {
            html += '<option value="' + p + '">' + gameState.player_names[p] + ' (' + p + '号)</option>';
        });
        html += '</select></div>' +
            '<button class="action-btn" onclick="executeNightAction()">执行夜晚操作</button>';

        return html;
    }

    /**
     * 从 DOM 收集夜晚操作参数
     */
    function collectNightParams() {
        var targetEl = document.getElementById('seer-target');
        var target = targetEl ? targetEl.value : null;
        if (!target) return { error: '请选择查验目标' };
        return { user_seer_target: parseInt(target) };
    }

    /**
     * 处理夜晚 SSE 流 done 事件 — 显示查验结果
     */
    function handleDoneEvent(event) {
        // 查验结果已在 seer_result 事件中即时显示，这里只做兜底存储
        if (event.checked_role && event.checked) {
            window.checkedRoles = window.checkedRoles || {};
            window.checkedRoles[event.checked] = event.checked_role;
        }
    }

    /**
     * 重置状态
     */
    function resetState() {
        // 预言家无额外状态需要重置
    }

    // 挂载到全局
    window.RoleActions = window.RoleActions || {};
    window.RoleActions['预言家'] = {
        name: '预言家',
        getRoleRevealExtra: getRoleRevealExtra,
        renderNightActions: renderNightActions,
        collectNightParams: collectNightParams,
        resetState: resetState,
        handleDoneEvent: handleDoneEvent,
        autoTriggerWolfAfterVote: true,
    };
})();
