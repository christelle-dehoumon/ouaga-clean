// Outils d'interface communs : création sûre d'éléments (textContent, jamais innerHTML avec des données),
// messages, confirmation, bandeau du mode démonstration, formats français.

/** el("div", {class: "x", onclick}, ["texte", autreElement]) : le texte passe toujours par textContent. */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "text") node.textContent = String(v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export const $ = (sel, root = document) => root.querySelector(sel);

const NF = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const NF0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
export const fmt = {
  n: (v, d = 1) => (Number.isFinite(Number(v)) ? new Intl.NumberFormat("fr-FR", { maximumFractionDigits: d }).format(Number(v)) : "—"),
  int: (v) => (Number.isFinite(Number(v)) ? NF0.format(Number(v)) : "—"),
  pct: (v, d = 0) => (Number.isFinite(Number(v)) ? `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: d }).format(Number(v) * 100)} %` : "—"),
  fcfa: (v) => (Number.isFinite(Number(v)) ? `${NF0.format(Number(v))} FCFA` : "—"),
  t: (kg) => (Number.isFinite(Number(kg)) ? `${NF.format(Number(kg) / 1000)} t` : "—"),
  date: (iso) => {
    const d = iso ? new Date(iso) : null;
    return d && !Number.isNaN(d.getTime())
      ? d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
      : "—";
  },
  ms: (v) => (Number.isFinite(Number(v)) ? (Number(v) >= 1000 ? `${NF.format(Number(v) / 1000)} s` : `${NF0.format(Number(v))} ms`) : "—"),
};

/** Message temporaire en bas d'écran (type : info | ok | erreur). */
export function toast(message, type = "info", ms = 4200) {
  let host = document.getElementById("toasts");
  if (!host) {
    host = el("div", { id: "toasts", class: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(host);
  }
  const t = el("div", { class: `toast toast-${type}` }, [message]);
  host.append(t);
  setTimeout(() => t.remove(), ms);
}

/** Confirmation dans la page (pas de window.confirm) ; résout true / false. */
export function confirmDialog({ title, message, confirm = "Confirmer", cancel = "Annuler", danger = false }) {
  return new Promise((resolve) => {
    const close = (v) => { overlay.remove(); resolve(v); };
    const ok = el("button", { class: `btn ${danger ? "btn-danger" : "btn-primary"}`, onclick: () => close(true) }, [confirm]);
    const overlay = el("div", { class: "modal-overlay", role: "dialog", "aria-modal": "true" }, [
      el("div", { class: "modal" }, [
        el("h2", {}, [title]),
        el("p", {}, [message]),
        el("div", { class: "modal-actions" }, [
          el("button", { class: "btn", onclick: () => close(false) }, [cancel]), ok,
        ]),
      ]),
    ]);
    overlay.addEventListener("keydown", (e) => { if (e.key === "Escape") close(false); });
    document.body.append(overlay);
    ok.focus();
  });
}

/** Bandeau permanent du mode démonstration. */
export function mockBanner() {
  if (document.getElementById("bandeau-demo")) return;
  document.body.prepend(el("div", { id: "bandeau-demo", class: "bandeau-demo", role: "status" },
    ["MODE DÉMONSTRATION — DONNÉES FICTIVES"]));
  document.body.classList.add("mode-demo");
}

/** Demande un code de rôle dans la page ; résout le code saisi ou null. */
export function askCode({ role, title, hint }) {
  return new Promise((resolve) => {
    const input = el("input", { type: "password", autocomplete: "current-password", "aria-label": "Code d'accès", class: "input" });
    const form = el("form", { class: "modal" }, [
      el("h2", {}, [title]),
      el("p", {}, [hint]),
      input,
      el("div", { class: "modal-actions" }, [el("button", { class: "btn btn-primary", type: "submit" }, ["Entrer"])]),
    ]);
    const overlay = el("div", { class: "modal-overlay", role: "dialog", "aria-modal": "true", "data-role": role }, [form]);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      overlay.remove();
      resolve(v);
    });
    document.body.append(overlay);
    input.focus();
  });
}
