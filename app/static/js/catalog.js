(function () {
    var THEME_DEFAULT = "default";
    var THEME_LEGACY = "legacy";
    var THEME_STORAGE_KEY_PREFIX = "dashboard.theme";

    var CLOCK_CITY_LABELS = {
        "europe/moscow": { ru: "Москва", en: "Moscow" },
        "europe/istanbul": { ru: "Стамбул", en: "Istanbul" },
        "africa/cairo": { ru: "Каир", en: "Cairo" },
        "europe/budapest": { ru: "Будапешт", en: "Budapest" },
    };

    function normalize(value) {
        return (value || "").toLowerCase();
    }

    function normalizeLookup(value) {
        return (value || "").trim().toLowerCase();
    }

    function getPageLanguage() {
        var lang = normalizeLookup(document.documentElement.getAttribute("lang") || "ru");
        return lang.indexOf("en") === 0 ? "en" : "ru";
    }

    function getLocaleForLanguage(lang) {
        return lang === "en" ? "en-US" : "ru-RU";
    }

    function normalizeTheme(value) {
        return value === THEME_LEGACY ? THEME_LEGACY : THEME_DEFAULT;
    }

    function readStoredValue(storageKey) {
        try {
            return window.localStorage.getItem(storageKey);
        } catch (_error) {
            return null;
        }
    }

    function writeStoredValue(storageKey, value) {
        try {
            window.localStorage.setItem(storageKey, value);
        } catch (_error) {
            // Ignore storage errors (for example in strict privacy mode).
        }
    }

    function getThemeStorageKey(toggleButton) {
        if (!toggleButton) {
            return THEME_STORAGE_KEY_PREFIX;
        }
        var rawScope = (toggleButton.getAttribute("data-theme-storage-scope") || "").trim().toLowerCase();
        if (!rawScope) {
            return THEME_STORAGE_KEY_PREFIX;
        }
        return THEME_STORAGE_KEY_PREFIX + "." + encodeURIComponent(rawScope);
    }

    function applyTheme(themeName) {
        var nextTheme = normalizeTheme(themeName);
        document.body.setAttribute("data-theme", nextTheme);
        return nextTheme;
    }

    function updateThemeToggleLabel(toggleButton, activeTheme) {
        if (!toggleButton) {
            return;
        }
        var labelForDefaultTheme = toggleButton.getAttribute("data-theme-label-default") || "Alternative theme";
        var labelForLegacyTheme = toggleButton.getAttribute("data-theme-label-legacy") || "Default theme";
        var nextLabel = activeTheme === THEME_LEGACY ? labelForLegacyTheme : labelForDefaultTheme;
        var srLabel = toggleButton.querySelector(".theme-toggle-sr-label");
        if (srLabel) {
            srLabel.textContent = nextLabel;
        }
        toggleButton.setAttribute("aria-label", nextLabel);
        toggleButton.setAttribute("title", nextLabel);
        toggleButton.setAttribute("aria-pressed", activeTheme === THEME_LEGACY ? "true" : "false");
    }

    function setupThemeToggle() {
        var toggleButton = document.querySelector("[data-theme-toggle]");
        var storageKey = getThemeStorageKey(toggleButton);
        var activeTheme = applyTheme(readStoredValue(storageKey));

        updateThemeToggleLabel(toggleButton, activeTheme);
        if (!toggleButton) {
            return;
        }

        toggleButton.addEventListener("click", function () {
            var currentTheme = normalizeTheme(document.body.getAttribute("data-theme"));
            var nextTheme = currentTheme === THEME_LEGACY ? THEME_DEFAULT : THEME_LEGACY;
            applyTheme(nextTheme);
            writeStoredValue(storageKey, nextTheme);
            updateThemeToggleLabel(toggleButton, nextTheme);
            scheduleStickyOffsetUpdate();
        });
    }

    function setupSearch() {
        var input = document.getElementById("serviceSearch");
        if (!input) {
            return;
        }

        var sections = Array.prototype.slice.call(document.querySelectorAll("[data-section]")).map(function (section) {
            return {
                section: section,
                cells: Array.prototype.slice.call(section.querySelectorAll("[data-service]")),
            };
        });

        function setVisibility(element, isVisible) {
            element.hidden = !isVisible;
        }

        function applyFilter() {
            var query = normalize(input.value.trim());

            sections.forEach(function (entry) {
                var visibleCount = 0;

                entry.cells.forEach(function (cell) {
                    var text = normalize(cell.getAttribute("data-text") || cell.textContent);
                    var isVisible = query.length === 0 || text.indexOf(query) !== -1;
                    setVisibility(cell, isVisible);
                    if (isVisible) {
                        visibleCount += 1;
                    }
                });

                setVisibility(entry.section, visibleCount > 0);
            });
        }

        applyFilter();
        input.addEventListener("input", applyFilter);
    }

    function formatTime(timeZone, locale) {
        var formatter = new Intl.DateTimeFormat(locale, {
            timeZone: timeZone,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
        return formatter.format(new Date());
    }

    function formatDate(timeZone, locale) {
        var formatter = new Intl.DateTimeFormat(locale, {
            timeZone: timeZone,
            weekday: "long",
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
        return formatter.format(new Date());
    }

    function fallbackClockTitleFromTimezone(timeZone) {
        if (!timeZone) {
            return "";
        }
        var parts = timeZone.split("/");
        return (parts[parts.length - 1] || "").replace(/_/g, " ");
    }

    function normalizeTimezoneKey(timeZone) {
        return normalizeLookup(timeZone);
    }

    function getWidgetLanguage(widget, fallbackLang) {
        var raw = normalizeLookup(widget.getAttribute("data-lang") || "");
        if (raw.indexOf("en") === 0) {
            return "en";
        }
        if (raw.indexOf("ru") === 0) {
            return "ru";
        }
        return fallbackLang;
    }

    function getWidgetLocale(widget, lang) {
        var explicit = (widget.getAttribute("data-locale") || "").trim();
        if (explicit) {
            return explicit;
        }
        return getLocaleForLanguage(lang);
    }

    function getClockTitle(timeZone, lang, defaultLabel) {
        var labels = CLOCK_CITY_LABELS[normalizeTimezoneKey(timeZone)];
        if (labels && labels[lang]) {
            return labels[lang];
        }
        if (defaultLabel) {
            return defaultLabel;
        }
        return fallbackClockTitleFromTimezone(timeZone);
    }

    function setupClocks() {
        var clocks = Array.prototype.slice.call(document.querySelectorAll(".clock-widget"));
        if (clocks.length === 0) {
            return;
        }

        var pageLang = getPageLanguage();

        function tick() {
            clocks.forEach(function (widget) {
                var timeZone = widget.getAttribute("data-timezone");
                if (!timeZone) {
                    return;
                }
                var lang = getWidgetLanguage(widget, pageLang);
                var locale = getWidgetLocale(widget, lang);

                var timeEl = widget.querySelector(".clock-time");
                var dateEl = widget.querySelector(".clock-date");
                var titleEl = widget.querySelector(".service-title");

                if (titleEl) {
                    var defaultLabel = widget.getAttribute("data-label") || "";
                    titleEl.textContent = getClockTitle(timeZone, lang, defaultLabel);
                }

                if (timeEl) {
                    timeEl.textContent = formatTime(timeZone, locale);
                }
                if (dateEl) {
                    dateEl.textContent = formatDate(timeZone, locale);
                }
            });
        }

        tick();
        window.setInterval(tick, 1000);
    }

    function markBrokenIconImage(img) {
        var wrapper = img.closest(".service-icon-image-mode");
        if (wrapper) {
            wrapper.classList.add("image-failed");
        }
    }

    function setupImageIconFallback() {
        var images = Array.prototype.slice.call(document.querySelectorAll(".service-icon-image-mode .service-icon-image"));
        images.forEach(function (img) {
            img.addEventListener("error", function () {
                markBrokenIconImage(img);
            });
            if (img.complete && img.naturalWidth === 0) {
                markBrokenIconImage(img);
            }
        });
    }

    function detectFontAwesomeLoaded() {
        var probe = document.createElement("i");
        probe.className = "fa fa-envelope-o";
        probe.style.position = "absolute";
        probe.style.visibility = "hidden";
        probe.style.pointerEvents = "none";
        probe.style.left = "-9999px";
        document.body.appendChild(probe);

        var family = "";
        try {
            family = window.getComputedStyle(probe).fontFamily || "";
        } finally {
            probe.remove();
        }

        if (/fontawesome|font awesome/i.test(family)) {
            document.documentElement.classList.add("icon-fa-ready");
        }
    }

    function updateStickyOffset() {
        var root = document.documentElement;
        var topbar = document.querySelector(".topbar");
        if (!topbar) {
            root.style.removeProperty("--time-section-height");
            return;
        }
        var styles = window.getComputedStyle(topbar);
        var marginBottom = parseFloat(styles.marginBottom || "0");
        var extraGap = 10;
        var offset = Math.ceil(topbar.getBoundingClientRect().height + marginBottom + extraGap);
        root.style.setProperty("--sticky-offset", offset + "px");

        var timeSection = document.querySelector(".time-column .section-time");
        if (!timeSection || window.matchMedia("(max-width: 1024px)").matches) {
            root.style.removeProperty("--time-section-height");
            return;
        }

        var viewportHeight = window.innerHeight || root.clientHeight;
        var sectionTop = Math.max(timeSection.getBoundingClientRect().top, 0);
        var bottomGap = 12;
        var availableHeight = Math.floor(viewportHeight - sectionTop - bottomGap);

        if (availableHeight > 0) {
            root.style.setProperty("--time-section-height", availableHeight + "px");
        }
    }

    var stickyUpdateScheduled = false;

    function scheduleStickyOffsetUpdate() {
        if (stickyUpdateScheduled) {
            return;
        }
        stickyUpdateScheduled = true;
        window.requestAnimationFrame(function () {
            stickyUpdateScheduled = false;
            updateStickyOffset();
        });
    }

    function clearConfigReloadQueryParam() {
        if (!window.history || typeof window.history.replaceState !== "function") {
            return;
        }

        var url = new URL(window.location.href);
        if (!url.searchParams.has("config_reload")) {
            return;
        }

        url.searchParams.delete("config_reload");
        var nextUrl = url.pathname;
        var nextQuery = url.searchParams.toString();
        if (nextQuery) {
            nextUrl += "?" + nextQuery;
        }
        if (url.hash) {
            nextUrl += url.hash;
        }
        window.history.replaceState({}, document.title, nextUrl);
    }

    function setupConfigReloadStatusModal() {
        var modal = document.querySelector("[data-config-reload-modal]");
        if (!modal) {
            return;
        }

        var okButton = modal.querySelector("[data-config-reload-ok]");
        if (!okButton) {
            return;
        }

        okButton.addEventListener("click", function () {
            modal.remove();
            clearConfigReloadQueryParam();
        });
        okButton.focus();
    }

    document.addEventListener("DOMContentLoaded", function () {
        setupThemeToggle();
        setupSearch();
        setupClocks();
        setupImageIconFallback();
        setupConfigReloadStatusModal();
        detectFontAwesomeLoaded();
        scheduleStickyOffsetUpdate();
        window.setTimeout(detectFontAwesomeLoaded, 300);
        window.setTimeout(scheduleStickyOffsetUpdate, 120);
        window.addEventListener("resize", scheduleStickyOffsetUpdate);
        window.addEventListener("scroll", scheduleStickyOffsetUpdate, { passive: true });
    });
})();
