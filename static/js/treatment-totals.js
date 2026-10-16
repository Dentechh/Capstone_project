(function () {

    // Balance for one treatment row. A new charge owes (value - paid). A
    // follow-up has no charge of its own: it owes what is left on its plan
    // (row.dataset.planBalance, set by applyPlanMode in app-core.js) minus
    // what is paid today.
    function recalc(row) {
        if (!row) return;
        var valueEl = row.querySelector(".td-value");
        var paidEl = row.querySelector(".td-paid");
        var balEl = row.querySelector(".td-balance");
        if (!valueEl || !paidEl || !balEl) return;

        var value = parseFloat(valueEl.value) || 0;
        var paid = parseFloat(paidEl.value) || 0;
        var planBal = row.dataset.planBalance;
        var base = (planBal !== undefined && planBal !== "") ? (parseFloat(planBal) || 0) : value;
        var balance = base - paid;

        balEl.value = balance.toFixed(2);
        // Paying more than is owed is rejected by the server too; flag it early.
        paidEl.style.outline = balance < -0.005 ? "2px solid #d93025" : "";
    }

    window.tdRecalcBalance = recalc;

    document.addEventListener("input", function (e) {
        if (e.target.classList.contains("td-value") ||
            e.target.classList.contains("td-paid")) {
            recalc(e.target.closest("tr"));
        }
    });

})();