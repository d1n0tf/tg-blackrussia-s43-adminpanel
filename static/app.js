"use strict";

(() => {
    let activeRequestController = null;

    const shouldHandleLink = (link, event) => {
        if (!link || event.defaultPrevented || event.button !== 0) {
            return false;
        }
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return false;
        }
        if (link.target && link.target !== "_self") {
            return false;
        }
        if (link.hasAttribute("download") || link.dataset.noLive !== undefined) {
            return false;
        }

        const rawHref = link.getAttribute("href");
        if (!rawHref || rawHref.startsWith("#")) {
            return false;
        }
        if (
            rawHref.startsWith("mailto:") ||
            rawHref.startsWith("tel:") ||
            rawHref.startsWith("javascript:")
        ) {
            return false;
        }

        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin) {
            return false;
        }
        if (url.pathname.startsWith("/attachments/")) {
            return false;
        }
        return true;
    };

    const shouldHandleForm = (form) => {
        if (!form || form.dataset.noLive !== undefined) {
            return false;
        }
        if (form.enctype === "multipart/form-data" || form.querySelector('input[type="file"]')) {
            return false;
        }
        if (form.target && form.target !== "_self") {
            return false;
        }
        return true;
    };

    const setLoadingState = (isLoading) => {
        document.body.classList.toggle("is-live-loading", isLoading);
    };

    const buildFormData = (form, submitter) => {
        let data;
        try {
            data = new FormData(form, submitter || undefined);
        } catch {
            data = new FormData(form);
        }

        if (
            submitter &&
            submitter.name &&
            !data.has(submitter.name)
        ) {
            data.append(submitter.name, submitter.value);
        }
        return data;
    };

    const formDataToSearchParams = (formData) => {
        const params = new URLSearchParams();
        for (const [key, value] of formData.entries()) {
            if (value instanceof File) {
                continue;
            }
            params.append(key, value);
        }
        return params;
    };

    const replaceOuterHtml = (selector, nextDocument) => {
        const currentNode = document.querySelector(selector);
        const nextNode = nextDocument.querySelector(selector);
        if (!currentNode || !nextNode) {
            return false;
        }
        currentNode.outerHTML = nextNode.outerHTML;
        return true;
    };

    const replaceInnerHtml = (selector, nextDocument) => {
        const currentNode = document.querySelector(selector);
        const nextNode = nextDocument.querySelector(selector);
        if (!currentNode || !nextNode) {
            return false;
        }
        currentNode.innerHTML = nextNode.innerHTML;
        return true;
    };

    const sameLayout = (nextDocument) => {
        const currentHasAppShell = Boolean(document.querySelector(".app-shell"));
        const nextHasAppShell = Boolean(nextDocument.querySelector(".app-shell"));
        const currentHasAuthShell = Boolean(document.querySelector(".auth-shell"));
        const nextHasAuthShell = Boolean(nextDocument.querySelector(".auth-shell"));

        return (
            (currentHasAppShell && nextHasAppShell) ||
            (currentHasAuthShell && nextHasAuthShell)
        );
    };

    const fallbackSwapDocument = (nextDocument) => {
        document.body.innerHTML = nextDocument.body.innerHTML;
    };

    const swapDocument = (nextDocument) => {
        document.title = nextDocument.title;

        if (!sameLayout(nextDocument)) {
            fallbackSwapDocument(nextDocument);
            hydrateDynamicUi();
            return;
        }

        if (document.querySelector(".app-shell") && nextDocument.querySelector(".app-shell")) {
            replaceOuterHtml(".mobile-topbar", nextDocument);
            replaceOuterHtml(".sidebar", nextDocument);
            replaceInnerHtml(".content", nextDocument);
            hydrateDynamicUi();
            return;
        }

        if (document.querySelector(".auth-shell") && nextDocument.querySelector(".auth-shell")) {
            replaceInnerHtml(".auth-shell", nextDocument);
            hydrateDynamicUi();
            return;
        }

        fallbackSwapDocument(nextDocument);
        hydrateDynamicUi();
    };

    const captureUiState = () => ({
        openDetails: Array.from(document.querySelectorAll("details[data-live-key][open]"))
            .map((node) => node.dataset.liveKey)
            .filter(Boolean),
        openPanels: Array.from(document.querySelectorAll("[data-review-panel][data-live-key]:not([hidden])"))
            .map((node) => node.dataset.liveKey)
            .filter(Boolean),
    });

    const escapeLiveKey = (value) => {
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(value);
        }
        return String(value).replace(/["\\]/g, "\\$&");
    };

    const restoreUiState = (state) => {
        if (!state) {
            return;
        }
        state.openDetails.forEach((key) => {
            const selector = `details[data-live-key="${escapeLiveKey(key)}"]`;
            document.querySelector(selector)?.setAttribute("open", "");
        });
        state.openPanels.forEach((key) => {
            setReviewPanelOpen(key, true);
        });
    };

    const setReviewPanelOpen = (key, shouldOpen) => {
        const escapedKey = escapeLiveKey(key);
        const panel = document.querySelector(`[data-review-panel="${escapedKey}"]`);
        const trigger = document.querySelector(`[data-review-toggle="${escapedKey}"]`);
        if (!panel || !trigger) {
            return;
        }
        panel.hidden = !shouldOpen;
        trigger.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
        trigger.classList.toggle("is-open", shouldOpen);
    };

    const toggleReviewPanel = (key) => {
        const escapedKey = escapeLiveKey(key);
        const panel = document.querySelector(`[data-review-panel="${escapedKey}"]`);
        if (!panel) {
            return;
        }
        setReviewPanelOpen(key, panel.hidden);
    };

    const resolveHistoryMode = (requestMethod, options) => {
        if (options.historyMode) {
            return options.historyMode;
        }
        return requestMethod === "GET" ? "push" : "replace";
    };

    const shouldScrollToTop = (requestMethod, previousUrl, nextUrl, options) => {
        if (typeof options.scroll === "boolean") {
            return options.scroll;
        }
        if (requestMethod !== "GET") {
            return false;
        }
        return previousUrl.pathname !== nextUrl.pathname;
    };

    const hashTargetId = (hash) => {
        if (!hash) {
            return "";
        }
        try {
            return decodeURIComponent(hash.slice(1));
        } catch {
            return hash.slice(1);
        }
    };

    const scrollToHashTarget = (url) => {
        const targetId = hashTargetId(url.hash);
        if (!targetId) {
            return false;
        }
        const target = document.getElementById(targetId);
        if (!target) {
            return false;
        }
        target.scrollIntoView({ block: "start", inline: "nearest", behavior: "auto" });
        return true;
    };

    const fetchAndSwap = async (url, options = {}) => {
        if (activeRequestController) {
            activeRequestController.abort();
        }

        const controller = new AbortController();
        activeRequestController = controller;
        const requestMethod = (options.method || "GET").toUpperCase();
        const requestedUrl = new URL(url.toString(), window.location.href);
        const previousUrl = new URL(window.location.href);
        const uiState = captureUiState();
        setLoadingState(true);

        try {
            const response = await fetch(url, {
                ...options,
                credentials: "same-origin",
                redirect: "follow",
                signal: controller.signal,
                headers: {
                    Accept: "text/html, */*;q=0.1",
                    "X-Requested-With": "fetch",
                    ...(options.headers || {}),
                },
            });

            const contentType = response.headers.get("content-type") || "";
            if (!contentType.includes("text/html")) {
                window.location.assign(response.url || url.toString());
                return;
            }

            const html = await response.text();
            const nextDocument = new DOMParser().parseFromString(html, "text/html");
            swapDocument(nextDocument);
            restoreUiState(uiState);

            const finalUrl = new URL(response.url || url.toString(), window.location.href);
            if (
                !finalUrl.hash &&
                requestedUrl.hash &&
                finalUrl.pathname === requestedUrl.pathname
            ) {
                finalUrl.hash = requestedUrl.hash;
            }
            const historyMode = resolveHistoryMode(requestMethod, options);
            if (historyMode === "replace") {
                window.history.replaceState({}, "", finalUrl);
            } else if (historyMode !== "none") {
                window.history.pushState({}, "", finalUrl);
            }

            if (scrollToHashTarget(finalUrl)) {
                return;
            }
            if (shouldScrollToTop(requestMethod, previousUrl, finalUrl, options)) {
                window.scrollTo({ top: 0, left: 0, behavior: "auto" });
            }
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            window.location.assign(url.toString());
        } finally {
            if (activeRequestController === controller) {
                activeRequestController = null;
            }
            setLoadingState(false);
        }
    };

    const toggleFractionForSelect = (select) => {
        const form = select.closest("form");
        const fractionWrap = form?.querySelector("[data-fraction-wrap]");
        if (!fractionWrap) {
            return;
        }
        fractionWrap.style.display = select.value === "__leader__" ? "grid" : "none";
    };

    const findReportUi = () => {
        const input = document.getElementById("report-attachments");
        const pasteTarget = document.querySelector("[data-paste-target]");
        const pasteStatus = document.querySelector("[data-paste-status]");
        const preview = document.querySelector("[data-attachment-preview]");

        if (!input || !pasteTarget || !pasteStatus || !preview) {
            return null;
        }

        return { input, pasteTarget, pasteStatus, preview };
    };

    const formatFileSize = (size) => {
        if (size < 1024) {
            return `${size} Б`;
        }
        if (size < 1024 * 1024) {
            return `${(size / 1024).toFixed(1)} КБ`;
        }
        return `${(size / (1024 * 1024)).toFixed(1)} МБ`;
    };

    const findUploadUi = (form) => ({
        wrap: form.querySelector("[data-upload-progress-wrap]"),
        status: form.querySelector("[data-upload-status]"),
        progress: form.querySelector("[data-upload-progress]"),
        value: form.querySelector("[data-upload-progress-value]"),
    });

    const setUploadProgress = (form, percent, text) => {
        const ui = findUploadUi(form);
        if (!ui.wrap || !ui.progress || !ui.value || !ui.status) {
            return;
        }
        ui.wrap.hidden = false;
        const safePercent = Math.max(0, Math.min(Math.round(percent), 100));
        ui.progress.value = safePercent;
        ui.value.textContent = `${safePercent}%`;
        if (text) {
            ui.status.textContent = text;
        }
    };

    const selectedUploadFiles = (form) => Array.from(form.querySelectorAll('input[type="file"]'))
        .flatMap((input) => Array.from(input.files || []));

    const validateUploadSelection = (form) => {
        const files = selectedUploadFiles(form);
        const maxFiles = Number(form.dataset.maxFiles || 0);
        const maxFileBytes = Number(form.dataset.maxFileBytes || 0);
        const maxTotalBytes = Number(form.dataset.maxTotalBytes || 0);
        const totalBytes = files.reduce((sum, file) => sum + file.size, 0);

        if (maxFiles && files.length > maxFiles) {
            return `Слишком много файлов: ${files.length}. Максимум: ${maxFiles}.`;
        }
        if (maxFileBytes) {
            const oversized = files.find((file) => file.size > maxFileBytes);
            if (oversized) {
                return `Файл «${oversized.name}» слишком большой: ${formatFileSize(oversized.size)}. Максимум: ${formatFileSize(maxFileBytes)}.`;
            }
        }
        if (maxTotalBytes && totalBytes > maxTotalBytes) {
            return `Суммарный размер файлов ${formatFileSize(totalBytes)} больше лимита ${formatFileSize(maxTotalBytes)}.`;
        }
        return "";
    };

    const submitUploadForm = (form, submitter) => new Promise((resolve) => {
        const validationError = validateUploadSelection(form);
        if (validationError) {
            setUploadProgress(form, 0, validationError);
            resolve(false);
            return;
        }

        const xhr = new XMLHttpRequest();
        const body = buildFormData(form, submitter);
        const requestedUrl = new URL(submitter?.getAttribute("formaction") || form.getAttribute("action") || window.location.href, window.location.href);
        const uiState = captureUiState();

        setLoadingState(true);
        setUploadProgress(form, 0, "Загрузка началась. Не закрывайте страницу...");

        xhr.open((form.getAttribute("method") || "POST").toUpperCase(), requestedUrl.toString(), true);
        xhr.setRequestHeader("Accept", "text/html, */*;q=0.1");
        xhr.setRequestHeader("X-Requested-With", "fetch");
        xhr.timeout = Number(form.dataset.uploadTimeout || 0);

        xhr.upload.addEventListener("progress", (event) => {
            if (!event.lengthComputable) {
                const uploaded = formatFileSize(event.loaded || 0);
                setUploadProgress(form, 0, `Загружено ${uploaded}. Ждём ответа сервера...`);
                return;
            }
            const percent = (event.loaded / event.total) * 100;
            setUploadProgress(form, percent, `Загружено ${formatFileSize(event.loaded)} из ${formatFileSize(event.total)}`);
        });

        xhr.addEventListener("load", () => {
            setLoadingState(false);
            if (xhr.status >= 400) {
                setUploadProgress(
                    form,
                    0,
                    `Сервер отклонил загрузку (${xhr.status}). Попробуйте файл меньше или повторите позже.`
                );
                resolve(false);
                return;
            }

            const contentType = xhr.getResponseHeader("content-type") || "";
            if (!contentType.includes("text/html")) {
                window.location.assign(xhr.responseURL || requestedUrl.toString());
                resolve(true);
                return;
            }

            setUploadProgress(form, 100, "Загрузка завершена. Обновляем страницу...");
            const nextDocument = new DOMParser().parseFromString(xhr.responseText, "text/html");
            swapDocument(nextDocument);
            restoreUiState(uiState);
            window.history.replaceState({}, "", xhr.responseURL || requestedUrl.toString());
            window.scrollTo({ top: 0, left: 0, behavior: "auto" });
            resolve(true);
        });

        xhr.addEventListener("error", () => {
            setLoadingState(false);
            setUploadProgress(
                form,
                0,
                "Соединение оборвалось во время загрузки. Проверьте интернет и попробуйте отправить ещё раз."
            );
            resolve(false);
        });

        xhr.addEventListener("timeout", () => {
            setLoadingState(false);
            setUploadProgress(
                form,
                0,
                "Истекло время ожидания загрузки. Попробуйте стабильный Wi-Fi или файл меньшего размера."
            );
            resolve(false);
        });

        xhr.addEventListener("abort", () => {
            setLoadingState(false);
            setUploadProgress(form, 0, "Загрузка отменена.");
            resolve(false);
        });

        xhr.send(body);
    });

    const updateReportAttachmentPreview = () => {
        const reportUi = findReportUi();
        if (!reportUi) {
            return;
        }

        const { input, preview } = reportUi;
        const files = Array.from(input.files || []);
        if (!files.length) {
            preview.hidden = true;
            preview.innerHTML = "";
            return;
        }

        preview.hidden = false;
        preview.innerHTML = "";

        const title = document.createElement("strong");
        title.textContent = `Прикреплено файлов: ${files.length}`;
        preview.appendChild(title);

        const list = document.createElement("div");
        list.className = "attachment-preview-list";
        files.forEach((file) => {
            const item = document.createElement("div");
            item.className = "attachment-chip";
            item.textContent = `${file.name} · ${formatFileSize(file.size)}`;
            list.appendChild(item);
        });
        preview.appendChild(list);
    };

    const buildPastedFile = (file, index) => {
        const extension = file.type.split("/")[1] || "png";
        const fallbackName = `pasted-image-${Date.now()}-${index}.${extension}`;
        const safeName = file.name && file.name.trim() ? file.name : fallbackName;
        return new File([file], safeName, {
            type: file.type || "image/png",
            lastModified: Date.now(),
        });
    };

    const mergeReportFiles = (incomingFiles) => {
        const reportUi = findReportUi();
        if (!reportUi) {
            return;
        }

        const transfer = new DataTransfer();
        Array.from(reportUi.input.files || []).forEach((file) => transfer.items.add(file));
        incomingFiles.forEach((file) => transfer.items.add(file));
        reportUi.input.files = transfer.files;
        updateReportAttachmentPreview();
    };

    const extractImagesFromClipboard = (event) => {
        const items = Array.from(event.clipboardData?.items || []);
        let imageIndex = 0;

        return items.flatMap((item) => {
            if (item.kind !== "file") {
                return [];
            }
            const file = item.getAsFile();
            if (!file || !file.type.startsWith("image/")) {
                return [];
            }
            imageIndex += 1;
            return [buildPastedFile(file, imageIndex)];
        });
    };

    const showCopyFeedback = (feedback, text) => {
        if (!feedback) {
            return;
        }
        feedback.textContent = text;
        window.clearTimeout(feedback._copyTimer);
        feedback._copyTimer = window.setTimeout(() => {
            feedback.textContent = "";
        }, 1800);
    };

    const copyText = async (value) => {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(value);
            return;
        }

        const area = document.createElement("textarea");
        area.value = value;
        area.setAttribute("readonly", "");
        area.style.position = "absolute";
        area.style.left = "-9999px";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        document.body.removeChild(area);
    };

    const normStatusLabels = {
        completed: "Выполнен норматив",
        no_norm: "Нет нормы",
        inactive: "Неактивы",
    };

    const normRows = (form) => Array.from(form.querySelectorAll("[data-norm-row]"));

    const normPreviewOrder = (row) => {
        const value = Number(row.dataset.normPreviewOrder || 0);
        return Number.isFinite(value) ? value : 0;
    };

    const ensureNormPreviewOrders = (form, rows = normRows(form)) => {
        let maxOrder = Number(form.dataset.normPreviewSequence || 0);
        maxOrder = Number.isFinite(maxOrder) ? maxOrder : 0;

        rows.forEach((row, index) => {
            const currentOrder = normPreviewOrder(row);
            if (currentOrder > 0) {
                maxOrder = Math.max(maxOrder, currentOrder);
                return;
            }

            const order = index + 1;
            row.dataset.normPreviewOrder = String(order);
            maxOrder = Math.max(maxOrder, order);
        });

        form.dataset.normPreviewSequence = String(maxOrder);
    };

    const moveNormRowToPreviewEnd = (row) => {
        const form = row.closest("[data-norm-check-form]");
        if (!form) {
            return;
        }
        ensureNormPreviewOrders(form);
        const currentSequence = Number(form.dataset.normPreviewSequence || 0);
        const nextOrder = (Number.isFinite(currentSequence) ? currentSequence : normRows(form).length) + 1;
        form.dataset.normPreviewSequence = String(nextOrder);
        row.dataset.normPreviewOrder = String(nextOrder);
    };

    const normRowControl = (row, selector) => row.querySelector(selector);

    const normRowAnswers = (row) => {
        const value = Number(normRowControl(row, "[data-norm-answers]")?.value || 0);
        return Number.isFinite(value) ? value : 0;
    };

    const normRowObjective = (row) => normRowControl(row, "[data-norm-objective]")?.value === "1";

    const normRowAppliedAnswers = (row) => {
        const value = Number(normRowControl(row, "[data-norm-applied-answers]")?.value || 0);
        return Number.isFinite(value) ? Math.max(Math.trunc(value), 0) : 0;
    };

    const normRowAppliedObjective = (row) => normRowControl(row, "[data-norm-applied-objective]")?.value === "1";

    const normRowAppliedObjectiveDate = (row) => normRowControl(row, "[data-norm-applied-objective-date]")?.value || "";

    const setNormSyncStatus = (row, message = "") => {
        const status = normRowControl(row, "[data-norm-sync-status]");
        if (status) {
            status.textContent = message;
        }
    };

    const clearNormSyncStatusLater = (row, ticket) => {
        window.setTimeout(() => {
            if (row.dataset.normSyncTicket === ticket && !row.classList.contains("is-norm-syncing")) {
                setNormSyncStatus(row, "");
            }
        }, 1600);
    };

    const normFormUserId = (row) => row.dataset.userId || normRowControl(row, 'input[name="user_id"]')?.value || "";

    const normFormCsrfToken = (form) => form?.querySelector('input[name="csrf_token"]')?.value || "";

    const syncNormStatusButtons = (row, status) => {
        row.querySelectorAll("[data-norm-status-button]").forEach((button) => {
            const isActive = button.dataset.normStatusButton === status;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
    };

    const setNormRowStatus = (row, status, inactiveInfo = "") => {
        const statusInput = normRowControl(row, "[data-norm-status]");
        const hiddenInfo = normRowControl(row, "[data-norm-inactive-info]");
        if (!statusInput || !Object.prototype.hasOwnProperty.call(normStatusLabels, status)) {
            return;
        }
        const previousStatus = statusInput.value || row.dataset.normStatus || "";
        if (previousStatus !== status) {
            moveNormRowToPreviewEnd(row);
        }
        statusInput.value = status;
        row.dataset.normStatus = status;
        row.classList.toggle("is-norm-completed", status === "completed");
        row.classList.toggle("is-norm-missing", status === "no_norm");
        row.classList.toggle("is-norm-inactive", status === "inactive");
        if (hiddenInfo) {
            hiddenInfo.value = status === "inactive" ? inactiveInfo : "";
        }
        syncNormStatusButtons(row, status);
    };

    const parseInactivePeriods = (row) => {
        try {
            const parsed = JSON.parse(row.dataset.inactivePeriods || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    };

    const isIsoDateValue = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value || "");

    const inactiveInfoForDate = (row, dateValue) => {
        if (!isIsoDateValue(dateValue)) {
            return "";
        }
        const period = parseInactivePeriods(row).find((item) => (
            isIsoDateValue(item.start) &&
            isIsoDateValue(item.end) &&
            item.start <= dateValue &&
            dateValue <= item.end
        ));
        return period?.label || "";
    };

    const syncNormInactiveBadge = (row, dateValue) => {
        const badge = normRowControl(row, "[data-norm-inactive-badge]");
        if (!badge) {
            return;
        }
        const inactiveInfo = inactiveInfoForDate(row, dateValue);
        badge.textContent = inactiveInfo ? `Неактив: ${inactiveInfo}` : "";
        badge.classList.toggle("has-inactive", Boolean(inactiveInfo));
    };

    const syncNormPlusButton = (row) => {
        const hidden = normRowControl(row, "[data-norm-objective]");
        const button = normRowControl(row, "[data-norm-plus]");
        if (!hidden || !button) {
            return;
        }
        const isActive = hidden.value === "1";
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
    };

    const applyNormAnswersNow = async (row, options = {}) => {
        const form = row.closest("[data-norm-check-form]");
        const appliedInput = normRowControl(row, "[data-norm-applied-answers]");
        const userId = normFormUserId(row);
        const csrf = normFormCsrfToken(form);
        if (!form || !appliedInput || !userId || !csrf) {
            return;
        }

        const status = normRowControl(row, "[data-norm-status]")?.value || "completed";
        const rawAmount = typeof options.forceAmount === "number" ? options.forceAmount : normRowAnswers(row);
        let amount = status === "completed" ? Math.max(Math.trunc(rawAmount), 0) : 0;
        const appliedAmount = normRowAppliedAnswers(row);
        if (amount === appliedAmount && !options.force) {
            return;
        }

        const body = new FormData();
        body.set("csrf_token", csrf);
        body.set("user_id", userId);
        body.set("amount", String(amount));
        body.set("applied_amount", String(appliedAmount));

        const ticket = `${Date.now()}:${Math.random()}`;
        row.dataset.normSyncTicket = ticket;
        row.classList.add("is-norm-syncing");
        row.classList.remove("is-norm-sync-error");
        setNormSyncStatus(row, amount >= appliedAmount ? "Начисляю ответы..." : "Обновляю ответы...");

        try {
            const response = await fetch(form.dataset.normAnswerUrl || "/administration/norm-checks/answers", {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не удалось начислить ответы");
            }
            const nextApplied = Number(result.applied_amount);
            const delta = Number(result.delta || 0);
            appliedInput.value = String(Number.isFinite(nextApplied) ? Math.max(Math.trunc(nextApplied), 0) : amount);
            row.classList.remove("is-norm-sync-error");
            setNormSyncStatus(row, delta === 0 ? "Без изменений" : (delta > 0 ? "Ответы начислены" : "Ответы сняты"));
            clearNormSyncStatusLater(row, ticket);
        } catch {
            row.classList.add("is-norm-sync-error");
            setNormSyncStatus(row, "Ошибка начисления");
        } finally {
            if (row.dataset.normSyncTicket === ticket) {
                row.classList.remove("is-norm-syncing");
            }
        }
    };

    const applyNormAnswers = (row, options = {}) => {
        if (row._normAnswerRequest) {
            row._normAnswerQueuedOptions = options;
            return row._normAnswerRequest;
        }
        row._normAnswerRequest = applyNormAnswersNow(row, options).finally(() => {
            const queuedOptions = row._normAnswerQueuedOptions;
            row._normAnswerQueuedOptions = null;
            row._normAnswerRequest = null;
            if (queuedOptions) {
                return applyNormAnswers(row, queuedOptions);
            }
            return undefined;
        });
        return row._normAnswerRequest;
    };

    const applyNormObjectiveNow = async (row, options = {}) => {
        const form = row.closest("[data-norm-check-form]");
        const hidden = normRowControl(row, "[data-norm-objective]");
        const appliedInput = normRowControl(row, "[data-norm-applied-objective]");
        const appliedDateInput = normRowControl(row, "[data-norm-applied-objective-date]");
        const button = normRowControl(row, "[data-norm-plus]");
        const userId = normFormUserId(row);
        const csrf = normFormCsrfToken(form);
        const normDate = form?.querySelector("[data-norm-date]")?.value || "";
        if (!form || !hidden || !appliedInput || !appliedDateInput || !userId || !csrf) {
            return;
        }

        let enabled = typeof options.forceEnabled === "boolean" ? options.forceEnabled : hidden.value === "1";
        const applied = normRowAppliedObjective(row);
        const appliedDate = normRowAppliedObjectiveDate(row);
        if (options.preserveApplied && applied && !enabled) {
            enabled = true;
            hidden.value = "1";
            syncNormPlusButton(row);
        }
        if (options.preserveApplied && applied && appliedDate && appliedDate !== normDate) {
            hidden.value = "0";
            syncNormPlusButton(row);
            return;
        }
        if (enabled === applied && (!enabled || appliedDate === normDate) && !options.force) {
            return;
        }

        const body = new FormData();
        body.set("csrf_token", csrf);
        body.set("user_id", userId);
        body.set("enabled", enabled ? "1" : "0");
        body.set("applied", applied ? "1" : "0");
        body.set("norm_date", normDate);
        body.set("applied_norm_date", appliedDate);

        const ticket = `${Date.now()}:${Math.random()}`;
        row.dataset.normSyncTicket = ticket;
        row.classList.add("is-norm-syncing");
        row.classList.remove("is-norm-sync-error");
        if (button) {
            button.disabled = true;
        }
        setNormSyncStatus(row, enabled ? "Начисляю +1..." : "Снимаю +1...");

        try {
            const response = await fetch(form.dataset.normObjectiveUrl || "/administration/norm-checks/objective", {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не удалось обновить +1");
            }
            const nextApplied = Boolean(result.applied_objective);
            hidden.value = nextApplied ? "1" : "0";
            appliedInput.value = nextApplied ? "1" : "0";
            appliedDateInput.value = nextApplied ? (result.applied_norm_date || normDate) : "";
            row.classList.remove("is-norm-sync-error");
            syncNormPlusButton(row);
            setNormSyncStatus(row, nextApplied ? "+1 день начислен" : "+1 день снят");
            clearNormSyncStatusLater(row, ticket);
        } catch {
            hidden.value = applied ? "1" : "0";
            row.classList.add("is-norm-sync-error");
            syncNormPlusButton(row);
            if (!applied && normRowAnswers(row) <= 0) {
                setNormRowStatus(row, "no_norm");
                if (form) {
                    updateNormPreview(form);
                }
            }
            setNormSyncStatus(row, "Ошибка +1");
        } finally {
            if (button) {
                button.disabled = false;
            }
            if (row.dataset.normSyncTicket === ticket) {
                row.classList.remove("is-norm-syncing");
            }
        }
    };

    const applyNormObjective = (row, options = {}) => {
        if (row._normObjectiveRequest) {
            row._normObjectiveQueuedOptions = options;
            return row._normObjectiveRequest;
        }
        row._normObjectiveRequest = applyNormObjectiveNow(row, options).finally(() => {
            const queuedOptions = row._normObjectiveQueuedOptions;
            row._normObjectiveQueuedOptions = null;
            row._normObjectiveRequest = null;
            if (queuedOptions) {
                return applyNormObjective(row, queuedOptions);
            }
            return undefined;
        });
        return row._normObjectiveRequest;
    };

    const clearNormObjectiveSelection = (row) => {
        const hidden = normRowControl(row, "[data-norm-objective]");
        if (!hidden || hidden.value === "0") {
            return false;
        }
        hidden.value = "0";
        syncNormPlusButton(row);
        return true;
    };

    const syncNormRowAppliedState = (row) => {
        const status = normRowControl(row, "[data-norm-status]")?.value || "no_norm";
        if (status === "completed") {
            applyNormAnswers(row);
            const wantsObjective = normRowObjective(row);
            if (wantsObjective || normRowAppliedObjective(row)) {
                applyNormObjective(row, { forceEnabled: wantsObjective });
            }
            return;
        }

        const hadSelectedObjective = normRowObjective(row);
        clearNormObjectiveSelection(row);
        applyNormAnswers(row, { forceAmount: 0 });
        if (hadSelectedObjective || normRowAppliedObjective(row)) {
            applyNormObjective(row, { forceEnabled: false });
        }
    };

    const syncNormRowImmediateState = (row) => {
        const status = normRowControl(row, "[data-norm-status]")?.value || "no_norm";
        if (status === "completed") {
            return;
        }
        const form = row.closest("[data-norm-check-form]");
        const normDate = form?.querySelector("[data-norm-date]")?.value || "";
        const appliedDate = normRowAppliedObjectiveDate(row);
        const hidden = normRowControl(row, "[data-norm-objective]");
        if (hidden && hidden.value === "1" && normRowAppliedObjective(row) && appliedDate && appliedDate !== normDate) {
            hidden.value = "0";
            syncNormPlusButton(row);
            return;
        }
        if (hidden && hidden.value === "1" && !normRowAppliedObjective(row)) {
            hidden.value = "0";
            syncNormPlusButton(row);
        }
    };

    const settleNormCheckImmediateSync = async (form) => {
        const active = document.activeElement;
        if (active instanceof HTMLElement && form.contains(active)) {
            const row = active.closest("[data-norm-row]");
            active.blur();
            if (row && active.matches("[data-norm-answers]")) {
                applyNormAnswers(row);
            }
        }
        normRows(form).forEach(syncNormRowAppliedState);
        let pending = normRows(form).flatMap((row) => (
            [row._normAnswerRequest, row._normObjectiveRequest].filter(Boolean)
        ));
        while (pending.length) {
            await Promise.allSettled(pending);
            pending = normRows(form).flatMap((row) => (
                [row._normAnswerRequest, row._normObjectiveRequest].filter(Boolean)
            ));
        }
    };

    const makeNormPreviewItem = (row, status) => {
        const item = document.createElement("div");
        item.className = "norm-preview-item";

        const name = document.createElement("strong");
        name.textContent = row.dataset.normNick || "Администратор";
        item.appendChild(name);

        const details = document.createElement("span");
        if (status === "completed") {
            const parts = [`${Math.max(normRowAnswers(row), 0)} отв.`];
            if (normRowObjective(row)) {
                parts.push("+1 день");
            }
            details.textContent = parts.join(" · ");
        } else if (status === "inactive") {
            details.textContent = normRowControl(row, "[data-norm-inactive-info]")?.value || "Неактив";
        } else {
            details.textContent = "0 ответов";
        }
        item.appendChild(details);
        return item;
    };

    const updateNormPreview = (form) => {
        const counts = { completed: 0, no_norm: 0, inactive: 0 };
        const groupedRows = { completed: [], no_norm: [], inactive: [] };
        const lists = {};
        const dateValue = form.querySelector("[data-norm-date]")?.value || "";
        const rows = normRows(form);
        const rowIndexes = new Map(rows.map((row, index) => [row, index]));
        ensureNormPreviewOrders(form, rows);

        Object.keys(counts).forEach((status) => {
            lists[status] = form.querySelector(`[data-norm-preview="${status}"]`);
            if (lists[status]) {
                lists[status].innerHTML = "";
            }
        });

        rows.forEach((row) => {
            const statusInput = normRowControl(row, "[data-norm-status]");
            const status = Object.prototype.hasOwnProperty.call(counts, statusInput?.value)
                ? statusInput.value
                : "no_norm";
            setNormRowStatus(row, status, normRowControl(row, "[data-norm-inactive-info]")?.value || "");
            syncNormInactiveBadge(row, dateValue);
            counts[status] += 1;
            groupedRows[status].push(row);
            syncNormPlusButton(row);
        });

        Object.keys(groupedRows).forEach((status) => {
            groupedRows[status]
                .sort((left, right) => (
                    normPreviewOrder(left) - normPreviewOrder(right) ||
                    (rowIndexes.get(left) ?? 0) - (rowIndexes.get(right) ?? 0)
                ))
                .forEach((row) => {
                    lists[status]?.appendChild(makeNormPreviewItem(row, status));
                });
        });

        Object.entries(counts).forEach(([status, count]) => {
            const counter = form.querySelector(`[data-norm-count="${status}"]`);
            if (counter) {
                counter.textContent = String(count);
            }
            if (count === 0 && lists[status]) {
                const empty = document.createElement("p");
                empty.className = "empty-state norm-preview-empty";
                empty.textContent = "Пока пусто";
                lists[status].appendChild(empty);
            }
        });
    };

    const runNormAction = (form, action) => {
        const dateValue = form.querySelector("[data-norm-date]")?.value || "";
        if (action === "check") {
            normRows(form).forEach((row) => {
                const status = normRowAnswers(row) > 0 || normRowObjective(row) ? "completed" : "no_norm";
                setNormRowStatus(row, status);
            });
        }
        if (action === "inactives") {
            normRows(form).forEach((row) => {
                const currentStatus = normRowControl(row, "[data-norm-status]")?.value;
                if (currentStatus === "completed" && normRowAnswers(row) <= 0 && !normRowObjective(row)) {
                    setNormRowStatus(row, "no_norm");
                }
            });
            normRows(form).forEach((row) => {
                const currentStatus = normRowControl(row, "[data-norm-status]")?.value;
                if (currentStatus !== "no_norm") {
                    return;
                }
                const inactiveInfo = inactiveInfoForDate(row, dateValue);
                if (inactiveInfo) {
                    setNormRowStatus(row, "inactive", inactiveInfo);
                }
            });
        }
        updateNormPreview(form);
        if (action === "check" || action === "inactives") {
            normRows(form).forEach(syncNormRowAppliedState);
        } else {
            normRows(form).forEach(syncNormRowImmediateState);
        }
        if (action === "result") {
            form.querySelector(".norm-check-result-grid")?.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
    };

    const hydrateNormCheckForms = () => {
        document.querySelectorAll("[data-norm-check-form]").forEach(updateNormPreview);
    };

    const hydrateDynamicUi = () => {
        document.querySelectorAll("[data-role-select]").forEach(toggleFractionForSelect);
        updateReportAttachmentPreview();
        hydrateNormCheckForms();
    };

    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-value]");
        if (copyButton) {
            event.preventDefault();
            const feedback = copyButton
                .closest(".dashboard-copy")
                ?.querySelector("[data-copy-feedback]");
            try {
                await copyText(copyButton.dataset.copyValue);
                showCopyFeedback(feedback, "Скопировано");
            } catch {
                showCopyFeedback(feedback, "Ошибка");
            }
            return;
        }

        const copyLinkButton = event.target.closest("[data-copy-link]");
        if (copyLinkButton) {
            event.preventDefault();
            let link = copyLinkButton.dataset.copyLink || "";
            const shareUrl = copyLinkButton.dataset.shareUrl || "";
            const originalText = copyLinkButton.dataset.copyOriginal || copyLinkButton.textContent;
            copyLinkButton.dataset.copyOriginal = originalText;
            copyLinkButton.textContent = shareUrl ? "Открываю..." : "Копирую...";
            copyLinkButton.disabled = true;
            try {
                if (shareUrl) {
                    const body = new FormData();
                    body.set("csrf_token", copyLinkButton.dataset.csrfToken || "");
                    const response = await fetch(shareUrl, {
                        method: "POST",
                        body,
                        credentials: "same-origin",
                        headers: {
                            Accept: "application/json",
                            "X-Requested-With": "fetch",
                        },
                    });
                    const result = await response.json().catch(() => ({}));
                    if (!response.ok || result.ok === false) {
                        throw new Error(result.error || "Не удалось открыть доступ.");
                    }
                    link = result.url || link;
                }
                await copyText(link);
                copyLinkButton.textContent = "Скопировано";
                copyLinkButton.classList.add("is-copied");
            } catch {
                copyLinkButton.textContent = "Ошибка";
                copyLinkButton.classList.remove("is-copied");
            } finally {
                copyLinkButton.disabled = false;
            }
            window.clearTimeout(copyLinkButton._copyTimer);
            copyLinkButton._copyTimer = window.setTimeout(() => {
                copyLinkButton.textContent = copyLinkButton.dataset.copyOriginal || originalText;
                copyLinkButton.classList.remove("is-copied");
            }, 1800);
            return;
        }

        const normStatusButton = event.target.closest("[data-norm-status-button]");
        if (normStatusButton) {
            event.preventDefault();
            const row = normStatusButton.closest("[data-norm-row]");
            const form = normStatusButton.closest("[data-norm-check-form]");
            const status = normStatusButton.dataset.normStatusButton || "";
            if (row && form && Object.prototype.hasOwnProperty.call(normStatusLabels, status)) {
                const dateValue = form.querySelector("[data-norm-date]")?.value || "";
                const inactiveInfo = status === "inactive" ? inactiveInfoForDate(row, dateValue) : "";
                setNormRowStatus(row, status, inactiveInfo);
                syncNormRowAppliedState(row);
                updateNormPreview(form);
            }
            return;
        }

        const normPlusButton = event.target.closest("[data-norm-plus]");
        if (normPlusButton) {
            event.preventDefault();
            const row = normPlusButton.closest("[data-norm-row]");
            const form = normPlusButton.closest("[data-norm-check-form]");
            const hidden = row?.querySelector("[data-norm-objective]");
            if (row && form && hidden) {
                const normDate = form.querySelector("[data-norm-date]")?.value || "";
                const wasApplied = normRowAppliedObjective(row);
                const appliedDate = normRowAppliedObjectiveDate(row);
                if (wasApplied && appliedDate && appliedDate !== normDate) {
                    hidden.value = "0";
                    setNormSyncStatus(row, "+1 уже выдан за другую дату");
                    syncNormPlusButton(row);
                    updateNormPreview(form);
                    return;
                }
                hidden.value = hidden.value === "1" ? "0" : "1";
                if (hidden.value === "1") {
                    setNormRowStatus(row, "completed");
                } else if (normRowAnswers(row) <= 0) {
                    setNormRowStatus(row, "no_norm");
                }
                syncNormPlusButton(row);
                updateNormPreview(form);
                if (hidden.value === "1" || wasApplied) {
                    applyNormObjective(row, { preserveApplied: hidden.value === "1" });
                }
            }
            return;
        }

        const normActionButton = event.target.closest("[data-norm-action]");
        if (normActionButton) {
            event.preventDefault();
            const form = normActionButton.closest("[data-norm-check-form]");
            if (form) {
                runNormAction(form, normActionButton.dataset.normAction);
            }
            return;
        }

        const pasteTarget = event.target.closest("[data-paste-target]");
        if (pasteTarget) {
            pasteTarget.focus();
            return;
        }

        const reviewToggle = event.target.closest("[data-review-toggle]");
        if (reviewToggle) {
            event.preventDefault();
            toggleReviewPanel(reviewToggle.dataset.reviewToggle);
            return;
        }

        const link = event.target.closest("a[href]");
        if (!shouldHandleLink(link, event)) {
            return;
        }

        event.preventDefault();
        await fetchAndSwap(link.href);
    });

    document.addEventListener("submit", async (event) => {
        const form = event.target;
        if (form instanceof HTMLFormElement && form.dataset.uploadForm !== undefined) {
            event.preventDefault();
            const submitter = event.submitter || null;
            if (submitter) {
                submitter.disabled = true;
            }
            const completed = await submitUploadForm(form, submitter);
            if (!completed && submitter && document.body.contains(submitter)) {
                submitter.disabled = false;
            }
            return;
        }

        if (!(form instanceof HTMLFormElement) || !shouldHandleForm(form)) {
            return;
        }

        const submitter = event.submitter || null;
        const method = (
            submitter?.getAttribute("formmethod") ||
            form.getAttribute("method") ||
            "get"
        ).toUpperCase();
        if (!["GET", "POST"].includes(method)) {
            return;
        }

        const action = submitter?.getAttribute("formaction") || form.getAttribute("action") || window.location.href;
        const url = new URL(action, window.location.href);

        event.preventDefault();

        if (submitter) {
            submitter.disabled = true;
        }

        try {
            if (form.dataset.normCheckForm !== undefined) {
                await settleNormCheckImmediateSync(form);
            }
            if (method === "GET") {
                const params = formDataToSearchParams(buildFormData(form, submitter));
                url.search = params.toString();
                await fetchAndSwap(url.toString());
            } else {
                const body = buildFormData(form, submitter);
                await fetchAndSwap(url.toString(), {
                    method,
                    body,
                });
            }
        } finally {
            if (submitter && document.body.contains(submitter)) {
                submitter.disabled = false;
            }
        }
    });

    document.addEventListener("change", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }

        if (target.matches("[data-role-select]")) {
            toggleFractionForSelect(target);
            return;
        }

        if (target.matches("[data-norm-date]")) {
            const form = target.closest("[data-norm-check-form]");
            if (form) {
                normRows(form).forEach((row) => {
                    if (normRowControl(row, "[data-norm-status]")?.value === "inactive") {
                        setNormRowStatus(row, "no_norm");
                    }
                });
                normRows(form).forEach((row) => {
                    const hidden = normRowControl(row, "[data-norm-objective]");
                    const appliedDate = normRowAppliedObjectiveDate(row);
                    if (hidden && normRowAppliedObjective(row) && appliedDate) {
                        if (appliedDate !== target.value) {
                            hidden.value = "0";
                            syncNormPlusButton(row);
                            if (normRowAnswers(row) <= 0 && normRowControl(row, "[data-norm-status]")?.value === "completed") {
                                setNormRowStatus(row, "no_norm");
                            }
                        } else if (hidden.value !== "1") {
                            hidden.value = "1";
                            syncNormPlusButton(row);
                            if (normRowAnswers(row) <= 0 && normRowControl(row, "[data-norm-status]")?.value === "no_norm") {
                                setNormRowStatus(row, "completed");
                            }
                        }
                    }
                    if (normRowObjective(row) && !normRowAppliedObjective(row)) {
                        applyNormObjective(row, { preserveApplied: true });
                    }
                    syncNormRowImmediateState(row);
                });
                updateNormPreview(form);
            }
            return;
        }

        if (target.id === "report-attachments") {
            updateReportAttachmentPreview();
        }
    });

    document.addEventListener("focusout", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches("[data-norm-answers]")) {
            return;
        }
        const row = target.closest("[data-norm-row]");
        if (row) {
            applyNormAnswers(row);
        }
    });

    document.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches("[data-norm-answers]")) {
            return;
        }
        const row = target.closest("[data-norm-row]");
        const form = target.closest("[data-norm-check-form]");
        if (!row || !form) {
            return;
        }
        const answers = normRowAnswers(row);
        const status = normRowControl(row, "[data-norm-status]")?.value || "no_norm";
        if (answers > 0 && status === "no_norm") {
            setNormRowStatus(row, "completed");
        } else if (answers <= 0 && status === "completed" && !normRowObjective(row)) {
            setNormRowStatus(row, "no_norm");
        }
        updateNormPreview(form);
    });

    document.addEventListener("paste", (event) => {
        const reportUi = findReportUi();
        if (!reportUi || event.defaultPrevented) {
            return;
        }

        const pastedImages = extractImagesFromClipboard(event);
        if (!pastedImages.length) {
            return;
        }

        event.preventDefault();
        mergeReportFiles(pastedImages);
        reportUi.pasteTarget.classList.add("is-success");
        reportUi.pasteStatus.textContent = `Добавлено изображений: ${pastedImages.length}`;
        window.clearTimeout(reportUi.pasteTarget._pasteTimer);
        reportUi.pasteTarget._pasteTimer = window.setTimeout(() => {
            reportUi.pasteTarget.classList.remove("is-success");
            reportUi.pasteStatus.textContent =
                "Можно и дальше добавлять обычные файлы через выбор.";
        }, 2200);
    });

    window.addEventListener("popstate", async () => {
        await fetchAndSwap(window.location.href, {
            historyMode: "replace",
            scroll: false,
        });
    });

    window.addEventListener("DOMContentLoaded", () => {
        hydrateDynamicUi();
        window.history.replaceState({}, "", window.location.href);
    });
})();
