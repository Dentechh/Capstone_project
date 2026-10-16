(function () {
    var QR_MAX_BYTES = 300 * 1024;
    var saving = false;

    function csrfHeaders() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? { "X-CSRFToken": meta.content } : {};
    }

    function msg(text) {
        var el = document.getElementById("psMsg");
        if (el) el.textContent = text || "";
    }

    function setPreview(card, src) {
        var box = card.querySelector(".ps-qr-box");
        box.textContent = "";
        if (src && /^(data:image\/(png|jpeg|webp);base64,|blob:)/.test(src)) {
            var img = document.createElement("img");
            img.alt = "QR code preview";
            img.src = src;
            box.appendChild(img);
        } else {
            var empty = document.createElement("div");
            empty.className = "ps-qr-empty";
            empty.textContent = "No QR image uploaded";
            box.appendChild(empty);
        }
    }

    function field(card, labelText, name, value) {
        var label = document.createElement("label");
        label.textContent = labelText;
        var input = document.createElement("input");
        input.type = "text";
        input.name = name;
        input.maxLength = 80;
        input.autocomplete = "off";
        input.value = value || "";
        label.appendChild(input);
        card.appendChild(label);
    }

    function renderChannels(channels) {
        var grid = document.getElementById("psChannels");
        grid.textContent = "";

        channels.forEach(function (c) {
            var card = document.createElement("div");
            card.className = "ps-channel";
            card.dataset.key = c.key;

            var h = document.createElement("h4");
            h.textContent = c.label;
            card.appendChild(h);

            field(card, "Account name", "account_name", c.account_name);
            field(card, "Account number", "account_number", c.account_number);

            var fileLabel = document.createElement("label");
            fileLabel.textContent = "QR image";
            var file = document.createElement("input");
            file.type = "file";
            file.name = "qr";
            file.accept = "image/png,image/jpeg,image/webp";
            fileLabel.appendChild(file);
            card.appendChild(fileLabel);

            var box = document.createElement("div");
            box.className = "ps-qr-box";
            card.appendChild(box);
            setPreview(card, c.qr_image);

            var rmLabel = document.createElement("label");
            rmLabel.className = "ps-remove";
            var rm = document.createElement("input");
            rm.type = "checkbox";
            rm.name = "remove_qr";
            rmLabel.appendChild(rm);
            rmLabel.appendChild(document.createTextNode(" Remove current QR"));
            card.appendChild(rmLabel);

            file.addEventListener("change", function () {
                var f = file.files && file.files[0];
                if (!f) { setPreview(card, c.qr_image); return; }
                if (f.size > QR_MAX_BYTES) {
                    msg(c.label + " QR is larger than 300 KB. Please choose a smaller image.");
                    file.value = "";
                    setPreview(card, c.qr_image);
                    return;
                }
                msg("");
                rm.checked = false;
                setPreview(card, URL.createObjectURL(f));
            });
            rm.addEventListener("change", function () {
                if (rm.checked) { file.value = ""; setPreview(card, ""); }
                else setPreview(card, c.qr_image);
            });

            grid.appendChild(card);
        });
    }

    window.openPaymentSettings = async function () {
        var modal = document.getElementById("paymentSettingsModal");
        if (!modal) return;
        modal.style.display = "flex";
        msg("Loading...");
        document.getElementById("psChannels").textContent = "";
        try {
            var res = await fetch("/admin/payment_settings", { headers: csrfHeaders() });
            var data = await res.json();
            if (!data.success) { msg(data.message || "Could not load payment settings."); return; }
            msg("");
            renderChannels(data.channels || []);
        } catch (err) {
            console.error("Load payment settings error:", err);
            msg("Could not load payment settings.");
        }
    };

    window.closePaymentSettings = function () {
        var modal = document.getElementById("paymentSettingsModal");
        if (modal) modal.style.display = "none";
    };

    window.savePaymentSettings = async function () {
        if (saving) return;
        var btn = document.getElementById("psSaveBtn");
        var cards = document.querySelectorAll("#psChannels .ps-channel");
        if (!cards.length) return;

        var fd = new FormData();
        cards.forEach(function (card) {
            var key = card.dataset.key;
            fd.append(key + "_account_name", card.querySelector('[name="account_name"]').value.trim());
            fd.append(key + "_account_number", card.querySelector('[name="account_number"]').value.trim());
            var f = card.querySelector('[name="qr"]').files[0];
            if (f) fd.append(key + "_qr", f);
            if (card.querySelector('[name="remove_qr"]').checked) fd.append(key + "_remove_qr", "1");
        });

        saving = true;
        btn.disabled = true;
        msg("Saving...");
        try {
            var res = await fetch("/admin/payment_settings", { method: "POST", body: fd, headers: csrfHeaders() });
            var data = await res.json();
            if (data.success) {
                renderChannels(data.channels || []);
                msg("");
                if (typeof showToast === "function") showToast(data.message || "Payment settings saved.");
            } else {
                msg(data.message || "Could not save payment settings.");
            }
        } catch (err) {
            console.error("Save payment settings error:", err);
            msg("Could not save payment settings. Please try again.");
        } finally {
            saving = false;
            btn.disabled = false;
        }
    };

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") window.closePaymentSettings();
    });
})();