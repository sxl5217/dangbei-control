// 全局状态变量
let volume = 2;
let volumeMin = 0;
let volumeMax = 15;
let deviceIp = null;
let isConnected = false;
let isErrorShowing = false;
let isScanSuccessShowing = false;
let errorTimeoutId = null;
let isDraggingVolume = false;
let pollInterval = null;
let isFirstVolumeRender = true;

// ========== DOM元素 ==========
const topBar = document.getElementById('topBar');
const topBarText = document.getElementById('topBarText');
const topBarIcon = document.getElementById('topBarIcon');
const scanToast = document.getElementById('scanToast');
const deviceModal = document.getElementById('deviceModal');
const closeModalBtn = document.getElementById('closeModalBtn');
const volumeFill = document.getElementById('volumeFill');
const volumeSlider = document.getElementById('volumeSlider');
const offlineDialog = document.getElementById('offlineDialog');
const offlineCancel = document.getElementById('offlineCancel');
const offlineRetry = document.getElementById('offlineRetry');
const popupDeviceName = document.getElementById('popupDeviceName');
const popupStatusDot = document.getElementById('popupStatusDot');
const popupStatusText = document.getElementById('popupStatusText');
const popupDeviceIp = document.getElementById('popupDeviceIp');
const deviceListContainer = document.getElementById('deviceListContainer');

let isDeviceModalOpen = false;
let isOfflineDialogOpen = false;
let pendingKey = null;

// ========== 长按相关 ==========
const longPressKeys = ['up', 'down', 'left', 'right', 'volumeup', 'volumedown'];
let longPressTimer = null;
let repeatTimer = null;
let isLongPressing = false;
let currentPressKey = null;
let hasSentOnRelease = false;
let activeButton = null;

// ========== Toast提示 ==========
function showToast(message, duration = 1500) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, duration);
}

// ========== 更新音量显示 (0-15格) ==========
function updateVolumeDisplay() {
  const clampedVolume = Math.max(volumeMin, Math.min(volumeMax, volume));
  const percentage = volumeMax > 0 ? (clampedVolume / volumeMax) * 100 : 0;

  if (volumeSlider) {
    volumeSlider.value = clampedVolume;
  }

  if (isFirstVolumeRender) {
    // 首次渲染：临时关闭过渡动画，直接跳到目标值
    volumeFill.style.transition = 'none';
    volumeFill.style.width = `${percentage}%`;
    // 强制浏览器重排
    void volumeFill.offsetWidth;
    // 恢复过渡动画
    volumeFill.style.transition = '';
    isFirstVolumeRender = false;
  } else {
    // 非首次渲染：正常更新，带过渡动画
    volumeFill.style.width = `${percentage}%`;
  }
}

// ========== 更新连接状态显示 ==========
function updateConnectionStatus(connected) {
  if (isErrorShowing || isScanSuccessShowing) return;

  isConnected = connected;
  if (connected) {
    topBar.className = 'top-bar';
    topBarIcon.classList.add('hidden');
    topBarText.textContent = '设备已连接，点击查看';
  } else {
    topBar.className = 'top-bar';
    topBarIcon.classList.add('hidden');
    topBarText.textContent = '设备未连接，点击查看';
  }
}

// ========== 更新设备浮层状态 ==========
function updatePopupStatus(connected, ip) {
  if (connected) {
    popupStatusDot.classList.add('online');
    popupStatusText.classList.add('online');
    popupStatusText.textContent = '在线';
  } else {
    popupStatusDot.classList.remove('online');
    popupStatusText.classList.remove('online');
    popupStatusText.textContent = '离线';
  }
  popupDeviceIp.textContent = ip || '--';
}

// ========== 渲染设备列表 ==========
function renderDeviceList(connected, ip) {
  if (!deviceListContainer) return;

  const deviceName = '当贝投影';
  const displayIp = ip ? `${ip}:6689` : '--';
  const statusText = connected ? '已连接' : '未连接';

  deviceListContainer.innerHTML = `
    <div class="device-card">
      <div class="device-icon">
        <svg width="42" height="30" viewBox="0 0 40 28" fill="none">
          <rect x="2" y="6" width="36" height="18" rx="2" fill="#f3f4f6" stroke="#e5e7eb" stroke-width="1.5"/>
          <circle cx="28" cy="15" r="5" fill="#374151"/>
          <rect x="6" y="11" width="10" height="2" rx="1" fill="#4b5563"/>
          <rect x="6" y="21" width="28" height="3" fill="#374151"/>
        </svg>
      </div>
      <div class="device-info">
        <div class="device-name">${deviceName}</div>
        <div class="device-ip">${displayIp}</div>
      </div>
      <div class="device-status">${statusText}</div>
    </div>
  `;
}

// ========== 打开设备浮层 (Bottom Sheet) ==========
function openDeviceModal(showSuccessGreen = false) {
  if (isDeviceModalOpen || isOfflineDialogOpen) return;

  // 如果正在显示错误提示，先取消它
  if (isErrorShowing) {
    isErrorShowing = false;
    if (errorTimeoutId) {
      clearTimeout(errorTimeoutId);
      errorTimeoutId = null;
    }
  }

  isDeviceModalOpen = true;
  deviceModal.classList.add('show');
  if (showSuccessGreen) {
    isScanSuccessShowing = true;
    topBar.className = 'top-bar green';
    topBarText.textContent = '设备连接成功';
  } else {
    topBar.className = 'top-bar';
    topBarText.textContent = '设备已连接，点击查看';
  }
  renderDeviceList(isConnected, deviceIp);
  fetchStatus();
}

// ========== 关闭设备浮层 ==========
function closeDeviceModal() {
  if (!isDeviceModalOpen) return;
  isDeviceModalOpen = false;
  isScanSuccessShowing = false;
  deviceModal.classList.remove('show');
  resetTopBar();
}

// ========== 重置顶部栏 ==========
function resetTopBar() {
  if (isConnected) {
    topBar.className = 'top-bar';
    topBarIcon.classList.add('hidden');
    topBarText.textContent = '设备已连接，点击查看';
  } else {
    topBar.className = 'top-bar';
    topBarIcon.classList.add('hidden');
    topBarText.textContent = '设备未连接，点击查看';
  }
}

// ========== 显示错误提示 ==========
function showErrorBar() {
  isErrorShowing = true;

  topBar.className = 'top-bar green';
  topBarIcon.classList.remove('hidden');
  topBarText.textContent = '请将设备连接在同一个局域网内';

  if (errorTimeoutId) {
    clearTimeout(errorTimeoutId);
  }
  errorTimeoutId = setTimeout(() => {
    isErrorShowing = false;
    errorTimeoutId = null;
    if (!isConnected) {
      resetTopBar();
    }
  }, 2500);
}

// ========== 显示扫描中 ==========
function showScanToast() {
  scanToast.classList.add('show');
}

function hideScanToast() {
  scanToast.classList.remove('show');
}

// ========== 打开离线确认框 ==========
function openOfflineDialog(key) {
  if (isOfflineDialogOpen) return;
  isOfflineDialogOpen = true;
  pendingKey = key;
  offlineDialog.classList.add('show');
}

// ========== 关闭离线确认框 ==========
function closeOfflineDialog() {
  isOfflineDialogOpen = false;
  pendingKey = null;
  offlineDialog.classList.remove('show');
}

// ========== 停止长按 ==========
function stopLongPress() {
  if (longPressTimer) {
    clearTimeout(longPressTimer);
    longPressTimer = null;
  }
  if (repeatTimer) {
    clearInterval(repeatTimer);
    repeatTimer = null;
  }
  isLongPressing = false;
  currentPressKey = null;
  activeButton = null;
}

// ========== 获取状态 ==========
async function fetchStatus() {
  try {
    const response = await fetch('/api/status');
    const data = await response.json();

    // 只有不在拖拽时，才根据后端状态更新音量
    if (data.volume !== undefined && !isDraggingVolume) {
      volume = data.volume;
    }
    if (data.volumeMin !== undefined) {
      volumeMin = data.volumeMin;
    }
    if (data.volumeMax !== undefined) {
      volumeMax = data.volumeMax;
    }
    if (data.deviceIp !== undefined) {
      deviceIp = data.deviceIp;
    }

    // 只有不在拖拽时，才更新音量显示
    if (!isDraggingVolume) {
      updateVolumeDisplay();
    }
    updateConnectionStatus(data.connected);
    updatePopupStatus(data.connected, deviceIp);
    if (isDeviceModalOpen) {
      renderDeviceList(data.connected, deviceIp);
    }
  } catch (e) {
    console.error('获取状态失败:', e);
    updateConnectionStatus(false);
    updatePopupStatus(false, null);
  } finally {
    document.querySelectorAll('.app-loading').forEach(el => {
      el.classList.remove('app-loading');
    });
  }
}

// ========== 发送按键 ==========
async function sendKey(key, isRepeat = false, updateState = true) {
  if (isDeviceModalOpen || isOfflineDialogOpen) return;

  try {
    const response = await fetch('/api/key', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ key: key }),
    });

    const data = await response.json();

    if (!data.success) {
      stopLongPress();
      if (data.error === 'device_offline' || data.state === 'offline') {
        openOfflineDialog(key);
        return;
      }
      if (!isRepeat) {
        showToast(data.error || '操作失败');
      }
      await fetchStatus();
      return;
    }

    // 只有在 updateState 为 true 时，才修改内部变量和 UI
    if (updateState) {
      if (key === 'volumeup') {
        volume = Math.min(volumeMax, volume + 1);
        updateVolumeDisplay();
        if (volumeSlider) {
          volumeSlider.value = volume;
        }
      } else if (key === 'volumedown') {
        volume = Math.max(volumeMin, volume - 1);
        updateVolumeDisplay();
        if (volumeSlider) {
          volumeSlider.value = volume;
        }
      }
    }
  } catch (e) {
    stopLongPress();
    console.error('发送按键失败:', e);
    if (!isRepeat) {
      showToast('连接失败');
    }
    await fetchStatus();
  }
}

// ========== 检查是否在同一个按钮上 ==========
function isSameButton(target) {
  if (!target || !activeButton) return false;
  return target === activeButton || activeButton.contains(target);
}

// ========== 处理按下事件 ==========
function handlePressStart(e, button, key) {
  if (isDeviceModalOpen || isOfflineDialogOpen) return;

  activeButton = button;
  currentPressKey = key;
  isLongPressing = false;
  hasSentOnRelease = false;

  if (longPressKeys.includes(key)) {
    longPressTimer = setTimeout(() => {
      isLongPressing = true;
      sendKey(key, false);
      repeatTimer = setInterval(() => {
        if (currentPressKey) {
          sendKey(currentPressKey, true);
        }
      }, 100);
    }, 500);
  }
}

// ========== 处理释放事件 ==========
function handlePressEnd(e, button, key) {
  const needsSend = !isLongPressing && key && !hasSentOnRelease && isSameButton(e.target);

  stopLongPress();

  if (needsSend) {
    hasSentOnRelease = true;
    sendKey(key, false);
  }
}

// ========== 触发扫描 (真实扫描) ==========
async function triggerScan() {
  try {
    showScanToast();
    const response = await fetch('/api/scan', {
      method: 'POST',
    });
    const data = await response.json();
    hideScanToast();

    if (data.found) {
      isConnected = true;
      showToast('设备已连接');
      // 打开弹窗并显示绿色"设备连接成功"
      openDeviceModal(true);
      if (pendingKey) {
        const key = pendingKey;
        pendingKey = null;
        setTimeout(() => sendKey(key), 300);
      }
    } else {
      isConnected = false;
      showErrorBar();
      await fetchStatus();
    }
  } catch (e) {
    hideScanToast();
    console.error('扫描失败:', e);
    showToast('扫描失败');
  }
}

// ========== 初始化事件监听 ==========
function initEventListeners() {
  const buttons = document.querySelectorAll('[data-key]');
  buttons.forEach(button => {
    const key = button.getAttribute('data-key');

    button.addEventListener('touchstart', (e) => {
      e.preventDefault();
      e.stopPropagation();
      handlePressStart(e, button, key);
    }, { passive: false });

    button.addEventListener('touchend', (e) => {
      e.preventDefault();
      e.stopPropagation();
      handlePressEnd(e, button, key);
    }, { passive: false });

    button.addEventListener('touchmove', (e) => {
      const touch = e.touches[0];
      const target = document.elementFromPoint(touch.clientX, touch.clientY);
      if (!isSameButton(target)) {
        stopLongPress();
      }
    }, { passive: false });

    button.addEventListener('touchcancel', (e) => {
      e.preventDefault();
      e.stopPropagation();
      stopLongPress();
    }, { passive: false });

    button.addEventListener('mousedown', (e) => {
      e.preventDefault();
      handlePressStart(e, button, key);
    });

    button.addEventListener('mouseup', (e) => {
      e.preventDefault();
      handlePressEnd(e, button, key);
    });

    button.addEventListener('mouseleave', (e) => {
      e.preventDefault();
      stopLongPress();
    });
  });

  // ========== 顶部栏点击 - 关键修复 ==========
  topBar.addEventListener('click', () => {
    if (isConnected) {
      // 已连接时点击，打开设备列表
      openDeviceModal();
    } else {
      // 未连接时点击，开始扫描
      triggerScan();
    }
  });

  closeModalBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    closeDeviceModal();
  });

  deviceModal.addEventListener('click', (e) => {
    if (e.target === deviceModal) {
      closeDeviceModal();
    }
  });

  offlineCancel.addEventListener('click', () => {
    closeOfflineDialog();
  });

  offlineRetry.addEventListener('click', async () => {
    closeOfflineDialog();
    await triggerScan();
  });

  if (volumeSlider) {
    volumeSlider.addEventListener('mousedown', () => isDraggingVolume = true);
    volumeSlider.addEventListener('touchstart', () => isDraggingVolume = true);

    volumeSlider.addEventListener('input', (e) => {
      const tempVolume = parseInt(e.target.value);
      const percentage = volumeMax > 0 ? (tempVolume / volumeMax) * 100 : 0;
      volumeFill.style.width = `${percentage}%`;
    });

    volumeSlider.addEventListener('change', async (e) => {
      const targetVolume = parseInt(e.target.value);
      const diff = targetVolume - volume;

      if (diff === 0) {
        // 没有变化，确保UI和真实状态一致
        updateVolumeDisplay();
        isDraggingVolume = false;
        return;
      }

      // 1. 提前把真实的 volume 变量更新为目标值，锁定 UI 不变
      volume = targetVolume;
      updateVolumeDisplay(); // 这里会自动更新 volumeSlider.value 和 volumeFill 的宽度

      const keyCmd = diff > 0 ? 'volumeup' : 'volumedown';
      const steps = Math.abs(diff);

      // 循环发送请求
      for (let i = 0; i < steps; i++) {
        if (isOfflineDialogOpen) {
          break;
        }

        await sendKey(keyCmd, false, false);
        await new Promise(r => setTimeout(r, 100));
      }

      await fetchStatus();

      // 所有操作完成后释放拖拽锁
      isDraggingVolume = false;
    });
  }
}

// ========== 页面可见性 API 轮询控制 ==========
function startPolling() {
  if (!pollInterval) {
    // 每5秒轮询一次状态，同步多端状态
    pollInterval = setInterval(fetchStatus, 5000);
  }
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

function init() {
  initEventListeners();
  fetchStatus();
  startPolling();

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopPolling();
    } else {
      fetchStatus();
      startPolling();
    }
  });
}

document.addEventListener('DOMContentLoaded', init);
