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

    const hydrateDynamicUi = () => {
        document.querySelectorAll("[data-role-select]").forEach(toggleFractionForSelect);
        updateReportAttachmentPreview();
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

        if (target.id === "report-attachments") {
            updateReportAttachmentPreview();
        }
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
