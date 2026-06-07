// ==================== 女巫角色模块 ====================
(function() {
    'use strict';

    // 模块内部状态
    var witchAction = 'none';     // none / save / poison
    var witchPoisonTarget = null;

    /**
     * 角色揭示时的额外信息 — 女巫无额外信息
     */
    function getRoleRevealExtra(gameState) {
        return '';
    }

    /**
     * 渲染夜晚行动区域 — 女巫救人/毒人/不操作 UI
     */
    function renderNightActions(gameState) {
        var alivePlayers = gameState.alive_players.filter(function(p) { return p !== 1; });
        var wolfTarget = gameState.werewolf_kill_target;

        if (wolfTarget === null || wolfTarget === undefined) {
            return '<div class="night-action-box">' +
                '<h4>🧙 女巫操作</h4>' +
                '<div style="padding: 20px; text-align: center;">' +
                '<div style="font-size: 24px; margin-bottom: 10px;">🔄</div>' +
                '<p style="color: #fbbf24;">等待狼人选择击杀目标...</p>' +
                '<button class="action-btn" onclick="executeWolfAction()" style="margin-top: 10px;">触发狼人行动</button>' +
                '</div></div>';
        }

        var wolfTargetName = gameState.player_names[wolfTarget] || ('玩家' + wolfTarget);
        var saveBtnClass = 'witch-btn' + (witchAction === 'save' ? ' active' : '');
        var poisonBtnClass = 'witch-btn' + (witchAction === 'poison' ? ' active' : '');
        var noneBtnClass = 'witch-btn' + (witchAction === 'none' ? ' active' : '');

        var html = '<div class="night-action-box">' +
            '<h4>🧙 女巫操作</h4>' +
            '<div style="margin-bottom: 15px; padding: 10px; background: rgba(239, 68, 68, 0.15); border-radius: 8px;">' +
            '<span style="color: #ef4444;">⚠️ 狼人选择击杀: </span>' +
            '<span style="font-weight: bold;">' + wolfTargetName + ' (' + wolfTarget + '号)</span></div>' +
            '<div style="margin-bottom: 10px; font-size: 12px; color: #9ca3af;">' +
            '你的药水: 解药' + (gameState.witch_has_save ? '✅' : '❌') + ' 毒药' + (gameState.witch_has_poison ? '✅' : '❌') +
            '</div>' +
            '<div class="witch-options">' +
            '<button class="' + saveBtnClass + '" onclick="setWitchAction(\'save\')"' +
            (gameState.witch_has_save ? '' : ' disabled') + '>' +
            (witchAction === 'save' ? '✓ 救人' : '救人') +
            (!gameState.witch_has_save ? ' (已用)' : '') + '</button>' +
            '<button class="' + poisonBtnClass + '" onclick="setWitchAction(\'poison\')"' +
            (gameState.witch_has_poison ? '' : ' disabled') + '>' +
            (witchAction === 'poison' ? '✓ 毒人' : '毒人') +
            (!gameState.witch_has_poison ? ' (已用)' : '') + '</button>' +
            '<button class="' + noneBtnClass + '" onclick="setWitchAction(\'none\')"' +
            ' style="background: rgba(74, 222, 128, 0.15); border-color: rgba(74, 222, 128, 0.5);">' +
            (witchAction === 'none' ? '✓ 不操作' : '不操作') + '</button>' +
            '</div>';

        if (witchPoisonTarget !== null) {
            html += '<select class="action-input" id="witch-poison" onchange="updateWitchPoison(this)">' +
                '<option value="">选择毒杀目标</option>';
            alivePlayers.forEach(function(p) {
                var selected = witchPoisonTarget === p ? ' selected' : '';
                html += '<option value="' + p + '"' + selected + '>' + gameState.player_names[p] + ' (' + p + '号)</option>';
            });
            html += '</select>';
        }

        html += '<button class="action-btn" onclick="executeNightAction()" style="margin-top: 15px;">执行夜晚操作</button>' +
            '</div>';

        return html;
    }

    /**
     * 设置女巫行动类型
     */
    function setAction(action) {
        witchAction = action;
        if (action !== 'poison') witchPoisonTarget = null;
    }

    /**
     * 设置毒杀目标
     */
    function setPoisonTarget(selectElement) {
        witchPoisonTarget = selectElement.value ? parseInt(selectElement.value) : null;
    }

    /**
     * 从 DOM 收集夜晚操作参数
     */
    function collectNightParams() {
        var params = {};
        params.user_witch_save = witchAction === 'save';
        if (witchAction === 'poison' && witchPoisonTarget !== null && witchPoisonTarget > 0) {
            params.user_witch_poison = witchPoisonTarget;
        }
        return params;
    }

    /**
     * 重置模块内部状态
     */
    function resetState() {
        witchAction = 'none';
        witchPoisonTarget = null;
    }

    // 挂载到全局
    window.RoleActions = window.RoleActions || {};
    window.RoleActions['女巫'] = {
        name: '女巫',
        getRoleRevealExtra: getRoleRevealExtra,
        renderNightActions: renderNightActions,
        collectNightParams: collectNightParams,
        resetState: resetState,
        setAction: setAction,
        setPoisonTarget: setPoisonTarget,
        autoTriggerWolfAfterVote: false,
    };

    // 女巫桥接函数（供 onclick 使用）
    window.setWitchAction = function(action) {
        setAction(action);
        if (typeof refreshState === 'function') refreshState();
    };

    window.updateWitchPoison = function(selectElement) {
        setPoisonTarget(selectElement);
    };
})();
