const assert = require("assert");
const { buildStaticPayload } = require("../assets/js/pix.js");

const actual = buildStaticPayload({
  key: "123e4567-e12b-12d1-a456-426655440000",
  merchantName: "Fulano de Tal",
  merchantCity: "BRASILIA",
  txid: "***",
});

const expected =
  "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D";

assert.strictEqual(actual, expected);

console.log("OK: payload idêntico ao exemplo oficial de QR Code Pix estático.");
console.log(actual);
