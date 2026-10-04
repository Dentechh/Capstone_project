            document.addEventListener("input", function (e) {

                if (e.target.classList.contains("td-value") ||
                    e.target.classList.contains("td-paid")) {

                    let row = e.target.closest("tr");

                    let value = parseFloat(row.querySelector(".td-value").value) || 0;
                    let paid = parseFloat(row.querySelector(".td-paid").value) || 0;

                    row.querySelector(".td-balance").value = (value - paid).toFixed(2);
                }

            });
