(function () {
    function normalize(value) {
        return (value || "").toLowerCase();
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

    function formatTime(timeZone) {
        var formatter = new Intl.DateTimeFormat("ru-RU", {
            timeZone: timeZone,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
        return formatter.format(new Date());
    }

    function formatDate(timeZone) {
        var formatter = new Intl.DateTimeFormat("ru-RU", {
            timeZone: timeZone,
            weekday: "long",
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
        return formatter.format(new Date());
    }

    function setupClocks() {
        var clocks = Array.prototype.slice.call(document.querySelectorAll(".clock-widget"));
        if (clocks.length === 0) {
            return;
        }

        function tick() {
            clocks.forEach(function (widget) {
                var timeZone = widget.getAttribute("data-timezone");
                if (!timeZone) {
                    return;
                }

                var timeEl = widget.querySelector(".clock-time");
                var dateEl = widget.querySelector(".clock-date");

                if (timeEl) {
                    timeEl.textContent = formatTime(timeZone);
                }
                if (dateEl) {
                    dateEl.textContent = formatDate(timeZone);
                }
            });
        }

        tick();
        window.setInterval(tick, 1000);
    }

    document.addEventListener("DOMContentLoaded", function () {
        setupSearch();
        setupClocks();
    });
})();
