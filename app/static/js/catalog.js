(function () {
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

    function setupSearch() {
        var input = document.getElementById("serviceSearch");
        if (!input) {
            return;
        }

        var serviceCells = Array.prototype.slice.call(document.querySelectorAll("[data-service]"));
        var sections = Array.prototype.slice.call(document.querySelectorAll("[data-section]"));

        function applyFilter() {
            var query = normalize(input.value.trim());

            serviceCells.forEach(function (cell) {
                var text = normalize(cell.getAttribute("data-text") || cell.textContent);
                var visible = query.length === 0 || text.indexOf(query) !== -1;
                cell.style.display = visible ? "" : "none";
            });

            sections.forEach(function (section) {
                var visibleCells = section.querySelectorAll("[data-service]:not([style*='display: none'])");
                section.style.display = visibleCells.length > 0 ? "" : "none";
            });
        }

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
        var topbar = document.querySelector(".topbar");
        if (!topbar) {
            return;
        }
        var styles = window.getComputedStyle(topbar);
        var marginBottom = parseFloat(styles.marginBottom || "0");
        var extraGap = 10;
        var offset = Math.ceil(topbar.getBoundingClientRect().height + marginBottom + extraGap);
        document.documentElement.style.setProperty("--sticky-offset", offset + "px");
    }

    document.addEventListener("DOMContentLoaded", function () {
        setupSearch();
        setupClocks();
        setupImageIconFallback();
        detectFontAwesomeLoaded();
        updateStickyOffset();
        window.setTimeout(detectFontAwesomeLoaded, 300);
        window.setTimeout(updateStickyOffset, 120);
        window.addEventListener("resize", updateStickyOffset);
    });
})();
