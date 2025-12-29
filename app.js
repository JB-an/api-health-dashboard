/**
 * API 健康度檢測儀表板 - 互動邏輯
 */

// DOM 元素
const elements = {
    loading: document.getElementById('loading'),
    error: document.getElementById('error'),
    content: document.getElementById('content'),
    environment: document.getElementById('environment'),
    scoreRing: document.getElementById('score-ring'),
    scorePercentage: document.getElementById('score-percentage'),
    statTotal: document.getElementById('stat-total'),
    statSuccess: document.getElementById('stat-success'),
    statFailure: document.getElementById('stat-failure'),
    statAvgTime: document.getElementById('stat-avgtime'),
    alertsSection: document.getElementById('alerts-section'),
    resultsBody: document.getElementById('results-body'),
    lastUpdate: document.getElementById('last-update'),
    filterBtns: document.querySelectorAll('.filter-btn')
};

// 全域狀態
let testData = null;
let currentFilter = 'all';

/**
 * 初始化應用程式
 */
async function init() {
    try {
        testData = await loadTestResults();
        renderDashboard(testData);
        setupEventListeners();
        showContent();
    } catch (error) {
        console.error('載入失敗:', error);
        showError();
    }
}

/**
 * 載入測試結果
 */
async function loadTestResults() {
    const response = await fetch('test-result.json');
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
}

/**
 * 顯示主內容
 */
function showContent() {
    elements.loading.style.display = 'none';
    elements.error.style.display = 'none';
    elements.content.style.display = 'block';
}

/**
 * 顯示錯誤狀態
 */
function showError() {
    elements.loading.style.display = 'none';
    elements.error.style.display = 'flex';
    elements.content.style.display = 'none';
}

/**
 * 渲染儀表板
 */
function renderDashboard(data) {
    renderEnvironment(data.environment);
    renderHealthScore(data.summary.healthScore);
    renderStats(data.summary);
    renderAlerts(data.criticalFailures, data.warnings);
    renderResults(data.detailedResults);
    renderLastUpdate(data.testDate);
}

/**
 * 渲染環境資訊
 */
function renderEnvironment(environment) {
    elements.environment.textContent = `🌐 ${environment}`;
}

/**
 * 渲染健康度圓環
 */
function renderHealthScore(healthScore) {
    const score = parseFloat(healthScore);
    const circumference = 2 * Math.PI * 90; // r = 90
    const offset = circumference - (score / 100) * circumference;

    // 設定進度
    setTimeout(() => {
        elements.scoreRing.style.strokeDashoffset = offset;
    }, 100);

    // 根據分數設定顏色
    elements.scoreRing.classList.remove('warning', 'danger');
    if (score < 70) {
        elements.scoreRing.classList.add('danger');
    } else if (score < 90) {
        elements.scoreRing.classList.add('warning');
    }

    // 動態計數器
    animateCounter(elements.scorePercentage, 0, score, 1500, '%');
}

/**
 * 數字動畫計數器
 */
function animateCounter(element, start, end, duration, suffix = '') {
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3); // easeOutCubic
        const current = start + (end - start) * easeProgress;

        element.textContent = current.toFixed(1) + suffix;

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

/**
 * 渲染統計數據
 */
function renderStats(summary) {
    elements.statTotal.textContent = summary.totalApis;
    elements.statSuccess.textContent = summary.successCount;
    elements.statFailure.textContent = summary.failureCount;
    elements.statAvgTime.textContent = `${summary.avgResponseTimeMs.toFixed(0)}ms`;
}

/**
 * 渲染警告與錯誤
 */
function renderAlerts(criticalFailures, warnings) {
    let html = '';

    // 嚴重錯誤
    criticalFailures.forEach(failure => {
        html += `
      <div class="alert alert--danger">
        <span class="alert__icon">🚨</span>
        <div class="alert__content">
          <div class="alert__title">嚴重錯誤</div>
          <div class="alert__message">${escapeHtml(failure)}</div>
        </div>
      </div>
    `;
    });

    // 警告
    warnings.forEach(warning => {
        html += `
      <div class="alert alert--warning">
        <span class="alert__icon">⚠️</span>
        <div class="alert__content">
          <div class="alert__title">警告</div>
          <div class="alert__message">${escapeHtml(warning)}</div>
        </div>
      </div>
    `;
    });

    elements.alertsSection.innerHTML = html;
}

/**
 * 渲染測試結果列表
 */
function renderResults(results) {
    const filteredResults = filterResults(results, currentFilter);

    const html = filteredResults.map(result => {
        const statusClass = result.isSuccess ? 'success' : 'failure';
        const statusText = result.isSuccess ? '成功' : '失敗';
        const methodClass = result.method.toLowerCase();
        const timeClass = getTimeClass(result.responseTimeMs);
        const endpoint = result.endpoint.replace(/^(GET|POST|PUT|DELETE)\s+/, '');

        return `
      <tr>
        <td>
          <span class="status-badge status-badge--${statusClass}">
            <span class="status-badge__dot"></span>
            ${statusText}
          </span>
        </td>
        <td>
          <span class="method-badge method-badge--${methodClass}">${result.method}</span>
        </td>
        <td class="endpoint">${escapeHtml(endpoint)}</td>
        <td>${result.testStrategy || 'full_call'}</td>
        <td>
          <span class="response-time response-time--${timeClass}">
            ${result.responseTimeMs.toFixed(0)}ms
          </span>
        </td>
      </tr>
    `;
    }).join('');

    elements.resultsBody.innerHTML = html;
}

/**
 * 篩選結果
 */
function filterResults(results, filter) {
    switch (filter) {
        case 'success':
            return results.filter(r => r.isSuccess);
        case 'failure':
            return results.filter(r => !r.isSuccess);
        default:
            return results;
    }
}

/**
 * 取得回應時間等級
 */
function getTimeClass(ms) {
    if (ms < 500) return 'fast';
    if (ms < 2000) return 'normal';
    return 'slow';
}

/**
 * 渲染最後更新時間
 */
function renderLastUpdate(testDate) {
    const date = new Date(testDate);
    const formatted = date.toLocaleString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    elements.lastUpdate.textContent = formatted;
}

/**
 * 設定事件監聽器
 */
function setupEventListeners() {
    elements.filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // 更新 active 狀態
            elements.filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // 更新篩選並重新渲染
            currentFilter = btn.dataset.filter;
            renderResults(testData.detailedResults);
        });
    });
}

/**
 * HTML 跳脫
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 啟動應用程式
document.addEventListener('DOMContentLoaded', init);
