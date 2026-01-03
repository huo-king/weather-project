/**
 * charts.js
 *
 * 【教学版说明】
 * 这是前端“交互与可视化”的核心脚本，主要完成以下事情：
 *
 * 1) 从后端 API 获取数据（/api/*）
 * 2) 用 ECharts 把数据绘制成折线图/柱状图/散点图/热力图
 * 3) 处理页面交互：
 *    - 选择区域、日期、点击“应用筛选”
 *    - 打开/关闭“高级分析”面板
 *    - 登录/注册/重置密码弹窗
 *    - 点击“？”显示论文风格图表说明
 *
 * 运行方式：
 * - 先运行后端 api_server.py
 * - 浏览器打开 http://127.0.0.1:8000/
 * - charts.js 会被 index.html 引入并自动执行
 */

document.addEventListener('DOMContentLoaded', () => {
  // ============================================================
  // 一、初始化 ECharts 实例
  // ============================================================
  // echarts.init() 需要传入 DOM 元素（div），它会在 div 内部渲染图表。
  // 这些 id 对应 index.html 里每个图表容器。
  const charts = {
    aqiTrend: echarts.init(document.getElementById('aqiTrendChart')),      // AQI 趋势折线图
    tempTrend: echarts.init(document.getElementById('tempTrendChart')),    // 温度趋势（最高/最低）折线图
    aqiCompare: echarts.init(document.getElementById('aqiCompareChart')),  // 各区平均AQI对比柱状图
    correlation: echarts.init(document.getElementById('correlationChart')),// 温度-AQI 相关性散点图
  };

  // ============================================================
  // 二、页面状态（区域/时间范围）
  // ============================================================
  // state 用于保存用户当前选择的区域和日期范围。
  // 每次点击“应用筛选”，会更新 state 并重新请求后端数据。
  const state = {
    area: '广州',
    start: '',
    end: '',
    granularity: 'day', // day/week/month
  };

  // ============================================================
  // 三、获取页面上的 DOM 元素
  // ============================================================
  const areaSelect = document.getElementById('areaSelect');
  const preferredAreaSelect = document.getElementById('preferredAreaSelect');
  const savePreferredBtn = document.getElementById('savePreferredBtn');
  const startDateInput = document.getElementById('startDate');
  const endDateInput = document.getElementById('endDate');
  const applyFilterBtn = document.getElementById('applyFilter');

  // ===================== 日/周/月切换 + 导出 =====================
  const granularityGroup = document.getElementById('granularityGroup');
  const exportCsvBtn = document.getElementById('exportCsvBtn');

  // ===================== 高级分析 UI =====================
  const toggleAdvancedBtn = document.getElementById('toggleAdvanced');
  const scrapeNowBtn = document.getElementById('scrapeNowBtn');
  const advancedPanel = document.getElementById('advancedPanel');
  const analysisTypeSelect = document.getElementById('analysisType');
  const runAnalysisBtn = document.getElementById('runAnalysis');
  const runSelfCheckBtn = document.getElementById('runSelfCheck');
  const analysisResults = document.getElementById('analysisResults');

  // ===================== 登录 UI =====================
  const openLoginModalBtn = document.getElementById('openLoginModal');
  const logoutBtn = document.getElementById('logoutBtn');
  const userBadge = document.getElementById('userBadge');

  const authModal = document.getElementById('authModal');
  const authModalClose = document.getElementById('authModalClose');
  const authMsg = document.getElementById('authMsg');

  // 登录表单输入框
  const loginEmail = document.getElementById('loginEmail');
  const loginPassword = document.getElementById('loginPassword');
  const loginSubmit = document.getElementById('loginSubmit');

  // 注册表单输入框
  const regUsername = document.getElementById('regUsername');
  const regEmail = document.getElementById('regEmail');
  const regPassword = document.getElementById('regPassword');
  const registerSubmit = document.getElementById('registerSubmit');

  // 重置密码表单输入框
  const resetEmail = document.getElementById('resetEmail');
  const resetSubmit = document.getElementById('resetSubmit');
  const resetToken = document.getElementById('resetToken');
  const resetNewPassword = document.getElementById('resetNewPassword');
  const resetConfirmBtn = document.getElementById('resetConfirmBtn');

  // ============================================================
  // 四、高级分析图表实例（动态生成）
  // ============================================================
  // 高级分析面板里的图表，会在用户点击“运行分析”后动态插入 DOM。
  // 所以这里用对象保存引用，方便 resize。
  let advancedCharts = {
    regressionScatter: null, // 线性回归：实际 vs 预测散点
    windSpeed: null,         // 风力等级 vs AQI
    windDirection: null,     // 风向 vs AQI
    heatmap: null,           // 三因素热力图
  };

  // ============================================================
  // 五、图表说明（方式B：点击 ? 弹窗）——论文风格
  // ============================================================
  // 这些 DOM 元素来自 index.html 底部的 helpModal。
  const helpModal = document.getElementById('helpModal');
  const helpClose = document.getElementById('helpClose');
  const helpTitle = document.getElementById('helpTitle');
  const helpBody = document.getElementById('helpBody');

  // HELP_TEXT 是一个“说明文本字典”，key 对应每个 ? 按钮的 data-help。
  // html 用模板字符串（反引号）写，可以包含 HTML 标签。
  const HELP_TEXT = {
    aqi_trend: {
      title: 'AQI时间序列变化特征（折线图）',
      html: `
        <h3>研究对象与指标定义</h3>
        <ul>
          <li>图中展示空气质量指数（Air Quality Index, AQI）的时间序列变化。AQI 为综合指数，数值越大表示污染程度越高。</li>
          <li>横轴为日期（YYYY-MM-DD），纵轴为 AQI 值。若选择“广州（全市）”，则采用多辖区数据按日期求均值表征全市整体水平；若选择具体辖区，则为该辖区日尺度观测值。</li>
        </ul>
        <h3>解读要点（论文写法建议）</h3>
        <ul>
          <li>趋势项：观察 AQI 的长期变化趋势（上升/下降/阶段性波动），可作为空气质量季节性或阶段性特征的直观证据。</li>
          <li>极值事件：识别显著峰值（污染过程）与持续高值区间（持续性污染），可在“结果”部分描述为污染过程的起止与强度。</li>
          <li>阈值参考：AQI 常用分级（0–50优、51–100良、101–150轻度污染、151–200中度污染、201–300重度污染、&gt;300严重污染）。</li>
        </ul>
        <h3>注意事项</h3>
        <ul>
          <li>时间序列存在短期随机波动，若需更严格的趋势检验，可进一步采用滑动平均、STL分解或Mann–Kendall检验（本系统提供可视化解释为主）。</li>
        </ul>
      `,
    },

    temp_trend: {
      title: '气温时间序列特征（最高/最低）',
      html: `
        <h3>指标与数据结构</h3>
        <ul>
          <li>展示日最高温（Tmax）与日最低温（Tmin）的时间序列，用于刻画区域热力条件随时间变化的动态特征。</li>
          <li>可通过 Tmax 与 Tmin 的差值近似表征昼夜温差，对边界层稳定度与污染物扩散具有间接指示意义。</li>
        </ul>
        <h3>解读要点</h3>
        <ul>
          <li>温度升高阶段与 AQI 的同步变化，可用于提出“可能相关性”假设（需在后续相关性/回归分析中验证）。</li>
          <li>若出现持续高温且风力偏弱等条件，可能导致静稳与二次污染风险上升（需结合风力/风向与天气类型共同解释）。</li>
        </ul>
        <h3>注意事项</h3>
        <ul>
          <li>温度与AQI关系可能受到季节、降水、风场与排放等多因素共同影响，单变量趋势仅用于描述性分析。</li>
        </ul>
      `,
    },

    aqi_compare: {
      title: '空间差异：各辖区平均AQI对比（柱状图）',
      html: `
        <h3>统计口径</h3>
        <ul>
          <li>在给定时间范围内，对各辖区 AQI 进行均值统计，以反映该时期的平均污染水平。</li>
          <li>该图适用于比较不同辖区空气质量的空间差异，为热点区域识别提供直观依据。</li>
        </ul>
        <h3>解读要点</h3>
        <ul>
          <li>柱体越高表明该辖区在研究时段内平均污染水平越高。</li>
          <li>建议结合 AQI 时间序列图判断高均值是否由少数污染过程驱动。</li>
        </ul>
        <h3>局限性</h3>
        <ul>
          <li>均值对极端值敏感；如需稳健对比，可补充中位数/分位数分析。</li>
        </ul>
      `,
    },

    temp_aqi_corr: {
      title: '温度—AQI相关性分析（散点图与显著性检验）',
      html: `
        <h3>方法说明</h3>
        <ul>
          <li>采用 Pearson 相关系数 r 衡量温度与 AQI 的线性相关强度。</li>
          <li>同时给出 p 值用于显著性检验（p&lt;0.05 常认为相关性具有统计显著性）。</li>
        </ul>
        <h3>强度判别（经验划分）</h3>
        <ul>
          <li>|r| &lt; 0.2：极弱相关</li>
          <li>0.2 ≤ |r| &lt; 0.4：弱相关</li>
          <li>0.4 ≤ |r| &lt; 0.6：中等相关</li>
          <li>0.6 ≤ |r| &lt; 0.8：强相关</li>
          <li>|r| ≥ 0.8：极强相关</li>
        </ul>
        <h3>论文写作建议</h3>
        <ul>
          <li>可写作："最高温与AQI呈显著相关（r=..., p&lt;0.05, n=...）"。</li>
          <li>注意：相关不代表因果，需结合风场、天气形势与排放背景进行讨论。</li>
        </ul>
      `,
    },

    advanced_intro: {
      title: '高级分析模块说明',
      html: `
        <h3>模块定位</h3>
        <ul>
          <li>面向“解释性分析”与“多因素耦合特征识别”。</li>
          <li>包括：线性回归解释（AQI与多气象因素）、风力/风向统计、三因素热力图。</li>
        </ul>
      `,
    },
  };

  /** 打开说明弹窗 */
  function openHelp(key) {
    if (!helpModal) return;

    // 找到对应说明，没有则给默认
    const item = HELP_TEXT[key] || { title: '图表说明', html: '<p>暂无说明</p>' };

    // 更新弹窗标题/内容
    if (helpTitle) helpTitle.textContent = item.title;
    if (helpBody) helpBody.innerHTML = item.html;

    // 显示弹窗（CSS 中用 display:flex 居中）
    helpModal.style.display = 'flex';
  }

  /** 关闭说明弹窗 */
  function closeHelp() {
    if (!helpModal) return;
    helpModal.style.display = 'none';
  }

  /** 给页面所有 .help-btn 绑定点击事件 */
  function initHelpButtons() {
    document.querySelectorAll('.help-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-help');
        openHelp(key);
      });
    });

    // 点击关闭按钮关闭
    if (helpClose) helpClose.addEventListener('click', closeHelp);

    // 点击遮罩层（弹窗外部）关闭
    if (helpModal) {
      helpModal.addEventListener('click', (e) => {
        if (e.target === helpModal) closeHelp();
      });
    }
  }

  // ============================================================
  // 六、鉴权与网络请求封装
  // ============================================================

  /** 在弹窗中显示提示信息 */
  function setAuthMsg(msg) {
    if (!authMsg) return;
    authMsg.textContent = msg || '';
  }

  /** 从 localStorage 取 token */
  function getToken() {
    return localStorage.getItem('access_token') || '';
  }

  /** 保存 token */
  function setToken(token) {
    if (token) localStorage.setItem('access_token', token);
  }

  /** 清理 token（退出登录） */
  function clearToken() {
    localStorage.removeItem('access_token');
  }

  /**
   * fetchJson：统一封装 fetch 请求
   * - 自动带上 Authorization 头
   * - 自动处理 json body
   * - 统一错误提示
   */
  async function fetchJson(url, opts = {}) {
    const headers = opts.headers || {};

    // 如果已登录，则带上 token
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // 如果调用方传了 opts.json，则自动变成 JSON 请求
    if (opts.json) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }

    const res = await fetch(url, { ...opts, headers });

    // 只要不是 2xx，都认为失败
    if (!res.ok) {
      let text = '';
      try {
        text = await res.text();
      } catch (_) {
        // ignore
      }
      throw new Error(`请求失败：${res.status} ${text}`);
    }

    return await res.json();
  }

  /**
   * refreshUserUI：根据 token 状态刷新顶部“已登录/登录按钮/退出按钮”的显示
   */
  async function refreshUserUI() {
    const token = getToken();

    // 没 token => 未登录
    if (!token) {
      if (userBadge) userBadge.style.display = 'none';
      if (logoutBtn) logoutBtn.style.display = 'none';
      if (openLoginModalBtn) openLoginModalBtn.style.display = 'inline-block';

      // 常用辖区下拉框清空
      if (preferredAreaSelect) {
        preferredAreaSelect.innerHTML = '<option value="">（未设置）</option>';
      }
      return;
    }

    // 有 token => 调 /api/users/me 验证 token 并获取用户名
    try {
      const me = await fetchJson('/api/users/me');
      if (userBadge) {
        userBadge.style.display = 'inline-block';
        userBadge.textContent = `已登录：${me.username}`;
      }
      if (logoutBtn) logoutBtn.style.display = 'inline-block';
      if (openLoginModalBtn) openLoginModalBtn.style.display = 'none';

      // 拉取并渲染常用辖区
      await loadPreferredAreas();

      // 已登录状态下，更新社交按钮激活态
      refreshSocialStats();

    } catch (e) {
      // token 无效 => 清除 token，回到未登录状态
      clearToken();
      if (userBadge) userBadge.style.display = 'none';
      if (logoutBtn) logoutBtn.style.display = 'none';
      if (openLoginModalBtn) openLoginModalBtn.style.display = 'inline-block';
      if (preferredAreaSelect) {
        preferredAreaSelect.innerHTML = '<option value="">（未设置）</option>';
      }
    }
  }

  /** 加载常用辖区并填充下拉框 */
  async function loadPreferredAreas() {
    if (!preferredAreaSelect) return;
    try {
      const data = await fetchJson('/api/users/preferred_areas');
      const areas = (data.areas || []).filter(Boolean);

      if (!areas.length) {
        preferredAreaSelect.innerHTML = '<option value="">（未设置）</option>';
        return;
      }

      preferredAreaSelect.innerHTML = ['<option value="">（选择常用辖区）</option>']
        .concat(areas.map(a => `<option value="${a}">${a}</option>`))
        .join('');
    } catch (e) {
      // 静默失败
      preferredAreaSelect.innerHTML = '<option value="">（未设置）</option>';
    }
  }

  // ============================================================
  // 七、登录弹窗逻辑
  // ============================================================

  function openModal() {
    if (!authModal) return;
    authModal.style.display = 'flex';
    setAuthMsg('');
  }

  function closeModal() {
    if (!authModal) return;
    authModal.style.display = 'none';
    setAuthMsg('');
  }

  /** 切换“登录/注册/重置密码”三个 Tab */
  function setupTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(t => {
      t.addEventListener('click', () => {
        // 清除激活样式
        tabs.forEach(x => x.classList.remove('active'));
        t.classList.add('active');

        // 显示对应 panel
        const tab = t.getAttribute('data-tab');
        document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
        document.getElementById(`tab-${tab}`).style.display = 'block';

        setAuthMsg('');
      });
    });
  }

  /** 绑定登录/注册/重置事件 */
  function initAuthUI() {
    setupTabs();

    // 打开弹窗
    if (openLoginModalBtn) openLoginModalBtn.addEventListener('click', openModal);

    // 关闭弹窗
    if (authModalClose) authModalClose.addEventListener('click', closeModal);

    // 点击遮罩关闭
    if (authModal) {
      authModal.addEventListener('click', (e) => {
        if (e.target === authModal) closeModal();
      });
    }

    // 退出登录
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        clearToken();
        refreshUserUI();
        // 退出后隐藏用户面板
        refreshUserPanel();
        // 退出后刷新社交按钮（active=false）
        refreshSocialStats();
        alert('已退出登录');
      });
    }

    // 常用辖区下拉框：选择后直接切换区域
    if (preferredAreaSelect) {
      preferredAreaSelect.addEventListener('change', () => {
        const val = preferredAreaSelect.value;
        if (!val) return;
        if (areaSelect) areaSelect.value = val;
      });
    }

    // 保存当前“区域”为常用辖区（需要登录）
    if (savePreferredBtn) {
      savePreferredBtn.addEventListener('click', async () => {
        if (!getToken()) {
          alert('请先登录后再设置常用辖区');
          return;
        }
        const cur = (areaSelect?.value || '').trim();
        if (!cur || cur === '广州') {
          alert('请选择具体辖区（不支持把“广州（全市）”保存为常用）');
          return;
        }

        try {
          const old = await fetchJson('/api/users/preferred_areas');
          const areas = (old.areas || []).filter(Boolean);
          // 保序去重，把当前放到最前面
          const next = [cur].concat(areas.filter(a => a !== cur)).slice(0, 3);
          await fetchJson('/api/users/preferred_areas', {
            method: 'PUT',
            json: { areas: next },
          });
          await loadPreferredAreas();
          alert('已保存常用辖区');
        } catch (e) {
          alert('保存失败：' + (e.message || ''));
        }
      });
    }

    // 登录
    if (loginSubmit) {
      loginSubmit.addEventListener('click', async () => {
        try {
          setAuthMsg('登录中...');
          const data = await fetchJson('/api/users/login', {
            method: 'POST',
            json: { email: loginEmail.value, password: loginPassword.value },
          });

          // 保存 token
          setToken(data.access_token);

          // 刷新顶部 UI
          await refreshUserUI();

          // 登录后刷新用户面板（收藏/历史）
          refreshUserPanel();

          // 登录后刷新社交按钮激活态
          refreshSocialStats();

          setAuthMsg('登录成功');
          closeModal();
        } catch (e) {
          setAuthMsg('登录失败：' + (e.message || ''));
        }
      });
    }

    // 注册
    if (registerSubmit) {
      registerSubmit.addEventListener('click', async () => {
        try {
          setAuthMsg('注册中...');
          await fetchJson('/api/users/register', {
            method: 'POST',
            json: {
              username: regUsername.value,
              email: regEmail.value,
              password: regPassword.value,
            },
          });
          setAuthMsg('注册成功，请切换到“登录”进行登录');
        } catch (e) {
          setAuthMsg('注册失败：' + (e.message || ''));
        }
      });
    }

    // 请求重置 token（演示：直接返回 token）
    if (resetSubmit) {
      resetSubmit.addEventListener('click', async () => {
        try {
          setAuthMsg('请求重置token...');
          const data = await fetchJson('/api/users/password_reset/request', {
            method: 'POST',
            json: { email: resetEmail.value },
          });
          resetToken.value = data.reset_token;
          setAuthMsg('已生成重置Token（演示版），请粘贴token并设置新密码后点击确认');
        } catch (e) {
          setAuthMsg('获取token失败：' + (e.message || ''));
        }
      });
    }

    // 确认重置
    if (resetConfirmBtn) {
      resetConfirmBtn.addEventListener('click', async () => {
        try {
          setAuthMsg('重置中...');
          await fetchJson('/api/users/password_reset/confirm', {
            method: 'POST',
            json: { token: resetToken.value, new_password: resetNewPassword.value },
          });
          setAuthMsg('重置成功，请返回登录');
        } catch (e) {
          setAuthMsg('重置失败：' + (e.message || ''));
        }
      });
    }

    // 页面加载时刷新一次用户状态
    refreshUserUI();
  }

  // ============================================================
  // 八、图表数据请求与渲染（基础图表）
  // ============================================================

  /** 把 Date 转成 yyyy-mm-dd */
  function formatDate(date) {
    return date.toISOString().split('T')[0];
  }

  /** p 值格式化：论文常用写法 */
  function formatP(p) {
    if (p === null || p === undefined || isNaN(p)) return 'N/A';
    if (p < 0.001) return '< 0.001';
    return Number(p).toFixed(4);
  }

  /** 初始化顶部筛选控件（区域下拉框、默认日期） */
  function initControls() {
    const today = new Date();

    // 手动采集按钮（B方案：不自动定时，不影响原功能）
    if (scrapeNowBtn) {
      scrapeNowBtn.addEventListener('click', async () => {
        const ok = confirm('确定要手动采集一次 2345 天气数据并写入数据库吗？\n\n提示：可能需要几十秒到几分钟，期间请不要频繁重复点击。');
        if (!ok) return;

        scrapeNowBtn.disabled = true;
        const oldText = scrapeNowBtn.textContent;
        scrapeNowBtn.textContent = '采集中...';

        try {
          const res = await fetchJson('/api/admin/scrape_now', { method: 'POST' });
          if (res.ok) {
            alert(`采集完成！\n本次爬取：${res.total_scraped} 条\n入库新增：${res.inserted} 条`);
            // 采集后刷新图表（可选）
            fetchAllCharts();
          } else {
            alert('采集失败：' + (res.error || '未知错误'));
          }
        } catch (e) {
          alert('采集请求失败：' + (e.message || ''));
        } finally {
          scrapeNowBtn.disabled = false;
          scrapeNowBtn.textContent = oldText;
        }
      });
    }

    // 默认日期：从 2024-01-01 到 今天
    state.end = formatDate(today);
    state.start = '2024-01-01';

    // 写回到 date input
    endDateInput.value = state.end;
    startDateInput.value = state.start;

    // 1) 加载区域列表，填充下拉框
    // 后端 /api/areas 返回 {areas:["广州", "从化区", ...]}
    fetchJson('/api/areas', { headers: {} })
      .then(data => {
        data.areas.forEach(area => {
          if (area !== '广州') {
            const option = document.createElement('option');
            option.value = area;
            option.textContent = area;
            areaSelect.appendChild(option);
          }
        });
      })
      .catch(() => {
        // 如果加载失败，页面仍然可以用默认“广州”
      });

    // 2) 点击“应用筛选” => 更新 state 并重新请求数据
    applyFilterBtn.addEventListener('click', async () => {
      state.area = areaSelect.value;
      state.start = startDateInput.value;
      state.end = endDateInput.value;


      // 重新加载四张基础图
      fetchAllCharts();

      // 同步刷新社交统计
      refreshSocialStats();

      // 若用户登录，则写入历史记录
      if (getToken()) {
        fetchJson('/api/users/history', {
          method: 'POST',
          json: { area: state.area, start: state.start, end: state.end },
        }).catch(() => {});
      }

      // 若高级面板打开，也刷新高级分析
      if (advancedPanel && advancedPanel.style.display !== 'none') {
        runAdvancedAnalysis();
      }
    });

    // 3) 高级分析面板折叠/展开
    if (toggleAdvancedBtn && advancedPanel) {
      toggleAdvancedBtn.addEventListener('click', () => {
        const isHidden = advancedPanel.style.display === 'none';
        advancedPanel.style.display = isHidden ? 'block' : 'none';
        if (isHidden) runAdvancedAnalysis();
      });
    }

    // 4) 点击“运行分析”
    if (runAnalysisBtn) {
      runAnalysisBtn.addEventListener('click', () => runAdvancedAnalysis());
    }

    // 4.1) 一键运行自检
    if (runSelfCheckBtn) {
      runSelfCheckBtn.addEventListener('click', () => runSelfCheck());
    }

    if (document.getElementById('compareWithSource')) {
      document.getElementById('compareWithSource').addEventListener('click', () => runDataComparison());
    }

    // 5) 日/周/月切换
    if (granularityGroup) {
      granularityGroup.addEventListener('click', (e) => {
        if (e.target.classList.contains('gran-btn')) {
          document.querySelectorAll('.gran-btn').forEach(b => b.classList.remove('active'));
          e.target.classList.add('active');
          state.granularity = e.target.dataset.gran || 'day';
          fetchAllCharts();
        }
      });
    }

    // 6) 导出 CSV
    if (exportCsvBtn) {
      exportCsvBtn.addEventListener('click', () => {
        const { area, start, end } = state;
        const url = `/api/export/weather_data.csv?area=${encodeURIComponent(area)}&start=${start}&end=${end}`;
        window.open(url, '_blank');
      });
    }
  }

  /** 显示加载动画 */
  function showLoadingBasic() {
    Object.values(charts).forEach(chart => chart.showLoading());
  }

  /** 并行加载四张基础图 */
  function fetchAllCharts() {
    showLoadingBasic();

    // Promise.all：四个请求全部成功才算成功
    Promise.all([
      fetchAqiTrend(),
      fetchTempTrend(),
      fetchAqiCompare(),
      fetchCorrelation(),
    ]).catch(err => {
      console.error('Failed to load charts:', err);
      alert('加载图表失败，请检查后端服务是否开启，或刷新页面重试。');
    });
  }

  /** AQI趋势图：请求后端并绘制折线 */
  function fetchAqiTrend() {
    const { area, start, end } = state;

    return fetchJson(`/api/trend/aqi?area=${encodeURIComponent(area)}&start=${start}&end=${end}&granularity=${state.granularity}`, { headers: {} })
      .then(data => {
        charts.aqiTrend.hideLoading();

        // setOption 是 ECharts 的核心：传入 option 对象即可绘图
        charts.aqiTrend.setOption({
          tooltip: { trigger: 'axis' },
          toolbox: {
            feature: {
              dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原' } },
              saveAsImage: { title: '下载图片' }
            }
          },
          xAxis: { type: 'category', data: data.x },
          yAxis: { type: 'value', name: 'AQI' },
          series: [{ type: 'line', data: data.y, smooth: true }],
          grid: { left: '10%', right: '5%', bottom: '15%' },
        });
      });
  }

  /** 温度趋势：最高/最低两条线 */
  function fetchTempTrend() {
    const { area, start, end } = state;

    return fetchJson(`/api/trend/temp?area=${encodeURIComponent(area)}&start=${start}&end=${end}&granularity=${state.granularity}`, { headers: {} })
      .then(data => {
        charts.tempTrend.hideLoading();

        charts.tempTrend.setOption({
          tooltip: { trigger: 'axis' },
          toolbox: {
            feature: {
              dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原' } },
              saveAsImage: { title: '下载图片' }
            }
          },
          legend: { data: ['最高温', '最低温'] },
          xAxis: { type: 'category', data: data.x },
          yAxis: { type: 'value', name: '温度(℃)' },
          series: [
            { name: '最高温', type: 'line', data: data.max, smooth: true, color: '#d9534f' },
            { name: '最低温', type: 'line', data: data.min, smooth: true, color: '#5bc0de' },
          ],
          grid: { left: '10%', right: '5%', bottom: '15%' },
        });
      });
  }

  /** 各区平均AQI对比：柱状图 */
  function fetchAqiCompare() {
    const { start, end } = state;

    return fetchJson(`/api/compare/aqi?start=${start}&end=${end}&granularity=${state.granularity}`, { headers: {} })
      .then(data => {
        charts.aqiCompare.hideLoading();

        charts.aqiCompare.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          toolbox: {
            feature: {
              dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原' } },
              saveAsImage: { title: '下载图片' }
            }
          },
          xAxis: { type: 'category', data: data.data.map(d => d.area), axisLabel: { rotate: 30 } },
          yAxis: { type: 'value', name: '平均AQI' },
          series: [{ type: 'bar', data: data.data.map(d => d.aqi_avg) }],
          grid: { left: '10%', right: '5%', bottom: '20%' },
        });
      });
  }

  /** 温度与AQI相关性：散点图 + r/p/n */
  function fetchCorrelation() {
    const { area, start, end } = state;

    return fetchJson(`/api/correlation/temp_aqi?area=${encodeURIComponent(area)}&start=${start}&end=${end}`, { headers: {} })
      .then(data => {
        charts.correlation.hideLoading();

        charts.correlation.setOption({
          tooltip: { trigger: 'item', formatter: p => `温度: ${p.value[0]}℃, AQI: ${p.value[1]}` },
          toolbox: {
            feature: {
              dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原' } },
              saveAsImage: { title: '下载图片' }
            }
          },
          legend: { data: ['最高温 vs AQI', '最低温 vs AQI'] },
          xAxis: { type: 'value', name: '温度(℃)', splitLine: { show: false } },
          yAxis: { type: 'value', name: 'AQI', splitLine: { show: false } },
          series: [
            { name: '最高温 vs AQI', type: 'scatter', data: data.points_max, color: '#d9534f' },
            { name: '最低温 vs AQI', type: 'scatter', data: data.points_min, color: '#5bc0de' },
          ],
          grid: { left: '10%', right: '5%', bottom: '15%' },
        });

        // 在图下方显示 r/p/n
        document.getElementById('correlationResult').innerHTML = `
          最高温与AQI相关系数: <strong>${data.corr_max_aqi?.toFixed(4) ?? 'N/A'}</strong>
          <span style="color:#666">(p=${formatP(data.p_max_aqi)}, n=${data.n ?? 'N/A'})</span><br/>
          最低温与AQI相关系数: <strong>${data.corr_min_aqi?.toFixed(4) ?? 'N/A'}</strong>
          <span style="color:#666">(p=${formatP(data.p_min_aqi)}, n=${data.n ?? 'N/A'})</span>
        `;
      });
  }

  /**
   * 一键运行自检：真实 vs 预测 + MAPE/阈值
   */
  async function runSelfCheck() {
    if (!analysisResults) return;
    
    // 保持与基础筛选同步
    state.area = areaSelect.value;
    
    analysisResults.innerHTML = '<div class="loading">自检中，请稍候...</div>';
    
    try {
      // 1. 获取真实 vs 预测数据
      const data = await fetchJson(`/api/analysis/selfcheck?area=${encodeURIComponent(state.area)}&backtest_days=7&threshold=0.3&web_sample_size=20&web_error_rate_limit=0.05`);
      
      if (data.error) {
        renderError(data.error);
        return;
      }
      
      // 2. 渲染结果（后端返回：web_consistency + forecast_eval）
      const web = data.web_consistency || {};
      const forecast = data.forecast_eval || {};

      const webPass = !!web.pass;
      const forecastPass = !!forecast.pass;
      const passed = !!data.ok;

      const mape = Number(forecast.mape);
      const threshold = Number(forecast.threshold);
      const points = forecast.points || [];

      const webErrorRate = (web.error_rate === null || web.error_rate === undefined) ? null : Number(web.error_rate);
      const webLimit = (web.limit === null || web.limit === undefined) ? null : Number(web.limit);
      const webValid = (web.valid === null || web.valid === undefined) ? null : Number(web.valid);
      const webSampleSize = (web.sample_size === null || web.sample_size === undefined) ? null : Number(web.sample_size);

      const passText = passed ? '通过' : '不通过';
      const passClass = passed ? 'pass' : 'fail';
      
      // 3. 渲染结果卡片
      analysisResults.innerHTML = `
        <div class="result-card">
          <h3>模型自检报告（${state.area}）</h3>
          <div class="metrics">
            <div class="metric">
              <div class="label">数据一致性(抽检)</div>
              <div class="value">${(webErrorRate === null) ? 'N/A' : (webErrorRate * 100).toFixed(2) + '%'} ${webPass ? '✓' : '✗'} ${webValid === null ? '' : `(valid=${webValid}/${webSampleSize ?? ''})`}</div>
            </div>
            <div class="metric">
              <div class="label">一致性阈值</div>
              <div class="value">${(webLimit === null) ? 'N/A' : (webLimit * 100).toFixed(0) + '%'}</div>
            </div>
            <div class="metric">
              <div class="label">MAPE(7天)</div>
              <div class="value">${isFinite(mape) ? (mape * 100).toFixed(2) + '%' : 'N/A'} ${forecastPass ? '✓' : '✗'}</div>
            </div>
            <div class="metric">
              <div class="label">准确率要求</div>
              <div class="value">≥70%（等价：MAPE≤${isFinite(threshold) ? (threshold * 100).toFixed(0) : 'N/A'}%）</div>
            </div>
            <div class="metric">
              <div class="label">综合结果</div>
              <div class="value ${passClass}">${passText}</div>
            </div>
          </div>
          <div id="selfCheckChart" class="chart" style="height: 400px;"></div>
          <div class="small-tip">
            说明：
            <br/>1）数据一致性：从数据库随机抽取样本，与 2345 天气网页面再次解析的数据比对；不一致率 ≤ ${(webLimit === null) ? 'N/A' : (webLimit * 100).toFixed(0) + '%'} 视为通过。
            <br/>2）预测准确性：对最近 7 天做滚动回测；用 MAPE 衡量误差，MAPE ≤ ${(isFinite(threshold) ? (threshold * 100).toFixed(0) : 'N/A')}% 视为“准确率≥70%”。
            <br/>3）综合结果：以上两项都通过才算通过。
          </div>
        </div>
      `;
      
      // 4. 绘制真实 vs 预测折线图
      if (points.length > 0) {
        const chart = echarts.init(document.getElementById('selfCheckChart'));
        const dates = points.map(p => p.date);
        const actual = points.map(p => p.real);
        const predicted = points.map(p => p.pred);
        
        chart.setOption({
          tooltip: {
            trigger: 'axis',
            formatter: (params) => {
              const date = params[0].axisValue;
              const a = params[0].data;
              const p = params[1].data;
              const diff = Math.abs(a - p);
              const diffPct = (diff / a * 100).toFixed(2);
              return `
                <div>日期: ${date}</div>
                <div>实际值: ${a}</div>
                <div>预测值: ${p}</div>
                <div>绝对误差: ${diff.toFixed(2)} (${diffPct}%)</div>
              `;
            }
          },
          legend: {
            data: ['实际值', '预测值']
          },
          xAxis: {
            type: 'category',
            data: dates,
            axisLabel: {
              rotate: 45,
              fontSize: 10
            }
          },
          yAxis: {
            type: 'value',
            name: 'AQI'
          },
          series: [
            {
              name: '实际值',
              type: 'line',
              data: actual,
              smooth: true,
              lineStyle: { width: 2 }
            },
            {
              name: '预测值',
              type: 'line',
              data: predicted,
              smooth: true,
              lineStyle: { width: 2, type: 'dashed' },
              itemStyle: { opacity: 0.8 }
            }
          ],
          grid: {
            left: '10%',
            right: '5%',
            bottom: '25%'
          }
        });
        
        // 保存图表引用，用于窗口大小变化时重绘
        advancedCharts.selfCheck = chart;
      }
      
    } catch (e) {
      console.error('自检失败:', e);
      renderError('自检失败: ' + (e.message || '未知错误'));
    }
  }

  // ============================================================
  // 九、高级分析（线性回归/风向风力/三因素热力图）
  // ============================================================

  function renderError(msg) {
    analysisResults.innerHTML = `<div class="error-message">${msg}</div>`;
  }

  /** 根据 analysisType 下拉框调用不同接口 */
  async function runAdvancedAnalysis() {
    if (!analysisResults) return;

    // 保持与基础筛选同步
    state.area = areaSelect.value;
    state.start = startDateInput.value;
    state.end = endDateInput.value;

    const analysisType = analysisTypeSelect?.value || 'regression';
    analysisResults.innerHTML = '<div class="loading">分析中，请稍候...</div>';

    try {
      if (analysisType === 'regression') {
        const data = await fetchJson(`/api/analysis/linear_regression?area=${encodeURIComponent(state.area)}&start=${state.start}&end=${state.end}`, { headers: {} });
        renderRegression(data);
      } else if (analysisType === 'wind') {
        const data = await fetchJson(`/api/analysis/wind_vs_aqi?area=${encodeURIComponent(state.area)}&start=${state.start}&end=${state.end}`, { headers: {} });
        renderWind(data);
      } else if (analysisType === 'multi') {
        const data = await fetchJson(`/api/analysis/multi_factor?area=${encodeURIComponent(state.area)}&start=${state.start}&end=${state.end}`, { headers: {} });
        renderMultiFactorHeatmap(data);
      } else if (analysisType === 'forecast_7d') {
        const data = await fetchJson(`/api/analysis/forecast_7d?area=${encodeURIComponent(state.area)}&start=${state.start}&end=${state.end}`, { headers: {} });
        renderForecast7d(data);
      } else {
        renderError('未知分析类型');
      }
    } catch (e) {
      console.error(e);
      renderError(e.message || '分析失败');
    }
  }

  /** 渲染线性回归结果：R²/RMSE + 实际vs预测散点 */
  function renderRegression(data) {
    if (data.error) {
      renderError(data.error);
      return;
    }

    analysisResults.innerHTML = `
      <div class="result-card">
        <h3>线性回归：预测AQI与气象因素关系（${data.area}）</h3>
        <div class="metrics">
          <div class="metric"><div class="label">R²</div><div class="value">${(data.model_score_r2 ?? 0).toFixed(4)}</div></div>
          <div class="metric"><div class="label">RMSE</div><div class="value">${(data.rmse ?? 0).toFixed(2)}</div></div>
        </div>
        <div id="regressionScatter" class="chart"></div>
      </div>
    `;

    // 这里要注意：DOM 是动态插入的，所以要在插入后才能 init echarts
    const el = document.getElementById('regressionScatter');
    advancedCharts.regressionScatter = echarts.init(el);

    // scatter_data 里已经是实际/预测数组
    const pts = (data.scatter_data?.actual || []).map((a, i) => [a, data.scatter_data.predicted[i]]);

    advancedCharts.regressionScatter.setOption({
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', name: '实际AQI' },
      yAxis: { type: 'value', name: '预测AQI' },
      series: [{ type: 'scatter', data: pts, symbolSize: 7 }],
      grid: { left: '10%', right: '5%', bottom: '15%' },
    });
  }

  /** 渲染风力等级/风向与AQI的柱状图 */
  function renderWind(data) {
    analysisResults.innerHTML = `
      <div class="result-card">
        <h3>风力等级/风向 与 AQI（${data.area}）</h3>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1rem;">
          <div>
            <h4>风力等级 vs 平均AQI</h4>
            <div id="windSpeedChart" class="chart"></div>
          </div>
          <div>
            <h4>风向 vs 平均AQI</h4>
            <div id="windDirChart" class="chart"></div>
          </div>
        </div>
      </div>
    `;

    const speed = data.speed_analysis || [];
    const dir = data.direction_analysis || [];

    advancedCharts.windSpeed = echarts.init(document.getElementById('windSpeedChart'));
    advancedCharts.windDirection = echarts.init(document.getElementById('windDirChart'));

    // 风力等级图
    advancedCharts.windSpeed.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'category', data: speed.map(x => `${x.wind_speed}级`) },
      yAxis: { type: 'value', name: '平均AQI' },
      series: [{ type: 'bar', data: speed.map(x => Number(x.mean).toFixed(2)) }],
      grid: { left: '10%', right: '5%', bottom: '20%' },
    });

    // 风向可能很多，前端只展示前20个（避免太拥挤）
    const dirTop = dir.slice(0, 20);
    advancedCharts.windDirection.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'category', data: dirTop.map(x => x.wind_direction), axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', name: '平均AQI' },
      series: [{ type: 'bar', data: dirTop.map(x => Number(x.mean).toFixed(2)) }],
      grid: { left: '10%', right: '5%', bottom: '30%' },
    });
  }

  /**
   * 渲染未来7天AQI预测（折线 + 区间带）
   *
   * 后端返回格式（analysis.py -> forecast_aqi_7_days）：
   * {
   *   area: '从化区',
   *   forecast: [
   *     {date:'2024-01-02', aqi_p10:xx, aqi_p50:xx, aqi_p90:xx, level:'良'},
   *     ... 共7条
   *   ],
   *   model_info: {...}
   * }
   */
  function renderForecast7d(data) {
    if (data.error) {
      renderError(data.error);
      return;
    }

    const rows = data.forecast || [];
    if (!rows.length) {
      renderError('预测结果为空（可能是样本不足或时间范围不包含足够历史数据）。');
      return;
    }

    // 兼容旧接口：如果后端还没给 tip/color/confidence，这里给默认值
    const safeRows = rows.map(r => ({
      ...r,
      tip: r.tip || '-',
      color: r.color || '#333',
      confidence: (r.confidence === undefined || r.confidence === null) ? null : Number(r.confidence),
    }));

    // 1) 先把预测结果渲染出一个图表容器 + 表格
    analysisResults.innerHTML = `
      <div class="result-card">
        <h3>未来7天AQI预测（${data.area}）</h3>
        <div class="small-tip">
          说明：中位数预测（P50）作为主预测；P10-P90 为预测不确定性区间（分位数回归）。
        </div>
        <div id="forecastChart" class="chart" style="height:420px;"></div>
        <div class="feature-importance" style="margin-top: 12px;">
          <h4>预测明细（含风险等级/提示/置信度）</h4>
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>P50(预测)</th>
                <th>区间(P10~P90)</th>
                <th>等级</th>
                <th>健康提示</th>
                <th>置信度</th>
              </tr>
            </thead>
            <tbody>
              ${safeRows.map(r => {
                const confText = (r.confidence === null) ? 'N/A' : (Number(r.confidence) * 100).toFixed(1) + '%';
                return `
                  <tr>
                    <td>${r.date}</td>
                    <td><strong>${Number(r.aqi_p50).toFixed(2)}</strong></td>
                    <td>${Number(r.aqi_p10).toFixed(2)} ~ ${Number(r.aqi_p90).toFixed(2)}</td>
                    <td><span style="color:${r.color}">${r.level}</span></td>
                    <td style="max-width:520px;">${r.tip}</td>
                    <td>${confText}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
        <div class="small-tip" style="margin-top: 10px;">
          模型信息：训练样本数=${data.model_info?.train_samples ?? 'N/A'}，lags=${data.model_info?.lags ?? 'N/A'}。
          ${data.model_info?.note ? ('<br/>' + data.model_info.note) : ''}
        </div>
      </div>
    `;

    // 2) 准备 ECharts 数据
    const x = safeRows.map(r => r.date);
    const p10 = safeRows.map(r => Number(r.aqi_p10));
    const p50 = safeRows.map(r => Number(r.aqi_p50));
    const p90 = safeRows.map(r => Number(r.aqi_p90));

    // 3) 画“区间带”（两条线叠加 areaStyle）
    const chart = echarts.init(document.getElementById('forecastChart'));
    advancedCharts.forecast = chart;

    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['P50预测', 'P10下界', 'P90上界'] },
      xAxis: { type: 'category', data: x },
      yAxis: { type: 'value', name: 'AQI' },
      series: [
        {
          name: 'P90上界',
          type: 'line',
          data: p90,
          smooth: true,
          lineStyle: { opacity: 0.15 },
          areaStyle: { opacity: 0.18 },
          symbol: 'none',
        },
        {
          name: 'P10下界',
          type: 'line',
          data: p10,
          smooth: true,
          lineStyle: { opacity: 0.15 },
          stack: 'band',
          areaStyle: { opacity: 0.18 },
          symbol: 'none',
        },
        {
          name: 'P50预测',
          type: 'line',
          data: p50,
          smooth: true,
          lineStyle: { width: 3 },
        },
      ],
      grid: { left: '10%', right: '5%', bottom: '15%' },
    });
  }

  /** 渲染三因素热力图：温度分箱×风力分箱（按天气筛选） */
  function renderMultiFactorHeatmap(data) {
    const heat = data.heatmap_data || [];
    if (!heat.length) {
      renderError('无可用数据（可能是样本太少）');
      return;
    }

    // 抽取所有天气类型作为下拉筛选项
    const weathers = Array.from(new Set(heat.map(x => x.weather_simple))).filter(Boolean);
    const weatherOptions = weathers.map(w => `<option value="${w}">${w}</option>`).join('');

    analysisResults.innerHTML = `
      <div class="result-card">
        <h3>三因素关系：温度×风力（按天气筛选）热力图（${data.area}）</h3>
        <div class="analysis-controls">
          <label>天气类型：
            <select id="weatherFilter">${weatherOptions}</select>
          </label>
          <button id="refreshHeat">刷新热力图</button>
        </div>
        <div id="heatmapChart" class="chart" style="height:520px;"></div>
      </div>
    `;

    const weatherFilter = document.getElementById('weatherFilter');
    const refreshBtn = document.getElementById('refreshHeat');

    function drawHeatmap() {
      // 选中的天气类型
      const w = weatherFilter.value;

      // 只取该天气类型的数据
      const filtered = heat.filter(x => x.weather_simple === w);

      // x轴（温度分箱）与 y轴（风力分箱）
      const tempAxis = Array.from(new Set(filtered.map(x => x.temp_bin))).filter(Boolean);
      const windAxis = Array.from(new Set(filtered.map(x => x.wind_bin))).filter(Boolean);

      // heatmap 的数据格式：[xIndex, yIndex, value]
      const seriesData = filtered.map(x => [
        tempAxis.indexOf(x.temp_bin),
        windAxis.indexOf(x.wind_bin),
        Number(x.aqi)
      ]);

      const values = filtered.map(x => Number(x.aqi));
      const vmin = Math.min(...values);
      const vmax = Math.max(...values);

      advancedCharts.heatmap = echarts.init(document.getElementById('heatmapChart'));
      advancedCharts.heatmap.setOption({
        tooltip: {
          position: 'top',
          formatter: p => `温度:${tempAxis[p.value[0]]}<br/>风力:${windAxis[p.value[1]]}<br/>平均AQI:${Number(p.value[2]).toFixed(2)}`,
        },
        grid: { left: '10%', right: '5%', bottom: '18%', containLabel: true },
        xAxis: { type: 'category', data: tempAxis, name: '温度分箱', splitArea: { show: true } },
        yAxis: { type: 'category', data: windAxis, name: '风力分箱', splitArea: { show: true } },
        visualMap: {
          min: isFinite(vmin) ? vmin : 0,
          max: isFinite(vmax) ? vmax : 100,
          calculable: true,
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
        },
        series: [{
          name: 'AQI',
          type: 'heatmap',
          data: seriesData,
          label: { show: true, formatter: p => Number(p.value[2]).toFixed(1) },
          emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } },
        }],
      });
    }

    // 点击刷新按钮重绘热力图
    refreshBtn.addEventListener('click', drawHeatmap);

    // 默认绘制一次
    drawHeatmap();
  }

  // ============================================================
  // 十、社交按钮（收藏★/点赞❤/关注＋）
  // ============================================================

  // 顶部社交按钮（按“当前选择区域”统计）
  const btnFavorite = document.getElementById('btnFavorite');
  const btnLike = document.getElementById('btnLike');
  const btnFollow = document.getElementById('btnFollow');

  const countFavorite = document.getElementById('countFavorite');
  const countLike = document.getElementById('countLike');
  const countFollow = document.getElementById('countFollow');

  function formatCount(n) {
    const num = Number(n || 0);
    if (!isFinite(num)) return '0';
    if (num <= 9999) return String(Math.max(0, Math.trunc(num)));

    // >= 10000 -> 1.0w, 15000 -> 1.5w
    const w = num / 10000;
    const s = w.toFixed(1);
    return (s.endsWith('.0') ? s : s) + 'w';
  }

  function setSocialBtnState(btn, countEl, active, count) {
    if (btn) btn.classList.toggle('active', !!active);
    if (countEl) countEl.textContent = formatCount(count);
  }

  async function refreshSocialStats() {
    if (!btnLike && !btnFavorite && !btnFollow) return;

    const area = areaSelect?.value || state.area || '广州';

    try {
      const data = await fetchJson(`/api/social/stats?area=${encodeURIComponent(area)}`, { headers: {} });
      setSocialBtnState(btnLike, countLike, data?.like?.active, data?.like?.count);
      setSocialBtnState(btnFavorite, countFavorite, data?.favorite?.active, data?.favorite?.count);
      setSocialBtnState(btnFollow, countFollow, data?.follow?.active, data?.follow?.count);
    } catch (e) {
      // 静默失败：不影响主图表
      console.warn('refreshSocialStats failed:', e);
    }
  }

  // 旧的按区域社交 toggle 逻辑保留（目前顶部按钮已移除，不再使用）
  async function toggleSocial(type) {
    if (!getToken()) {
      alert('请先登录后再使用该功能');
      return;
    }

    const area = areaSelect?.value || state.area || '广州';

    // 查找对应的按钮和 count 元素
    const btnMap = { favorite: btnFavorite, like: btnLike, follow: btnFollow };
    const countMap = { favorite: countFavorite, like: countLike, follow: countFollow };
    const btn = btnMap[type];
    if (!btn) return;

    // 进入加载状态，防止连点
    btn.disabled = true;
    const originalIcon = btn.querySelector('.icon').innerHTML;
    btn.querySelector('.icon').innerHTML = '...';

    try {
      const res = await fetchJson('/api/social/toggle', {
        method: 'POST',
        json: { type, area },
      });

      if (!res || !res.ok) {
        alert('操作失败');
        return;
      }

      // 更新对应按钮状态
      setSocialBtnState(btn, countMap[type], res.active, res.count);
    } catch (e) {
      alert('请求失败：' + (e.message || ''));
      // 失败时刷新一次，恢复到服务器的真实状态
      refreshSocialStats();
    } finally {
      // 恢复按钮状态
      btn.disabled = false;
      btn.querySelector('.icon').innerHTML = originalIcon;
    }
  }

  function initSocialButtons() {
    if (btnLike) btnLike.addEventListener('click', () => toggleSocial('like'));
    if (btnFavorite) btnFavorite.addEventListener('click', () => toggleSocial('favorite'));
    if (btnFollow) btnFollow.addEventListener('click', () => toggleSocial('follow'));

    // 区域切换时刷新统计
    if (areaSelect) {
      areaSelect.addEventListener('change', () => {
        state.area = areaSelect.value;
        refreshSocialStats();
      });
    }

    // 初始刷新一次
    refreshSocialStats();
  }


  // ============================================================
  // 十、用户面板：收藏 / 历史
  // ============================================================

  const userPanel = document.getElementById('userPanel');
  const favoritesList = document.getElementById('favoritesList');
  const historyList = document.getElementById('historyList');

  function initUserPanelTabs() {
    const tabs = document.querySelectorAll('.user-panel-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.user-panel-pane').forEach(p => p.classList.remove('active'));
        document.getElementById(tab.dataset.tab + 'Content').classList.add('active');
      });
    });
  }

  async function loadFavorites() {
    if (!favoritesList) return;
    favoritesList.innerHTML = '';

    try {
      const favorites = await fetchJson('/api/users/favorites');
      favorites.forEach(fav => {
        const li = document.createElement('li');
        const text = document.createElement('span');
        text.textContent = `${fav.chart_type} - ${fav.area}`;
        text.className = 'user-item-link';
        text.addEventListener('click', () => {
          areaSelect.value = fav.area;
          fetchAllCharts();
        });

        const btn = document.createElement('button');
        btn.textContent = '删除';
        btn.className = 'user-item-btn';
        btn.addEventListener('click', async () => {
          await fetchJson(`/api/users/favorites/${fav.id}`, { method: 'DELETE' });
          loadFavorites();
        });

        li.appendChild(text);
        li.appendChild(btn);
        favoritesList.appendChild(li);
      });
    } catch (e) {
      favoritesList.innerHTML = '<li>加载收藏失败</li>';
    }
  }

  async function loadHistory() {
    if (!historyList) return;
    historyList.innerHTML = '';

    try {
      const history = await fetchJson('/api/users/history');
      history.forEach(h => {
        const li = document.createElement('li');
        const text = document.createElement('span');
        const p = h.search_params;
        text.textContent = `${p.area} | ${p.start || ''} ~ ${p.end || ''}`;
        text.className = 'user-item-link';
        text.addEventListener('click', () => {
          areaSelect.value = p.area;
          startDateInput.value = p.start;
          endDateInput.value = p.end;
          state.area = p.area;
          state.start = p.start;
          state.end = p.end;
          fetchAllCharts();
        });

        li.appendChild(text);
        historyList.appendChild(li);
      });
    } catch (e) {
      historyList.innerHTML = '<li>加载历史失败</li>';
    }
  }

  function refreshUserPanel() {
    if (!userPanel) return;

    if (!getToken()) {
      userPanel.style.display = 'none';
      return;
    }

    userPanel.style.display = 'block';
    loadFavorites();
    loadHistory();
  }


  // ============================================================
  // 十、初始化与窗口 resize
  // ============================================================

  // 初始化各种 UI 事件
  initControls();
  initAuthUI();
  initHelpButtons();
  initSocialButtons();
  initUserPanelTabs();
  refreshUserPanel();

  // 添加对比数据源功能
  async function runDataComparison() {
    try {
      // 显示加载中
      if (analysisResults) {
        analysisResults.innerHTML = '<div class="loading">正在对比数据，请稍候...</div>';
      }
      
      // 调用后端接口获取对比数据
      const data = await fetchJson(`/api/quality/web_consistency?sample_size=20&recent_days=7`);
      
      if (data.error) {
        renderError(data.error);
        return;
      }

      // 计算准确率
      const total = data.valid || 1;
      const correct = data.pass || 0;
      const accuracy = (correct / total * 100).toFixed(2) + '%';
      
      // 创建弹窗
      const modal = document.createElement('div');
      modal.className = 'data-compare-modal';
      modal.innerHTML = `
        <div class="data-compare-content">
          <h3>数据源对比结果</h3>
          <p>共对比 ${data.sample_size} 条数据，有效对比 ${data.valid} 条，一致 ${data.pass} 条，一致率: <strong>${accuracy}</strong></p>
          
          <table class="data-compare-table">
            <thead>
              <tr>
                <th>区域</th>
                <th>日期</th>
                <th>AQI (本地/网站)</th>
                <th>最高温 (本地/网站)</th>
                <th>最低温 (本地/网站)</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              ${data.items ? data.items.map(item => `
                <tr class="${item.ok ? 'match' : 'mismatch'}">
                  <td>${item.area || ''}</td>
                  <td>${item.date || ''}</td>
                  <td>${item.db_aqi !== null ? item.db_aqi : 'N/A'} / ${item.web_aqi !== null ? item.web_aqi : 'N/A'}</td>
                  <td>${item.db_max_temp !== null ? item.db_max_temp : 'N/A'} / ${item.web_max_temp !== null ? item.web_max_temp : 'N/A'}</td>
                  <td>${item.db_min_temp !== null ? item.db_min_temp : 'N/A'} / ${item.web_min_temp !== null ? item.web_min_temp : 'N/A'}</td>
                  <td>${item.ok ? '✓ 一致' : '✗ 不一致'}</td>
                </tr>
              `).join('') : '<tr><td colspan="6">没有对比数据</td></tr>'}
            </tbody>
          </table>
          <div style="margin-top: 15px; text-align: right;">
            <button id="closeCompareModal" class="btn-secondary">关闭</button>
          </div>
        </div>
      `;
      
      // 添加到页面
      document.body.appendChild(modal);
      
      // 关闭按钮事件
      modal.querySelector('#closeCompareModal').addEventListener('click', () => {
        document.body.removeChild(modal);
      });
      
      // 点击弹窗外部关闭
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          document.body.removeChild(modal);
        }
      });
      
    } catch (e) {
      console.error('对比失败:', e);
      if (analysisResults) {
        renderError('对比失败: ' + (e.message || '未知错误'));
      } else {
        alert('对比失败: ' + (e.message || '未知错误'));
      }
    }
  }

  // 图表收藏按钮（按图表类型 + 当前区域）
  function initChartFavoriteButtons() {
    document.querySelectorAll('.fav-chart-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!getToken()) {
          alert('请先登录后再收藏图表');
          return;
        }

        const chartType = btn.getAttribute('data-chart');
        const area = areaSelect?.value || state.area || '广州';

        // 查询当前收藏列表，判断是否已收藏
        try {
          const favorites = await fetchJson('/api/users/favorites');
          const existing = (favorites || []).find(f => f.chart_type === chartType && f.area === area);

          if (existing) {
            // 已收藏则取消
            await fetchJson(`/api/users/favorites/${existing.id}`, { method: 'DELETE' });
            btn.classList.remove('active');
          } else {
            // 未收藏则添加
            await fetchJson('/api/users/favorites', {
              method: 'POST',
              json: { chart_type: chartType, area },
            });
            btn.classList.add('active');
          }

          // 刷新收藏面板
          refreshUserPanel();
        } catch (e) {
          alert('收藏操作失败：' + (e.message || ''));
        }
      });
    });
  }

  // 初始化一次
  initChartFavoriteButtons();

  // 默认加载一次图表
  fetchAllCharts();

  // 浏览器窗口大小变化时，ECharts 必须 resize 才能自适应
  window.addEventListener('resize', () => {
    Object.values(charts).forEach(chart => chart.resize());
    Object.values(advancedCharts).forEach(c => c && c.resize && c.resize());
  });
});
