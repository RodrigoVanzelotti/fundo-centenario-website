(() => {
  "use strict";

  const config = window.FUNDO_CONFIG;
  const pix = window.PixPayload;

  const tabs = document.querySelectorAll("[data-donation-tab]");
  const panels = document.querySelectorAll("[data-donation-panel]");
  const amountButtons = document.querySelectorAll("[data-amount]");
  const customAmount = document.getElementById("customAmount");
  const generateButton = document.getElementById("generatePixButton");
  const qrBox = document.getElementById("qrBox");
  const pixCode = document.getElementById("pixCode");
  const copyButton = document.getElementById("copyPixButton");
  const pixStatus = document.getElementById("pixStatus");
  const pixAmountLabel = document.getElementById("pixAmountLabel");
  const autoAmountLabel = document.getElementById("autoAmountLabel");
  const autoButton = document.getElementById("pixAutomaticButton");
  const autoStatus = document.getElementById("autoStatus");
  const autoPill = document.getElementById("autoPill");
  const receiverName = document.querySelectorAll("[data-receiver-name]");

  let selectedAmount = Number(config?.pix?.defaultAmount || 100);

  receiverName.forEach((node) => {
    node.textContent = config?.organization?.legalReceiverName || "Fundo Centenário";
  });

  function formatBRL(value) {
    return Number(value).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  }

  function setStatus(element, message, type = "") {
    if (!element) return;
    element.className = `status-message${type ? ` ${type}` : ""}`;
    element.textContent = message;
  }

  function setSelectedAmount(value, sourceButton = null) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    selectedAmount = Math.round(parsed * 100) / 100;

    amountButtons.forEach((button) => {
      const samePreset = Number(button.dataset.amount) === selectedAmount;
      button.classList.toggle("active", Boolean(sourceButton) && samePreset);
    });
    if (sourceButton && customAmount) customAmount.value = "";

    if (pixCode?.value) {
      pixCode.value = "";
      pixCode.setAttribute("disabled", "");
      copyButton.disabled = true;
      qrBox.innerHTML = '<p class="qr-placeholder">O valor foi alterado. Gere um novo QR Code antes de pagar.</p>';
      setStatus(pixStatus, "Valor alterado. Gere novamente o QR Code Pix.");
    }

    if (pixAmountLabel) pixAmountLabel.textContent = formatBRL(selectedAmount);
    if (autoAmountLabel) autoAmountLabel.textContent = `${formatBRL(selectedAmount)} por mês`;
  }

  function renderQr(payload) {
    qrBox.innerHTML = "";

    if (typeof window.qrcode !== "function") {
      const placeholder = document.createElement("p");
      placeholder.className = "qr-placeholder";
      placeholder.textContent = "A biblioteca visual do QR Code não carregou. Use o Pix Copia e Cola abaixo ou verifique a conexão com a CDN configurada.";
      qrBox.appendChild(placeholder);
      return false;
    }

    const qr = window.qrcode(0, "M");
    qr.addData(payload);
    qr.make();
    qrBox.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 3, scalable: true });
    const svg = qrBox.querySelector("svg");
    if (svg) {
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", `QR Code Pix para doação de ${formatBRL(selectedAmount)}`);
    }
    return true;
  }

  function generatePix() {
    if (!config?.pix?.enabled) {
      setStatus(pixStatus, "Pix ainda não configurado. Edite assets/js/config.js com a chave oficial e altere pix.enabled para true.", "warning");
      return;
    }

    try {
      const txid = pix.generateTxid(config.pix.txidPrefix || "FC");
      const payload = pix.buildStaticPayload({
        key: config.pix.key,
        merchantName: config.pix.merchantName,
        merchantCity: config.pix.merchantCity,
        amount: selectedAmount,
        txid,
      });

      pixCode.value = payload;
      pixCode.removeAttribute("disabled");
      copyButton.disabled = false;
      renderQr(payload);
      setStatus(
        pixStatus,
        `QR Code preparado para ${formatBRL(selectedAmount)}. Confirme no aplicativo do banco o nome do recebedor antes de concluir.`,
        "success"
      );
    } catch (error) {
      setStatus(pixStatus, error.message || "Não foi possível gerar o Pix.", "error");
    }
  }

  async function copyPixCode() {
    if (!pixCode.value) return;
    try {
      await navigator.clipboard.writeText(pixCode.value);
      const original = copyButton.textContent;
      copyButton.textContent = "Código copiado";
      setTimeout(() => {
        copyButton.textContent = original;
      }, 1800);
    } catch {
      pixCode.focus();
      pixCode.select();
      document.execCommand("copy");
    }
  }

  function resolveAutomaticUrl() {
    const auto = config?.pixAutomatico;
    if (!auto?.enabled || !auto?.redirectUrlTemplate) {
      throw new Error("Pix Automático ainda não configurado.");
    }

    const returnUrl = new URL(window.location.href);
    returnUrl.search = "";
    returnUrl.hash = "";
    returnUrl.searchParams.set("origem", "pix-automatico");

    const raw = auto.redirectUrlTemplate
      .replaceAll("{amount}", selectedAmount.toFixed(2))
      .replaceAll("{amountCents}", String(Math.round(selectedAmount * 100)))
      .replaceAll("{returnUrl}", encodeURIComponent(returnUrl.toString()));

    const url = new URL(raw);
    if (url.protocol !== "https:") {
      throw new Error("A URL do Pix Automático precisa usar HTTPS.");
    }

    const allowedHosts = Array.isArray(auto.allowedHosts) ? auto.allowedHosts : [];
    if (!allowedHosts.includes(url.hostname)) {
      throw new Error("Domínio do Pix Automático não está na lista allowedHosts da configuração.");
    }

    return url;
  }

  function updateAutomaticState() {
    const configured = Boolean(
      config?.pixAutomatico?.enabled &&
        config?.pixAutomatico?.redirectUrlTemplate &&
        Array.isArray(config?.pixAutomatico?.allowedHosts) &&
        config.pixAutomatico.allowedHosts.length
    );

    autoButton.disabled = !configured;
    autoPill.textContent = configured ? "Integração pronta" : "Configuração pendente";
    autoPill.classList.toggle("ready", configured);

    setStatus(
      autoStatus,
      configured
        ? "Ao continuar, você será redirecionado ao ambiente oficial configurado do banco ou PSP para autorizar a recorrência."
        : "Para habilitar esta opção, configure uma URL pública de autorização hospedada pelo banco/PSP em assets/js/config.js. Nenhuma credencial secreta deve ser colocada no navegador.",
      configured ? "success" : "warning"
    );
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.donationTab;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.donationPanel !== target;
      });
    });
  });

  amountButtons.forEach((button) => {
    button.addEventListener("click", () => setSelectedAmount(button.dataset.amount, button));
  });

  customAmount?.addEventListener("input", () => {
    const normalized = customAmount.value.replace(",", ".");
    const parsed = Number(normalized);
    if (Number.isFinite(parsed) && parsed > 0) {
      setSelectedAmount(parsed, null);
      amountButtons.forEach((button) => button.classList.remove("active"));
    }
  });

  generateButton?.addEventListener("click", generatePix);
  copyButton?.addEventListener("click", copyPixCode);

  autoButton?.addEventListener("click", () => {
    try {
      const url = resolveAutomaticUrl();
      window.location.assign(url.toString());
    } catch (error) {
      setStatus(autoStatus, error.message || "Não foi possível iniciar o Pix Automático.", "error");
    }
  });

  setSelectedAmount(selectedAmount, document.querySelector(`[data-amount="${selectedAmount}"]`));
  updateAutomaticState();

  if (!config?.pix?.enabled) {
    generateButton.disabled = true;
    setStatus(pixStatus, "Pix pontual pronto para integração. Configure a chave oficial em assets/js/config.js para habilitar a geração do QR Code.", "warning");
  } else {
    generatePix();
  }
})();
