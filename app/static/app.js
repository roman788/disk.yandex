const LOCAL_HEADER = { "X-Local-Yandex-Disk": "1" };

const el = {
  health: document.querySelector("#health"),
  accountLabel: document.querySelector("#accountLabel"),
  token: document.querySelector("#token"),
  addAccount: document.querySelector("#addAccount"),
  accounts: document.querySelector("#accounts"),
  checkToken: document.querySelector("#checkToken"),
  loadDiskInfo: document.querySelector("#loadDiskInfo"),
  file: document.querySelector("#file"),
  diskPath: document.querySelector("#diskPath"),
  overwrite: document.querySelector("#overwrite"),
  publishAfter: document.querySelector("#publishAfter"),
  upload: document.querySelector("#upload"),
  folderPath: document.querySelector("#folderPath"),
  createFolder: document.querySelector("#createFolder"),
  listFolder: document.querySelector("#listFolder"),
  metadata: document.querySelector("#metadata"),
  output: document.querySelector("#output"),
  history: document.querySelector("#history"),
};

function selectedAccountId() {
  return el.accounts.value;
}

function storageMode() {
  return document.querySelector("input[name='storage']:checked").value;
}

function uploadMode() {
  return document.querySelector("input[name='uploadMode']:checked").value;
}

function configureUploadPicker() {
  const folderMode = uploadMode() === "folder";
  el.file.value = "";
  el.file.multiple = folderMode;
  if (folderMode) {
    el.file.setAttribute("webkitdirectory", "");
    el.file.setAttribute("directory", "");
  } else {
    el.file.removeAttribute("webkitdirectory");
    el.file.removeAttribute("directory");
    el.file.multiple = false;
  }
}

function show(value) {
  el.output.textContent = JSON.stringify(value, null, 2);
}

function showError(error) {
  show({ error: error.message || String(error) });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.method && options.method !== "GET" ? LOCAL_HEADER : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(payload?.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function withBusy(button, action) {
  button.disabled = true;
  try {
    return await action();
  } finally {
    button.disabled = false;
  }
}

async function refreshAccounts() {
  const accounts = await api("/api/accounts");
  el.accounts.innerHTML = "";
  for (const account of accounts) {
    const option = document.createElement("option");
    option.value = account.id;
    option.textContent = `${account.label} (${account.token_storage})`;
    el.accounts.append(option);
  }
  if (!accounts.length) {
    const option = document.createElement("option");
    option.textContent = "Добавьте аккаунт";
    option.value = "";
    el.accounts.append(option);
  }
}

async function refreshHistory() {
  const entries = await api("/api/uploads?limit=12");
  el.history.innerHTML = "";
  if (!entries.length) {
    el.history.textContent = "История пока пустая.";
    return;
  }
  for (const item of entries) {
    const row = document.createElement("div");
    row.className = "history-item";
    const statusClass = item.status === "completed" ? "ok" : item.status === "failed" ? "bad" : "warn";
    row.innerHTML = `
      <strong>${escapeHtml(item.disk_path)}</strong>
      <span>${escapeHtml(item.local_filename)} · ${formatBytes(item.local_size)}</span>
      <span class="${statusClass}">${escapeHtml(item.status)}</span>
      ${item.public_url ? `<a href="${escapeAttribute(item.public_url)}" target="_blank" rel="noreferrer">Публичная ссылка</a>` : ""}
    `;
    el.history.append(row);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

el.addAccount.addEventListener("click", () =>
  withBusy(el.addAccount, async () => {
    const payload = await api("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: el.accountLabel.value,
        token: el.token.value,
        storage: storageMode(),
      }),
    });
    el.token.value = "";
    show(payload);
    await refreshAccounts();
  }).catch(showError),
);

el.checkToken.addEventListener("click", () =>
  withBusy(el.checkToken, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    show(await api(`/api/accounts/${id}/check`, { method: "POST" }));
  }).catch(showError),
);

el.loadDiskInfo.addEventListener("click", () =>
  withBusy(el.loadDiskInfo, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    show(await api(`/api/accounts/${id}/disk-info`));
  }).catch(showError),
);

el.upload.addEventListener("click", () =>
  withBusy(el.upload, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    if (!el.file.files.length) throw new Error(uploadMode() === "folder" ? "Выберите папку." : "Выберите файл.");
    const form = new FormData();
    form.append("disk_path", el.diskPath.value);
    form.append("overwrite", el.overwrite.checked ? "true" : "false");
    form.append("publish_after_upload", el.publishAfter.checked ? "true" : "false");
    if (uploadMode() === "folder") {
      for (const file of el.file.files) {
        form.append("files", file, file.webkitRelativePath || file.name);
      }
      show(await api(`/api/accounts/${id}/upload-folder`, {
        method: "POST",
        headers: LOCAL_HEADER,
        body: form,
      }));
    } else {
      form.append("file", el.file.files[0]);
      show(await api(`/api/accounts/${id}/upload`, {
        method: "POST",
        headers: LOCAL_HEADER,
        body: form,
      }));
    }
    await refreshHistory();
  }).catch(showError),
);

for (const modeInput of document.querySelectorAll("input[name='uploadMode']")) {
  modeInput.addEventListener("change", configureUploadPicker);
}

el.createFolder.addEventListener("click", () =>
  withBusy(el.createFolder, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    show(await api(`/api/accounts/${id}/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: el.folderPath.value }),
    }));
  }).catch(showError),
);

el.listFolder.addEventListener("click", () =>
  withBusy(el.listFolder, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    show(await api(`/api/accounts/${id}/list?path=${encodeURIComponent(el.folderPath.value)}`));
  }).catch(showError),
);

el.metadata.addEventListener("click", () =>
  withBusy(el.metadata, async () => {
    const id = selectedAccountId();
    if (!id) throw new Error("Выберите аккаунт.");
    show(await api(`/api/accounts/${id}/metadata?path=${encodeURIComponent(el.folderPath.value)}`));
  }).catch(showError),
);

async function boot() {
  try {
    const health = await api("/api/health");
    el.health.textContent = `127.0.0.1 · ${health.version}`;
    configureUploadPicker();
    await refreshAccounts();
    await refreshHistory();
  } catch (error) {
    el.health.textContent = "ошибка";
    showError(error);
  }
}

boot();
