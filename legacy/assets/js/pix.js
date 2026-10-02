(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.PixPayload = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const GUI = "br.gov.bcb.pix";
  const COUNTRY = "BR";
  const CURRENCY_BRL = "986";

  function field(id, value) {
    const str = String(value);
    if (str.length > 99) {
      throw new Error(`Campo ${id} excede 99 caracteres.`);
    }
    return `${id}${String(str.length).padStart(2, "0")}${str}`;
  }

  function sanitizeEmvText(value, maxLength) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^A-Za-z0-9 $%*+\-./:]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, maxLength);
  }

  function normalizeAmount(amount) {
    const number = Number(amount);
    if (!Number.isFinite(number) || number <= 0) {
      throw new Error("Informe um valor de doação maior que zero.");
    }
    if (number > 999999999.99) {
      throw new Error("Valor fora do limite suportado pelo BR Code.");
    }
    return number.toFixed(2);
  }

  function normalizeTxid(txid) {
    const normalized = String(txid || "***");
    if (normalized === "***") return normalized;
    if (!/^[A-Za-z0-9]{1,25}$/.test(normalized)) {
      throw new Error("txid deve conter apenas letras e números e ter até 25 caracteres.");
    }
    return normalized;
  }

  function crc16CcittFalse(payload) {
    let crc = 0xffff;
    const polynomial = 0x1021;

    for (let index = 0; index < payload.length; index += 1) {
      crc ^= payload.charCodeAt(index) << 8;
      for (let bit = 0; bit < 8; bit += 1) {
        crc = (crc & 0x8000) !== 0 ? ((crc << 1) ^ polynomial) & 0xffff : (crc << 1) & 0xffff;
      }
    }

    return crc.toString(16).toUpperCase().padStart(4, "0");
  }

  function generateTxid(prefix = "FC") {
    const safePrefix = String(prefix)
      .replace(/[^A-Za-z0-9]/g, "")
      .slice(0, 6) || "FC";
    const timePart = Date.now().toString(36).toUpperCase();
    const randomPart = Math.random().toString(36).slice(2, 8).toUpperCase();
    return `${safePrefix}${timePart}${randomPart}`.slice(0, 25);
  }

  function buildStaticPayload({ key, merchantName, merchantCity, amount, txid = "***" }) {
    const pixKey = String(key || "").trim();
    if (!pixKey || pixKey === "SUBSTITUA_PELA_CHAVE_PIX_OFICIAL") {
      throw new Error("Chave Pix oficial ainda não foi configurada.");
    }

    const name = sanitizeEmvText(merchantName, 25);
    const city = sanitizeEmvText(merchantCity, 15);
    if (!name) throw new Error("Merchant Name não configurado.");
    if (!city) throw new Error("Merchant City não configurada.");

    const merchantAccount = field("00", GUI) + field("01", pixKey);
    const additionalData = field("05", normalizeTxid(txid));

    let payload = "";
    payload += field("00", "01");
    payload += field("26", merchantAccount);
    payload += field("52", "0000");
    payload += field("53", CURRENCY_BRL);
    if (amount !== undefined && amount !== null && amount !== "") {
      payload += field("54", normalizeAmount(amount));
    }
    payload += field("58", COUNTRY);
    payload += field("59", name);
    payload += field("60", city);
    payload += field("62", additionalData);
    payload += "6304";
    payload += crc16CcittFalse(payload);

    return payload;
  }

  return Object.freeze({
    buildStaticPayload,
    crc16CcittFalse,
    generateTxid,
    normalizeAmount,
    sanitizeEmvText,
  });
});
