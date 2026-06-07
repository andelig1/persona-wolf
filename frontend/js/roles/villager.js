// ==================== 村民角色模块 ====================
(function() {
    'use strict';

    /**
     * 角色揭示时的额外信息 — 村民无额外信息
     */
    function getRoleRevealExtra(gameState) {
        return '';
    }

    /**
     * 渲染夜晚行动区域 — 村民无特殊行动
     */
    function renderNightActions(gameState) {
        return '<div class="night-action-box" style="text-align: center;">' +
            '<div style="font-size: 36px; margin-bottom: 15px;">💤</div>' +
            '<p style="color: #9ca3af;">平民夜晚没有特殊行动</p>' +
            '<p style="color: #6b7280; font-size: 14px;">等待其他玩家行动...</p>' +
            '<button class="action-btn" onclick="executeNightAction()" style="margin-top: 20px;">跳过夜晚</button>' +
            '</div>';
    }

    /**
     * 从 DOM 收集夜晚操作参数 — 村民无需收集
     */
    function collectNightParams() {
        return {};
    }

    /**
     * 重置状态
     */
    function resetState() {
        // 村民无额外状态需要重置
    }

    // 挂载到全局
    window.RoleActions = window.RoleActions || {};
    window.RoleActions['村民'] = {
        name: '村民',
        getRoleRevealExtra: getRoleRevealExtra,
        renderNightActions: renderNightActions,
        collectNightParams: collectNightParams,
        resetState: resetState,
        autoTriggerWolfAfterVote: true,
    };
})();
