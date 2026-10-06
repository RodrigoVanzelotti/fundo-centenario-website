(() => {
  "use strict";

  const config = window.FUNDO_CONFIG || {};
  const apiBase = String(config.apiBaseUrl || "").replace(/\/$/, "");
  const pollInterval = Number(config?.donation?.pollIntervalMs || 2500);
  const storageKey = "fundoCentenarioDonationSessionV2";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const form = $("#donationQuestionnaire");
  const detailsStage = $("#detailsStage");
  const contributionStep = $("#contributionStep");
  const donorStep = $("#donorStep");
  const backButton = $("#backToContribution");
  const submitButton = form.querySelector("button[type='submit']");
  let currentStage = "contribution";
  const paymentStage = $("#paymentStage");
  const successStage = $("#successStage");
  const formStatus = $("#formStatus");
  const customAmount = $("#customAmount");
  const amountButtons = $$(".amount-button");
  const methodOptions = $$(".payment-method-option");
  const qrBox = $("#qrBox");
  const pixCode = $("#pixCode");
  const copyPixButton = $("#copyPixButton");
  const mockConfirmButton = $("#mockConfirmButton");
  const pixPaymentView = $("#pixPaymentView");
  const redirectPaymentView = $("#redirectPaymentView");
  const redirectButton = $("#redirectButton");
  const paymentStatusMessage = $("#paymentStatusMessage");

  let selectedAmount = Number(config?.donation?.defaultAmount || 100);
  let activeSession = readSession();
  let pollTimer = null;
  let polling = false;
  let mockConfirmUrl = null;

  function formatBRL(value) {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
  }

  function setFormError(message) {
    if (!message) {
      formStatus.hidden = true;
      formStatus.textContent = "";
      return;
    }
    formStatus.hidden = false;
    formStatus.textContent = message;
  }

  function readSession() {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey) || "null");
    } catch {
      return null;
    }
  }

  function writeSession(data) {
    activeSession = { ...(activeSession || {}), ...data };
    sessionStorage.setItem(storageKey, JSON.stringify(activeSession));
  }

  function clearSession() {
    activeSession = null;
    sessionStorage.removeItem(storageKey);
  }

  function normalizeCpf(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function formatCpf(value) {
    const digits = normalizeCpf(value).slice(0, 11);
    return digits
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function validCpf(value) {
    const cpf = normalizeCpf(value);
    if (!/^\d{11}$/.test(cpf) || /^(\d)\1{10}$/.test(cpf)) return false;
    const calc = (base, factor) => {
      let total = 0;
      for (const char of base) total += Number(char) * factor--;
      const digit = (total * 10) % 11;
      return digit === 10 ? 0 : digit;
    };
    const first = calc(cpf.slice(0, 9), 10);
    const second = calc(cpf.slice(0, 9) + first, 11);
    return cpf.endsWith(`${first}${second}`);
  }

  function setAmount(value, sourceButton = null) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    selectedAmount = Math.round(parsed * 100) / 100;
    amountButtons.forEach((button) => button.classList.toggle("active", button === sourceButton));
    if (sourceButton && customAmount) customAmount.value = "";
  }

  function selectedMethod() {
    return form?.elements?.method?.value || "pix";
  }

  function selectedProgram() {
    return form?.elements?.program?.value || "geral";
  }

  function questionnaire() {
    return {
      name: $("#donorName").value.trim(),
      email: $("#donorEmail").value.trim(),
      cpf: normalizeCpf($("#donorCpf").value),
      communication_opt_in: $("#communicationOptIn").checked,
    };
  }

  function validateContribution() {
    if (customAmount.value !== "" || customAmount.validity.badInput) {
      if (!customAmount.reportValidity()) return "Informe um valor de contribuição válido.";
      setAmount(customAmount.value);
    }
    if (!Number.isFinite(selectedAmount) || selectedAmount < 1 || selectedAmount > 1000000) {
      return "Informe um valor entre R$ 1,00 e R$ 1.000.000,00.";
    }
    return null;
  }

  function validateQuestionnaire() {
    if (!form.reportValidity()) return "Revise os campos obrigatórios antes de continuar.";
    if (!validCpf($("#donorCpf").value)) return "Informe um CPF válido.";
    return validateContribution();
  }

  function setProgress(stage) {
    const order = { contribution: 0, details: 1, payment: 2, done: 3 };
    $$(".donation-progress-item").forEach((item) => {
      const itemIndex = order[item.dataset.progress];
      item.classList.toggle("active", itemIndex <= order[stage]);
      item.classList.toggle("current", item.dataset.progress === stage);
      if (item.dataset.progress === stage) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }

  function showStage(stage) {
    currentStage = stage;
    detailsStage.hidden = stage !== "contribution" && stage !== "details";
    contributionStep.hidden = stage !== "contribution";
    donorStep.hidden = stage !== "details";
    donorStep.disabled = stage !== "details";
    backButton.hidden = stage !== "details";
    submitButton.textContent = stage === "contribution" ? "Continuar" : "Continuar para pagamento";
    if (stage === "details") {
      const methodLabel = { pix: "Pix pontual", pix_automatico: "Pix Automático mensal", card: "Cartão de crédito", card_recurring: "Contribuição mensal no cartão" };
      $("#contributionSummary").textContent = `${formatBRL(selectedAmount)} · ${methodLabel[selectedMethod()]}`;
    }
    paymentStage.hidden = stage !== "payment";
    successStage.hidden = stage !== "done";
    setProgress(stage);
    const visibleStage = stage === "contribution" ? contributionStep : stage === "details" ? donorStep : stage === "payment" ? paymentStage : successStage;
    visibleStage.querySelector("h2")?.focus({ preventScroll: true });
    window.scrollTo({ top: Math.max(0, document.querySelector("#contribuir").offsetTop - 90), behavior: "smooth" });
  }

  async function api(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => item.msg).join(" ")
        : payload.detail;
      throw new Error(detail || "Não foi possível concluir a operação.");
    }
    return payload;
  }

  async function loadPaymentOptions() {
    submitButton.disabled = true;
    try {
      const options = await api("/api/donations/options");
      if (!Array.isArray(options.methods) || !options.methods.length) throw new Error("Nenhuma forma de contribuição disponível.");
      methodOptions.forEach((option) => {
        const radio = option.querySelector("input");
        radio.disabled = !options.methods.includes(radio.value);
        option.hidden = radio.disabled;
        option.classList.remove("selected");
      });
      const available = form.querySelector("input[name='method']:not(:disabled)");
      if (!available) throw new Error("Nenhuma forma de contribuição disponível.");
      if (!form.querySelector("input[name='method']:checked:not(:disabled)")) available.checked = true;
      submitButton.disabled = false;
    } catch {
      setFormError("Não foi possível carregar as formas de contribuição. Recarregue a página para tentar novamente.");
    }
  }

  function renderQr(copyPaste, qrBase64) {
    qrBox.innerHTML = "";
    if (qrBase64) {
      const image = document.createElement("img");
      image.alt = `QR Code Pix para contribuição de ${formatBRL(selectedAmount)}`;
      image.src = qrBase64.startsWith("data:") ? qrBase64 : `data:image/png;base64,${qrBase64}`;
      qrBox.appendChild(image);
      return;
    }
    qrBox.innerHTML = '<p class="qr-placeholder">O PSP não forneceu uma imagem do QR Code. Use o Pix Copia e Cola abaixo.</p>';
  }

  async function createIntent() {
    const donor = questionnaire();
    const payload = {
      donor,
      program: selectedProgram(),
      method: selectedMethod(),
      amount_cents: Math.round(selectedAmount * 100),
    };

    const fingerprint = JSON.stringify([payload.amount_cents, payload.method, payload.program]);
    if (activeSession?.fingerprint !== fingerprint) clearSession();
    const idempotencyKey = activeSession?.idempotency_key || crypto.randomUUID();
    writeSession({ donor, fingerprint, idempotency_key: idempotencyKey });

    const response = await api("/api/donations/intents", {
      method: "POST",
      headers: { "X-Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });

    writeSession({
      donor,
      program: payload.program,
      method: payload.method,
      amount_cents: payload.amount_cents,
      donation_id: response.donation_id,
      status_token: response.status_token,
      program_label: response.program_label,
      payment: response,
      saved_at: Date.now(),
    });

    showStage("payment");
    renderPayment(response);
    startPolling();
  }

  function renderPayment(response) {
    selectedAmount = response.amount_cents / 100;
    $("#pixAmountLabel").textContent = formatBRL(selectedAmount);
    mockConfirmUrl = response.mock_confirm_url || null;
    mockConfirmButton.hidden = !mockConfirmUrl;

    if (response.pix_copy_paste && (response.method === "pix" || response.method === "pix_automatico")) {
      const automatic = response.method === "pix_automatico";
      $("#paymentStageTitle").textContent = automatic
        ? "Escaneie o QR Code para autorizar o Pix Automático."
        : "Escaneie o QR Code e confirme no seu banco.";
      $("#paymentStageCopy").textContent = automatic
        ? "A autorização acontece no ambiente bancário. Os dados só serão gravados após a confirmação de um pagamento."
        : "A página será atualizada automaticamente quando o PSP confirmar a transação.";
      pixPaymentView.hidden = false;
      pixCode.value = response.pix_copy_paste || "";
      renderQr(response.pix_copy_paste, response.pix_qr_base64);
      if (automatic && response.redirect_url) {
        redirectPaymentView.hidden = false;
        redirectButton.href = response.redirect_url;
        $("#redirectTitle").textContent = "Prefere continuar no ambiente do PSP?";
        $("#redirectCopy").textContent = "Você também pode abrir diretamente a experiência de autorização oferecida pelo provedor.";
      } else {
        redirectPaymentView.hidden = true;
      }
      return;
    }

    pixPaymentView.hidden = true;
    redirectPaymentView.hidden = false;
    redirectButton.href = response.redirect_url || "#";
    const auto = response.method === "pix_automatico";
    const monthlyCard = response.method === "card_recurring";
    $("#paymentStageTitle").textContent = auto ? "Autorize o Pix Automático no ambiente do PSP." : monthlyCard ? "Autorize sua contribuição mensal no checkout seguro." : "Finalize o pagamento no checkout seguro do PSP.";
    $("#paymentStageCopy").textContent = auto
      ? "A recorrência é criada pelo backend e autorizada no ambiente bancário."
      : monthlyCard ? `Sua contribuição de ${formatBRL(selectedAmount)} será cobrada todo mês. O Fundo não recebe os dados do cartão.` : response.method === "pix" ? "O QR Code e o código Pix serão exibidos no ambiente seguro do provedor." : "O Fundo não coleta número de cartão, validade ou CVV.";
    $("#redirectTitle").textContent = auto ? "Continuar para autorização do Pix Automático" : monthlyCard ? "Autorizar contribuição mensal" : response.method === "pix" ? "Continuar para pagamento Pix" : "Continuar para o checkout de cartão";
    $("#redirectCopy").textContent = auto
      ? "Você será encaminhado ao ambiente do PSP para revisar e autorizar a recorrência."
      : monthlyCard ? "Revise o valor mensal e autorize a cobrança recorrente no checkout do provedor. O primeiro pagamento será confirmado pelo PSP." : response.method === "pix" ? "Escaneie o QR Code ou copie o código no checkout do provedor." : "Os dados do cartão serão tratados exclusivamente pelo checkout hospedado do PSP.";
    if (response.redirect_url) {
      setTimeout(() => {
        if (!document.hidden) window.location.assign(response.redirect_url);
      }, 1200);
    }
  }

  async function getStatus() {
    if (!activeSession?.donation_id || !activeSession?.status_token) return null;
    return api(`/api/donations/${encodeURIComponent(activeSession.donation_id)}/status`, {
      method: "GET",
      headers: { "X-Donation-Token": activeSession.status_token },
    });
  }

  async function finalizeIfNecessary(statusData) {
    if (statusData.persisted || !activeSession?.donor) return statusData;
    return api(`/api/donations/${encodeURIComponent(activeSession.donation_id)}/finalize`, {
      method: "POST",
      headers: { "X-Donation-Token": activeSession.status_token },
      body: JSON.stringify({ donor: activeSession.donor }),
    });
  }

  function firstName(name) {
    return String(name || "").trim().split(/\s+/)[0] || "";
  }

  async function showSuccess(statusData) {
    const finalStatus = await finalizeIfNecessary(statusData);
    stopPolling();
    const donorFirstName = firstName(activeSession?.donor?.name);
    $("#successTitle").textContent = donorFirstName
      ? `Muito obrigado, ${donorFirstName}! Sua contribuição foi confirmada.`
      : "Muito obrigado! Sua contribuição foi confirmada.";
    $("#successMessage").textContent = `Seu apoio ao ${finalStatus.program_label} ajuda o Fundo Centenário a transformar recursos em oportunidades para a comunidade da Escola de Engenharia.`;
    $("#successAmount").textContent = formatBRL(finalStatus.amount_cents / 100);
    $("#successProgram").textContent = finalStatus.program_label;
    showStage("done");
    clearSession();
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("donation_id");
    history.replaceState({}, "", cleanUrl.pathname + cleanUrl.hash);
  }

  async function pollOnce() {
    if (polling) return;
    polling = true;
    try {
      const statusData = await getStatus();
      if (!statusData) return;
      paymentStatusMessage.textContent = statusData.message;
      if (statusData.status === "paid") {
        await showSuccess(statusData);
      }
    } catch (error) {
      paymentStatusMessage.textContent = error.message || "Não foi possível consultar o pagamento agora. Tentaremos novamente.";
    } finally {
      polling = false;
    }
  }

  function startPolling() {
    stopPolling();
    pollOnce();
    pollTimer = window.setInterval(pollOnce, pollInterval);
  }

  function stopPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  async function restoreReturnFlow() {
    const url = new URL(window.location.href);
    const donationId = url.searchParams.get("donation_id");
    if (!donationId && !activeSession?.donation_id) return false;
    if (!activeSession?.status_token || (donationId && activeSession.donation_id !== donationId)) {
      setFormError("O PSP retornou ao site, mas esta sessão não possui os dados necessários para consultar a contribuição. Se o pagamento foi concluído, entre em contato com o Fundo informando a referência exibida pelo PSP.");
      url.searchParams.delete("donation_id");
      history.replaceState({}, "", url.pathname + url.search + url.hash);
      return false;
    }
    showStage("payment");
    pixPaymentView.hidden = true;
    redirectPaymentView.hidden = true;
    $("#paymentStageTitle").textContent = "Verificando sua contribuição...";
    $("#paymentStageCopy").textContent = "Estamos consultando a confirmação recebida do PSP.";
    if (!donationId && activeSession.payment) {
      renderPayment({ ...activeSession.payment, redirect_url: null });
      if (activeSession.payment.redirect_url) {
        redirectPaymentView.hidden = false;
        redirectButton.href = activeSession.payment.redirect_url;
      }
    }
    await pollOnce();
    if (!successStage.hidden) return true;
    startPolling();
    return true;
  }

  ["input", "change", "click", "reset"].forEach((type) => {
    form.addEventListener(type, () => setFormError(""));
  });

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) setFormError("");
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    setFormError("");
    if (currentStage === "contribution") {
      const error = validateContribution();
      if (error) setFormError(error);
      else showStage("details");
      return;
    }
    const validationError = validateQuestionnaire();
    if (validationError) {
      setFormError(validationError);
      return;
    }
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    backButton.disabled = true;
    submit.textContent = "Preparando pagamento...";
    try {
      await createIntent();
    } catch (error) {
      setFormError(error.message || "Não foi possível iniciar a contribuição.");
    } finally {
      submit.disabled = false;
      backButton.disabled = false;
      submit.textContent = "Continuar para pagamento";
    }
  });

  backButton.addEventListener("click", () => {
    setFormError("");
    showStage("contribution");
  });

  $("#donorCpf")?.addEventListener("input", (event) => {
    event.target.value = formatCpf(event.target.value);
  });

  amountButtons.forEach((button) => {
    button.addEventListener("click", () => setAmount(button.dataset.amount, button));
  });

  customAmount?.addEventListener("input", () => {
    const parsed = Number(String(customAmount.value).replace(",", "."));
    if (Number.isFinite(parsed) && parsed > 0) {
      setAmount(parsed, null);
      amountButtons.forEach((button) => button.classList.remove("active"));
    }
  });

  copyPixButton?.addEventListener("click", async () => {
    if (!pixCode.value) return;
    try {
      await navigator.clipboard.writeText(pixCode.value);
      copyPixButton.textContent = "Código copiado";
      setTimeout(() => (copyPixButton.textContent = "Copiar código Pix"), 1600);
    } catch {
      pixCode.select();
      document.execCommand("copy");
    }
  });

  mockConfirmButton?.addEventListener("click", async () => {
    if (!mockConfirmUrl) return;
    mockConfirmButton.disabled = true;
    mockConfirmButton.textContent = "Confirmando...";
    try {
      await api(mockConfirmUrl, { method: "POST" });
      await pollOnce();
    } catch (error) {
      paymentStatusMessage.textContent = error.message || "Não foi possível simular a confirmação.";
      mockConfirmButton.disabled = false;
      mockConfirmButton.textContent = "Simular confirmação";
    }
  });

  redirectButton?.addEventListener("click", (event) => {
    if (!redirectButton.href || redirectButton.getAttribute("href") === "#") event.preventDefault();
  });

  setAmount(selectedAmount, document.querySelector(`[data-amount="${selectedAmount}"]`));
  setProgress("contribution");
  setFormError("");
  restoreReturnFlow().then((restored) => {
    if (!restored) loadPaymentOptions();
  });
})();
