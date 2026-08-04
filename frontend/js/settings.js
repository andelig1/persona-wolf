// ==================== 设置抽屉 + 胜率弹窗 ====================
(function () {
    'use strict';

    var overlay = null;
    var drawer = null;
    var statsOverlay = null;

    // —— 构建设置抽屉 DOM ——
    function buildDrawer() {
        overlay = document.createElement('div');
        overlay.className = 'settings-overlay';
        overlay.id = 'settings-overlay';

        drawer = document.createElement('div');
        drawer.className = 'settings-drawer';
        drawer.id = 'settings-drawer';

        drawer.innerHTML =
            '<div class="settings-drawer-header">' +
                '<span class="settings-drawer-title">⚙️ 设置</span>' +
                '<button class="settings-close" onclick="Settings.close()" title="关闭">✕</button>' +
            '</div>' +
            '<div class="settings-section-title">待扩展设置项</div>' +
            '<div class="settings-item"><span>🎵 游戏音效</span><span class="settings-item-placeholder">即将上线</span></div>' +
            '<div class="settings-item"><span>🌙 夜晚特效</span><span class="settings-item-placeholder">即将上线</span></div>' +
            '<div class="settings-item"><span>💬 发言速度</span><span class="settings-item-placeholder">即将上线</span></div>' +
            '<div class="settings-section-title">数据</div>' +
            '<button class="settings-stats-btn" onclick="Settings.showStats()">📊 查看胜率</button>' +
            '<div class="settings-footer">' +
                '<button class="home-btn" onclick="Settings.backHome()">' +
                    '<span class="home-tip">返回首页</span>' +
                    '<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22" aria-hidden="true">' +
                        '<path d="M10,20v-6h4v6h5v-8h3L12,3L2,12h3v8H10z"/>' +
                    '</svg>' +
                '</button>' +
            '</div>';

        overlay.appendChild(drawer);
        document.body.appendChild(overlay);

        // 点击遮罩（非抽屉区域）关闭
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) Settings.close();
        });
        // Esc 关闭
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                if (statsOverlay && statsOverlay.parentNode) closeStats();
                else if (drawer.classList.contains('open')) Settings.close();
            }
        });
    }

    // —— 胜率弹窗 ——
    function showStats() {
        var existing = document.getElementById('stats-overlay');
        if (existing) existing.remove();

        statsOverlay = document.createElement('div');
        statsOverlay.className = 'stats-overlay';
        statsOverlay.id = 'stats-overlay';
        statsOverlay.innerHTML =
            '<div class="stats-modal">' +
                '<div class="stats-modal-title">📊 胜率统计</div>' +
                '<div class="stats-modal-subtitle">数据来源于 Web 对局与 CLI 批量观战</div>' +
                '<div id="stats-loading"><div class="loading-spinner"></div></div>' +
            '</div>';
        document.body.appendChild(statsOverlay);

        statsOverlay.addEventListener('click', function (e) {
            if (e.target === statsOverlay) closeStats();
        });

        fetch('/api/stats')
            .then(function (r) { return r.json(); })
            .then(renderStats)
            .catch(function () {
                document.getElementById('stats-loading').innerHTML =
                    '<div class="stats-empty">加载胜率数据失败</div>';
            });
    }

    function renderStats(data) {
        var modal = statsOverlay.querySelector('.stats-modal');
        var html = '';

        var total = data.total_games || 0;
        var overall = data.overall || { games: 0, wins: 0, win_rate: 0 };

        html += '<div class="stats-modal-subtitle">' +
                '共 ' + total + ' 局 · 玩家槽位 ' + overall.games +
                ' · 整体胜率 ' + fmtRate(overall.win_rate) +
                '</div>';

        // —— 人格胜率 ——
        var persos = data.personalities || [];
        if (persos.length) {
            html += '<div class="stats-section"><div class="stats-section-title">人格胜率</div>';
            persos.forEach(function (p) {
                html += statsRow(
                    p.name,
                    p.win_rate,
                    '<span class="stats-whg">好人 ' + p.good.wins + '/' + p.good.games +
                        ' · 狼人 ' + p.bad.wins + '/' + p.bad.games + '</span>'
                );
            });
            html += '</div>';
        }

        // —— 真人玩家胜率 ——
        var player = data.player;
        if (player) {
            html += '<div class="stats-section"><div class="stats-section-title">我的胜率</div>' +
                statsRow(
                    player.name || '你',
                    player.win_rate,
                    '<span class="stats-whg">好人 ' + player.good.wins + '/' + player.good.games +
                        ' · 狼人 ' + player.bad.wins + '/' + player.bad.games + '</span>'
                ) + '</div>';
        }

        if (!persos.length && !player) {
            html += '<div class="stats-empty">暂无对局记录，先跑一局或使用批量观战模式吧</div>';
        }

        html += '<button class="stats-close" onclick="Settings.closeStats()">关闭</button>';
        modal.innerHTML = html;
    }

    function statsRow(name, winRate, extraHtml) {
        return '<div class="stats-row">' +
            '<span class="stats-name">' + esc(name) + '</span>' +
            '<span class="stats-bar-track"><span class="stats-bar-fill" style="width:' +
                clamp(winRate) + '%"></span></span>' +
            '<span class="stats-winrate">' + fmtRate(winRate) + '</span>' +
            extraHtml +
        '</div>';
    }

    function closeStats() {
        if (statsOverlay && statsOverlay.parentNode) statsOverlay.parentNode.removeChild(statsOverlay);
        statsOverlay = null;
    }

    function fmtRate(v) { return (Number(v) || 0).toFixed(1) + '%'; }
    function clamp(v) { return Math.max(0, Math.min(100, Number(v) || 0)); }
    function esc(s) { return String(s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    }); }

    // —— 导出全局接口（供 onclick 使用）——
    window.Settings = {
        open: function () {
            if (!drawer) buildDrawer();
            overlay.classList.add('open');
            drawer.classList.add('open');
        },
        close: function () {
            if (!drawer) return;
            overlay.classList.remove('open');
            drawer.classList.remove('open');
        },
        showStats: showStats,
        closeStats: closeStats,
        backHome: function () {
            // 结束当前对局，返回开始界面
            this.close();
            if (window.returnToHome) window.returnToHome();
        },
    };
})();
