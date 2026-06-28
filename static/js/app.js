(function () {
    const timeoutForm = document.querySelector("#timeout-form");
    if (timeoutForm && window.SSP_SESSION_TIMEOUT_MS) {
        let timeoutId;
        const resetTimeout = function () {
            window.clearTimeout(timeoutId);
            timeoutId = window.setTimeout(function () {
                timeoutForm.submit();
            }, window.SSP_SESSION_TIMEOUT_MS);
        };

        ["click", "keydown", "mousemove", "scroll", "touchstart", "change", "input"].forEach(function (eventName) {
            document.addEventListener(eventName, resetTimeout, { passive: true });
        });

        resetTimeout();
    }

    const costForm = document.querySelector("[data-cost-form='true']");
    if (costForm) {
        const environment = costForm.querySelector("[data-cost-environment]");
        const startDate = costForm.querySelector("#start_date");
        const endDate = costForm.querySelector("#end_date");
        const display = costForm.querySelector("[data-cost-display]");

        const formatCurrency = new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0
        });

        const updateCost = function () {
            const selectedOption = environment.options[environment.selectedIndex];
            const dailyCost = Number(selectedOption.dataset.dailyCost || 0);
            const start = startDate.value ? new Date(startDate.value + "T00:00:00") : null;
            const end = endDate.value ? new Date(endDate.value + "T00:00:00") : null;

            if (!dailyCost || !start || !end || end < start) {
                display.textContent = "Choose dates and environment";
                return;
            }

            const days = Math.round((end - start) / 86400000) + 1;
            display.textContent = formatCurrency.format(days * dailyCost) + " for " + days + " day" + (days > 1 ? "s" : "");
        };

        ["change", "input"].forEach(function (eventName) {
            environment.addEventListener(eventName, updateCost);
            startDate.addEventListener(eventName, updateCost);
            endDate.addEventListener(eventName, updateCost);
        });
        updateCost();
    }

    const envType = document.querySelector("#environment_type");
    const mainframeEnv = document.querySelector("[data-mainframe-environment]");
    if (envType && mainframeEnv && window.SSP_ENVIRONMENTS) {
        const renderOptions = function () {
            const type = envType.value;
            const options = type === "Production" ? window.SSP_ENVIRONMENTS.production : window.SSP_ENVIRONMENTS.test;
            const selected = window.SSP_ENVIRONMENTS.selected;
            mainframeEnv.innerHTML = "";

            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = type ? "Select environment" : "Select environment type first";
            mainframeEnv.appendChild(placeholder);

            if (!type) {
                return;
            }

            options.forEach(function (item) {
                const option = document.createElement("option");
                option.value = item;
                option.textContent = item;
                option.selected = selected === item;
                mainframeEnv.appendChild(option);
            });
        };

        envType.addEventListener("change", renderOptions);
        renderOptions();
    }
})();
