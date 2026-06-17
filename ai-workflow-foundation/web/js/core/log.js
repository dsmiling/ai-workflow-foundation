import { $ } from "./dom.js";

export function setLog(message) {
  $("log").textContent = message;
}
