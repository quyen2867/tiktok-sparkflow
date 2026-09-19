(() => {
  const root = document.documentElement;
  const storageKey = "sparkflow-theme";

  const storedTheme = () => {
    try {
      return localStorage.getItem(storageKey);
    } catch {
      return null;
    }
  };

  const applyTheme = (theme) => {
    const value = theme === "light" ? "light" : "dark";
    root.dataset.theme = value;
    root.style.colorScheme = value;
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // The active page can still switch themes when storage is unavailable.
    }
  };

  applyTheme(storedTheme() || "dark");
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      applyTheme(root.dataset.theme === "light" ? "dark" : "light");
    });
  });
})();

(() => {
  const body = document.body;
  document.querySelectorAll("[data-nav-toggle]").forEach((button) => {
    button.addEventListener("click", () => body.classList.add("nav-open"));
  });
  document.querySelectorAll("[data-nav-close]").forEach((button) => {
    button.addEventListener("click", () => body.classList.remove("nav-open"));
  });
  document.querySelectorAll(".nav-item").forEach((link) => {
    link.addEventListener("click", () => body.classList.remove("nav-open"));
  });
})();

(() => {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog) return;
  const title = document.getElementById("confirm-title");
  const message = document.getElementById("confirm-message");
  const accept = dialog.querySelector("[data-confirm-accept]");
  const cancel = dialog.querySelector("[data-confirm-cancel]");
  let pendingForm = null;
  let pendingLink = "";
  let pendingButton = null;

  const openDialog = (node) => {
    const source = node.closest("[data-confirm]") || node;
    title.textContent = source.dataset.confirmTitle || "Xác nhận thao tác";
    message.textContent =
      source.dataset.confirm ||
      "Thao tác này sẽ thay đổi tác vụ gửi tin. Bạn có muốn tiếp tục không?";
    accept.textContent = source.dataset.confirmAccept || "Xác nhận";
    accept.className =
      source.dataset.confirmTone === "primary"
        ? "button button-primary"
        : "button button-danger";
    dialog.showModal();
  };

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      pendingForm = form;
      pendingLink = "";
      pendingButton = null;
      openDialog(form);
    });
  });

  document.querySelectorAll("a[data-confirm]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      pendingForm = null;
      pendingLink = link.href;
      pendingButton = null;
      openDialog(link);
    });
  });

  document.querySelectorAll("button[data-confirm]").forEach((button) => {
    button.addEventListener(
      "click",
      (event) => {
        if (button.dataset.confirmApproved === "1") {
          delete button.dataset.confirmApproved;
          return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        pendingForm = null;
        pendingLink = "";
        pendingButton = button;
        openDialog(button);
      },
      true,
    );
  });

  cancel.addEventListener("click", () => {
    pendingForm = null;
    pendingLink = "";
    pendingButton = null;
    dialog.close();
  });

  accept.addEventListener("click", () => {
    const form = pendingForm;
    const href = pendingLink;
    const button = pendingButton;
    pendingForm = null;
    pendingLink = "";
    pendingButton = null;
    dialog.close();
    if (form) {
      HTMLFormElement.prototype.submit.call(form);
    } else if (href) {
      window.location.assign(href);
    } else if (button) {
      button.dataset.confirmApproved = "1";
      button.click();
    }
  });

  dialog.addEventListener("cancel", () => {
    pendingForm = null;
    pendingLink = "";
    pendingButton = null;
  });
})();

(() => {
  document.querySelectorAll("[data-segment-group]").forEach((group) => {
    const buttons = [...group.querySelectorAll("[data-segment-target]")];
    const owner = group.closest("[data-segment-owner]") || document;
    const panels = [...owner.querySelectorAll("[data-segment-panel]")];
    const activate = (name) => {
      buttons.forEach((button) => {
        const active = button.dataset.segmentTarget === name;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.segmentPanel !== name;
      });
    };
    buttons.forEach((button) => {
      button.addEventListener("click", () =>
        activate(button.dataset.segmentTarget),
      );
    });
    const initial =
      buttons.find((button) => button.classList.contains("active")) ||
      buttons[0];
    if (initial) activate(initial.dataset.segmentTarget);
  });
})();

(() => {
  const overviewRoots = document.querySelectorAll("[data-overview-root]");
  if (!overviewRoots.length) return;
  let previousRunning = null;
  let timer = null;

  const formatTime = (raw) => {
    if (!raw) return "-";
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;
    return new Intl.DateTimeFormat("vi-VN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(parsed);
  };

  const setText = (selector, value) => {
    document.querySelectorAll(selector).forEach((node) => {
      node.textContent = String(value ?? "");
    });
  };

  const updateTaskBanner = (task) => {
    document.querySelectorAll("[data-task-banner]").forEach((banner) => {
      banner.className = "status-banner";
      if (task.running) {
        banner.classList.add("warning");
        banner.querySelector("[data-task-text]").textContent =
          `Đang gửi tin, đã chạy khoảng ${task.ageSeconds || 0} giây`;
      } else if (task.stale) {
        banner.classList.add("info");
        banner.querySelector("[data-task-text]").textContent =
          "Phát hiện khóa tác vụ cũ; hệ thống sẽ kiểm tra lại ở lần chạy tiếp theo";
      } else {
        banner.classList.add("success");
        banner.querySelector("[data-task-text]").textContent =
          "Hiện không có lượt gửi đang chạy";
      }
    });
  };

  const updateAccounts = (accounts) => {
    accounts.forEach((account) => {
      const selector = `[data-account-overview="${CSS.escape(account.uniqueId)}"]`;
      document.querySelectorAll(selector).forEach((row) => {
        row.dataset.accountState = account.state;
        row.querySelectorAll("[data-account-confirmed]").forEach((node) => {
          node.textContent = account.confirmed;
        });
        row.querySelectorAll("[data-account-attention]").forEach((node) => {
          node.textContent = account.attention;
        });
        row.querySelectorAll("[data-account-pending]").forEach((node) => {
          node.textContent = account.pending;
        });
        row.querySelectorAll("[data-account-progress]").forEach((node) => {
          const pct = account.total
            ? Math.round((account.confirmed / account.total) * 100)
            : 0;
          node.style.width = `${pct}%`;
        });
        row.querySelectorAll("[data-account-progress-text]").forEach((node) => {
          node.textContent = `${account.confirmed}/${account.total}`;
        });
      });
    });
  };

  const updateActions = (summary, running) => {
    const counts = {
      attention: summary.attention,
      pending: summary.pending + summary.unprocessed,
      total: summary.total,
    };
    document.querySelectorAll("[data-action-count-source]").forEach((button) => {
      const count = counts[button.dataset.actionCountSource] || 0;
      button.disabled = running || count <= 0;
      const countNode = button.querySelector("[data-action-count]");
      if (countNode) countNode.textContent = count;
    });
    document.querySelectorAll("[data-disable-while-running]").forEach((button) => {
      if (!button.dataset.actionCountSource) {
        button.disabled = running;
      }
    });
  };

  const render = (data) => {
    const summary = data.summary || {};
    const task = data.task || {};
    updateTaskBanner(task);
    setText("[data-overview-value='total']", summary.total || 0);
    setText("[data-overview-value='confirmed']", summary.confirmed || 0);
    setText("[data-overview-value='attention']", summary.attention || 0);
    setText(
      "[data-overview-value='pending']",
      (summary.pending || 0) + (summary.unprocessed || 0),
    );
    setText("[data-overview-value='remaining']", summary.remaining || 0);
    setText(
      "[data-overview-value='progress']",
      `${summary.confirmed || 0}/${summary.total || 0}`,
    );
    setText(
      "[data-overview-value='progressPercent']",
      summary.total
        ? `${Math.round((summary.confirmed / summary.total) * 100)}%`
        : "0%",
    );
    setText(
      "[data-overview-value='lastConfirmedAt']",
      formatTime(summary.lastConfirmedAt),
    );
    setText(
      "[data-overview-value='nextTriggerAt']",
      formatTime(data.schedule?.nextTriggerAt),
    );
    setText(
      "[data-overview-value='scheduleLabel']",
      data.schedule?.label || "-",
    );
    updateAccounts(data.accounts || []);
    updateActions(summary, Boolean(task.running));

    if (previousRunning === true && !task.running) {
      document
        .querySelectorAll("[data-refresh-notice]")
        .forEach((node) => node.classList.add("visible"));
    }
    previousRunning = Boolean(task.running);
    document.querySelectorAll("[data-overview-live-state]").forEach((node) => {
      node.textContent = "Trực tiếp";
      node.classList.remove("poll-stale");
    });
  };

  const refresh = async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const response = await fetch("/api/ops/overview", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch {
      document.querySelectorAll("[data-overview-live-state]").forEach((node) => {
        node.textContent = "Cập nhật chậm";
        node.classList.add("poll-stale");
      });
    }
  };

  document.querySelectorAll("[data-refresh-page]").forEach((button) => {
    button.addEventListener("click", () => window.location.reload());
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  refresh();
  timer = window.setInterval(refresh, 10000);
  window.addEventListener("pagehide", () => window.clearInterval(timer));
})();

(() => {
  const root = document.getElementById("login-desktop-controls");
  if (!root) return;
  const section = document.getElementById("interactive-login-section");
  const csrfToken = root.dataset.csrfToken || "";
  const displayMode = root.dataset.displayMode || "novnc";
  const configuredPublicUrl = root.dataset.publicUrl || "";
  const publicUrl = (() => {
    if (!configuredPublicUrl) return "";
    try {
      return new URL(configuredPublicUrl, window.location.href).href;
    } catch {
      return configuredPublicUrl;
    }
  })();
  const runtimeState = document.getElementById("login-desktop-runtime-state");
  const statusText = document.getElementById("login-desktop-status-text");
  const frame = document.querySelector("[data-login-frame]");
  const frameWrap = document.querySelector(".desktop-frame-wrap");
  const nativePanel = document.querySelector("[data-native-login]");
  const copyLoginUrlButton = document.querySelector("[data-copy-login-url]");
  const qrImage = document.querySelector("[data-login-qr]");
  const qrStatus = document.querySelector("[data-login-qr-status]");
  let timer = null;
  let heartbeatTimer = null;
  let countdownTimer = null;
  let qrRefreshTimer = null;
  let workspace = { state: "closed", active: false, position: 0, ticket: "" };
  if (displayMode === "native" && copyLoginUrlButton) copyLoginUrlButton.hidden = true;
  if (displayMode === "native" && frameWrap) frameWrap.hidden = true;

  const setStatus = (text, tone = "") => {
    if (statusText) statusText.textContent = text;
    if (runtimeState) {
      runtimeState.className = `pill${tone ? ` ${tone}` : ""}`;
      runtimeState.textContent = tone === "success" ? "Đang sử dụng" : tone === "danger" ? "Cần xử lý" : tone === "warning" ? "Đang chờ lượt" : "Đã đóng";
    }
  };

  const postForm = async (url, payload = {}) => {
    const formData = new FormData();
    formData.set("csrf_token", csrfToken);
    Object.entries(payload).forEach(([key, value]) => formData.set(key, String(value ?? "")));
    const response = await fetch(url, { method: "POST", body: formData, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `Yêu cầu không thành công: ${response.status}`);
    return data;
  };

  const loadFrame = (force = false) => {
    if (displayMode === "native") return;
    if (frame && (force || frame.dataset.loaded !== "1") && frame.dataset.src) {
      frame.src = frame.dataset.src;
      frame.dataset.loaded = "1";
    }
  };

  const closeFrame = () => {
    if (nativePanel) nativePanel.hidden = true;
    if (frameWrap) {
      frameWrap.classList.remove("native-login-mode");
      if (displayMode === "native") frameWrap.hidden = true;
    }
    if (qrImage) {
      qrImage.hidden = true;
      const previous = qrImage.dataset.objectUrl || "";
      if (previous) URL.revokeObjectURL(previous);
      delete qrImage.dataset.objectUrl;
      qrImage.removeAttribute("src");
    }
    if (!frame) return;
    frame.removeAttribute("src");
    frame.dataset.loaded = "0";
  };

  const renderWorkspace = (next) => {
    workspace = next || { state: "closed", active: false, position: 0, ticket: "" };
    if (workspace.state === "queued") {
      setStatus(`Đang chờ cửa sổ đăng nhập; còn ${Math.max(0, Number(workspace.position || 1) - 1)} người trước bạn.`, "warning");
      if (qrStatus) qrStatus.textContent = "Đã vào hàng chờ. Cửa sổ đăng nhập sẽ mở khi đến lượt bạn.";
      return;
    }
    if (workspace.state === "resetting") {
      setStatus("Đang đóng phiên đăng nhập của người dùng trước. Vui lòng chờ.", "warning");
      return;
    }
    if (workspace.state === "active" && workspace.active) {
      const remaining = Math.max(0, Number(workspace.remaining_seconds || 0));
      const tone = remaining > 0 && remaining <= 60 ? "warning" : "success";
      if (displayMode === "native") {
        if (nativePanel) nativePanel.hidden = false;
        if (frameWrap) {
          frameWrap.hidden = false;
          frameWrap.classList.add("native-login-mode");
        }
        setStatus(`Đã mở trình duyệt đăng nhập trên máy Mac; còn ${remaining} giây. Đăng nhập xong, hãy lưu phiên.`, tone);
      } else {
        setStatus(`Đến lượt bạn đăng nhập; còn ${remaining} giây. Đăng nhập xong, hãy lưu phiên.`, tone);
      }
      return;
    }
    setStatus("Cửa sổ đăng nhập đang đóng. Bấm “Đăng nhập lại” tại tài khoản cần xử lý.");
  };

  const refreshLoginQr = async (delay = 0, retries = 40) => {
    if (!qrImage || workspace.state !== "active" || !workspace.active) return;
    window.clearTimeout(qrRefreshTimer);
    qrRefreshTimer = window.setTimeout(async () => {
      if (qrStatus) qrStatus.textContent = "Đang đọc mã QR đăng nhập...";
      try {
        const response = await fetch(`/login-desktop/qr?t=${Date.now()}`, { credentials: "same-origin", cache: "no-store" });
        if (response.status === 202) {
          if (retries > 1 && workspace.state === "active") {
            if (qrStatus) qrStatus.textContent = "Trình duyệt đang tạo mã QR, vui lòng chờ...";
            refreshLoginQr(1400, retries - 1);
          } else if (qrStatus) {
            qrStatus.textContent = "Trang đăng nhập chưa tạo được mã QR. Vui lòng thử lại sau.";
          }
          return;
        }
        if (response.status === 409) {
          if (qrStatus) qrStatus.textContent = "Mã QR đã hết hạn. Hãy cập nhật mã mới.";
          return;
        }
        if (response.status === 502) {
          const data = await response.json().catch(() => ({}));
          if (qrStatus) qrStatus.textContent = data.error || "Không truy cập được TikTok. Hãy kiểm tra kết nối mạng.";
          return;
        }
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        const previous = qrImage.dataset.objectUrl || "";
        const objectUrl = URL.createObjectURL(blob);
        qrImage.src = objectUrl;
        qrImage.dataset.objectUrl = objectUrl;
        qrImage.hidden = false;
        if (previous) URL.revokeObjectURL(previous);
        if (qrStatus) qrStatus.textContent = "Đã tải mã QR. Nếu mã hết hạn, hãy cập nhật mã mới.";
      } catch {
        if (retries > 1 && workspace.state === "active") {
          if (qrStatus) qrStatus.textContent = "Đang tải trang đăng nhập, vui lòng chờ mã QR...";
          refreshLoginQr(1400, retries - 1);
        } else if (qrStatus) {
          qrStatus.textContent = "Mã QR chưa sẵn sàng. Hãy kiểm tra xem đã đến lượt bạn đăng nhập chưa.";
        }
      }
    }, delay);
  };

  const pollStatus = async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const statusUrl = workspace.state === "active" ? "/login-desktop/status" : "/login-desktop/workspace-status";
      const response = await fetch(statusUrl, { credentials: "same-origin", cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.ok === false) {
        setStatus(data.error || "Không mở được cửa sổ đăng nhập. Hãy kiểm tra dịch vụ đăng nhập trên máy Mac.", "danger");
        return;
      }
      renderWorkspace(data.workspace);
      if (workspace.state === "active" && workspace.active) {
        loadFrame();
        if (data.logged_in) setStatus(`Trình duyệt đã đăng nhập tài khoản ${data.username}. Hãy lưu phiên đăng nhập.`, "success");
      } else {
        closeFrame();
      }
    } catch (error) {
      setStatus(`Không kiểm tra được trạng thái: ${error.message}`, "danger");
    }
  };

  const heartbeat = async () => {
    if (workspace.state !== "active" || !workspace.active || !workspace.ticket) return;
    try {
      const data = await postForm("/login-desktop/heartbeat", { ticket: workspace.ticket });
      renderWorkspace(data.workspace);
    } catch (error) {
      workspace = { state: "closed", active: false, position: 0, ticket: "" };
      closeFrame();
      setStatus(`Cửa sổ đăng nhập đã được giải phóng: ${error.message}`, "danger");
    }
  };

  document.querySelectorAll(".login-desktop-open").forEach((button) => {
    button.addEventListener("click", async () => {
      if (section) section.open = true;
      try {
        const reloginUniqueId = button.dataset.reloginUniqueId || "";
        const mode = button.dataset.loginMode || (reloginUniqueId ? "relogin" : "add");
        const data = await postForm("/login-desktop/open", {
          mode,
          ...(reloginUniqueId ? { relogin_unique_id: reloginUniqueId } : {}),
        });
        renderWorkspace(data.workspace);
        if (data.state === "queued") return;
        loadFrame(true);
        refreshLoginQr(500);
        if (frame) frame.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        setStatus(`Không thể yêu cầu cửa sổ đăng nhập: ${error.message}`, "danger");
      }
    });
  });

  document.querySelectorAll("[data-focus-native-browser]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await postForm("/login-desktop/focus", { ticket: workspace.ticket });
        setStatus("Đã yêu cầu hiện trình duyệt đăng nhập. Hãy tiếp tục trong cửa sổ trên máy Mac.", "success");
      } catch (error) {
        setStatus(`Không hiện được trình duyệt đăng nhập: ${error.message}`, "danger");
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll("[data-refresh-login-qr]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await postForm("/login-desktop/qr/refresh", { ticket: workspace.ticket });
        refreshLoginQr(500);
      } catch (error) {
        if (qrStatus) qrStatus.textContent = `Không cập nhật được mã QR: ${error.message}`;
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll(".login-desktop-save").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await postForm("/login-desktop/save", { relogin_unique_id: button.dataset.reloginUniqueId || "" });
        renderWorkspace(data.workspace);
        setStatus(`Đã lưu phiên đăng nhập cho tài khoản: ${data.account?.username || ""}`, "success");
        closeFrame();
        window.setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        setStatus(`Không lưu được phiên đăng nhập: ${error.message}`, "danger");
      }
    });
  });

  document.querySelectorAll(".login-desktop-close").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await postForm("/login-desktop/close");
        renderWorkspace(data.workspace);
        closeFrame();
        if (qrImage) qrImage.hidden = true;
      } catch (error) {
        setStatus(`Không đóng được cửa sổ đăng nhập: ${error.message}`, "danger");
      }
    });
  });

  document.querySelectorAll(".login-desktop-reset").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await postForm("/login-desktop/reset");
        renderWorkspace(data.workspace);
        closeFrame();
        if (qrImage) qrImage.hidden = true;
      } catch (error) {
        setStatus(`Không kết thúc được phiên đăng nhập: ${error.message}`, "danger");
      }
    });
  });

  document.querySelectorAll("[data-copy-login-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(publicUrl);
        setStatus("Đã sao chép địa chỉ cửa sổ đăng nhập.", "success");
      } catch (error) {
        setStatus(`Không sao chép được: ${error.message}`, "danger");
      }
    });
  });

  if (section) section.addEventListener("toggle", () => { if (section.open) pollStatus(); });
  pollStatus();
  timer = window.setInterval(pollStatus, 5000);
  heartbeatTimer = window.setInterval(heartbeat, 5000);
  countdownTimer = window.setInterval(() => {
    if (workspace.state !== "active" || !workspace.active) return;
    workspace.remaining_seconds = Math.max(0, Number(workspace.remaining_seconds || 0) - 1);
    const remaining = workspace.remaining_seconds;
    setStatus(`Đến lượt bạn đăng nhập; còn ${remaining} giây. Đăng nhập xong, hãy lưu phiên.`, remaining <= 60 ? "warning" : "success");
  }, 1000);
  window.addEventListener("pagehide", () => {
    window.clearInterval(timer);
    window.clearInterval(heartbeatTimer);
    window.clearInterval(countdownTimer);
  });
})();

(() => {
  const parseJson = (id) => {
    const node = document.getElementById(id);
    if (!node) return [];
    try {
      return JSON.parse(node.textContent || "[]");
    } catch {
      return [];
    }
  };

  document.querySelectorAll(".friend-picker").forEach((picker) => {
    const accountId = picker.dataset.accountId;
    const refreshUrl = picker.dataset.refreshUrl;
    const csrfToken = picker.dataset.csrfToken;
    const form = picker.closest("form");
    const textarea = form?.querySelector(".targets-textarea");
    const search = picker.querySelector(".friend-search-input");
    const refreshButton = picker.querySelector(".friend-refresh-button");
    const list = picker.querySelector(".friend-picker-list");
    const summary = picker.querySelector(".friend-picker-summary");
    const status = picker.querySelector(".friend-picker-status");
    let friends = parseJson(`friends-cache-${accountId}`);
    let selected = new Set(parseJson(`selected-targets-${accountId}`));

    const parseTargets = (value) =>
      [...new Set(
        String(value || "")
          .replaceAll(",", "\n")
          .split(/\r?\n/)
          .map((item) => item.trim())
          .filter(Boolean),
      )];

    const combined = () => [...new Set([...selected, ...friends])];

    const syncTextarea = () => {
      if (textarea) textarea.value = [...selected].join("\n");
    };

    const render = () => {
      const query = String(search?.value || "").trim().toLowerCase();
      const names = combined().filter((name) =>
        name.toLowerCase().includes(query),
      );
      if (summary) summary.textContent = `Đã chọn ${selected.size} người`;
      list.innerHTML = "";
      if (!names.length) {
        const empty = document.createElement("div");
        empty.className = "friend-picker-empty";
        empty.textContent = combined().length
          ? "Không có cuộc trò chuyện phù hợp."
          : "Bấm “Đọc các chat hiện có” rồi chọn người nhận.";
        list.appendChild(empty);
        return;
      }
      names.forEach((name) => {
        const label = document.createElement("label");
        label.className = `friend-option${selected.has(name) ? " selected" : ""}`;
        const text = document.createElement("span");
        text.textContent = name;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = selected.has(name);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) selected.add(name);
          else selected.delete(name);
          syncTextarea();
          render();
        });
        label.append(text, checkbox);
        list.appendChild(label);
      });
    };

    textarea?.addEventListener("input", () => {
      selected = new Set(parseTargets(textarea.value));
      render();
    });
    search?.addEventListener("input", render);
    refreshButton?.addEventListener("click", async () => {
      refreshButton.disabled = true;
      if (status) status.textContent = "Đang đọc danh sách cuộc trò chuyện...";
      try {
        const formData = new FormData();
        formData.set("csrf_token", csrfToken);
        const response = await fetch(refreshUrl, {
          method: "POST",
          body: formData,
          credentials: "same-origin",
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Không thể cập nhật");
        friends = data.friends || [];
        if (status) status.textContent = data.message || "Đã cập nhật danh sách cuộc trò chuyện";
        render();
      } catch (error) {
        if (status) status.textContent = `Không thể cập nhật: ${error.message}`;
      } finally {
        refreshButton.disabled = false;
      }
    });
    render();
  });
})();

window.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons({ attrs: { "aria-hidden": "true" } });
  }
});
