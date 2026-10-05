/*
 * CONFIGURAÇÃO PÚBLICA DO FRONTEND
 *
 * Este arquivo é público. Não coloque segredos, tokens privados, API keys,
 * client_secret, certificados ou credenciais bancárias aqui.
 */
window.FUNDO_CONFIG = Object.freeze({
  apiBaseUrl: "",
  organization: {
    displayName: "Fundo Centenário",
    legalReceiverName: "Associação Fundo Patrimonial Escola de Engenharia",
  },
  donation: {
    defaultAmount: 100,
    pollIntervalMs: 2500,
  },
});
