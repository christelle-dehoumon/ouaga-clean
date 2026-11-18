// Comparaison A/B et historique des scénarios (GET /api/scenarios, GET /api/scenarios/compare).
import { once } from "/dashboard/shared/api.js";
import { el, fmt } from "/dashboard/shared/ui.js";

const METRIQUES = {
  part_ramassee: { label: "Part des déchets ramassée (simulation)", sens: 1, f: (v) => fmt.pct(v, 1) },
  cout_fcfa: { label: "Coût d'un passage (plan)", sens: -1, f: fmt.fcfa },
  non_servis: { label: "Points non desservis", sens: -1, f: fmt.int },
  reportes: { label: "Arrêts reportés", sens: -1, f: fmt.int },
  depotoirs_restants: { label: "Dépotoirs restants (simulation)", sens: -1, f: fmt.int },
  compute_ms: { label: "Durée du calcul serveur", sens: -1, f: fmt.ms },
};

function resume(s) {
  const p = s.params || {};
  const ev = (s.events || []).map((e) => e.type === "truck_down" ? `panne ${e.vehicle_id}` : e.type === "rain" ? "pluie" : e.type === "new_district" ? `quartier ${e.territory_id}` : e.type);
  return [
    `${p.trucks ?? "?"} camions`, p.budget !== undefined ? fmt.fcfa(p.budget) : null,
    p.rainy_season ? "pluie" : null, (p.broken_trucks || []).length ? `en panne : ${p.broken_trucks.join(", ")}` : null,
    (p.extra_territories || []).length ? `quartiers : ${p.extra_territories.join(", ")}` : null, ...ev,
  ].filter(Boolean).join(" · ");
}

export function renderCompare(S, ctx) {
  const host = document.getElementById("onglet-comparer");
  const plan = S.plan[S.mode];
  const slot = (k) => {
    const s = S[k];
    return el("div", { class: "bloc" }, [
      el("h3", {}, [`Scénario ${k}`, s ? el("span", { class: "meta" }, [s.mode === "sim" ? "simulation" : "réel"]) : ""]),
      s ? el("p", {}, [el("b", {}, [s.label || s.id]), el("br"), fmt.date(s.created_at), el("br"), resume(s)]) : el("p", { class: "vide" }, ["Non choisi."]),
      el("button", { class: "btn", type: "button", disabled: !plan || null, onclick: () => {
        const id = `s_${plan.plan_id}`;
        S[k] = { id, label: `Plan ${plan.plan_id}`, created_at: plan.computed_at, params: plan.params_used, events: plan.events, mode: plan.data_mode };
        renderCompare(S, ctx);
      } }, [`Fixer le plan affiché comme ${k}`]),
    ]);
  };
  const result = el("div", {});
  const go = el("button", { class: "btn btn-primaire btn-large", type: "button", disabled: !(S.A && S.B) || null,
    onclick: (e) => once(e.currentTarget, async () => {
      try {
        const d = await ctx.call(() => S.api.compare(S.A.id, S.B.id));
        result.replaceChildren(...tableau(d));
      } catch (err) {
        result.replaceChildren(el("p", { class: "erreur" }, [`Comparaison impossible : ${err.message}`]));
      }
    }) }, ["Comparer A et B"]);
  host.replaceChildren(
    el("p", { class: "vide" }, ["Chaque calcul est enregistré côté serveur. Fixez deux plans (par exemple normal, puis panne + pluie) et comparez-les. La part ramassée vient de la simulation de 7 jours lancée après chaque calcul."]),
    slot("A"), slot("B"), go, result,
  );
}

function tableau(d) {
  const rows = d.ecarts.filter((l) => METRIQUES[l.indicateur]);
  const better = [];
  const worse = [];
  const lines = rows.map((l) => {
    const m = METRIQUES[l.indicateur];
    let cls = "";
    if (l.ecart !== null && l.ecart !== 0 && l.indicateur !== "compute_ms") {
      const good = Math.sign(l.ecart) === m.sens;
      cls = good ? "mieux" : "moins";
      (good ? better : worse).push(`${m.label.toLowerCase()} (${l.ecart > 0 ? "+" : ""}${l.indicateur === "part_ramassee" ? `${fmt.n(l.ecart * 100, 1)} pts` : m.f(l.ecart)})`);
    }
    return el("tr", {}, [el("td", {}, [m.label]), el("td", { class: "num" }, [l.a === null ? "—" : m.f(l.a)]),
      el("td", { class: "num" }, [l.b === null ? "—" : m.f(l.b)]), el("td", { class: `num ${cls}` }, [l.ecart === null ? "n.d." : `${l.ecart > 0 ? "+" : ""}${l.indicateur === "part_ramassee" ? fmt.n(l.ecart * 100, 1) + " pts" : m.f(l.ecart)}`])]);
  });
  const missing = rows.filter((l) => l.a === null || l.b === null).map((l) => METRIQUES[l.indicateur].label.toLowerCase());
  const texte = [];
  if (better.length) texte.push(`B fait mieux sur : ${better.join(", ")}.`);
  if (worse.length) texte.push(`B fait moins bien sur : ${worse.join(", ")}.`);
  if (better.length && worse.length) texte.push("Aucun des deux n'est meilleur sur tout : le choix dépend de la priorité (couverture ou coût).");
  else if (better.length) texte.push("B domine A sur les indicateurs disponibles.");
  else if (worse.length) texte.push("A domine B sur les indicateurs disponibles.");
  else texte.push("Pas de différence sur les indicateurs disponibles.");
  if (missing.length) texte.push(`Non disponible pour l'un des deux : ${missing.join(", ")} (simulation non lancée sur ce plan).`);
  return [
    el("table", { class: "table" }, [el("thead", {}, [el("tr", {}, ["Indicateur", "A", "B", "B − A"].map((h) => el("th", {}, [h])))]), el("tbody", {}, lines)]),
    el("ul", { class: "texte-comparaison" }, texte.map((t) => el("li", {}, [t]))),
  ];
}

export async function renderHistory(S, ctx) {
  const host = document.getElementById("onglet-historique");
  host.replaceChildren(el("p", { class: "vide" }, ["Chargement de l'historique…"]));
  let list;
  try {
    list = await ctx.call(() => S.api.scenarios());
  } catch (err) {
    host.replaceChildren(el("p", { class: "erreur" }, [`Historique indisponible : ${err.message}`]));
    return;
  }
  const current = S.plan[S.mode]?.plan_id;
  host.replaceChildren(
    el("p", { class: "vide" }, [`${list.length} calcul(s) enregistré(s), du plus récent au plus ancien. Le plan en cours est marqué.`]),
    ...list.slice(0, 60).map((s) => {
      const r = s.results || {};
      const statut = r.checks_ok ? (r.reportes ? "réalisable avec reports" : "réalisable") : "partiellement réalisable ou irréalisable";
      return el("div", { class: "bloc" }, [
        el("h3", {}, [s.label || "Calcul", el("span", { class: "meta" }, [`${s.mode === "sim" ? "simulation" : "réel"}${s.plan_id === current ? " · en cours" : ""}`])]),
        el("p", {}, [fmt.date(s.created_at), el("br"), resume(s)]),
        el("p", {}, [`Statut : ${statut} · non desservis ${fmt.int(r.non_servis)} · reportés ${fmt.int(r.reportes)} · coût ${fmt.fcfa(r.cout_fcfa)}`,
          r.part_ramassee !== undefined ? ` · part ramassée ${fmt.pct(r.part_ramassee, 1)}` : "", ` · calcul ${fmt.ms(s.compute_ms)}`]),
        el("div", { class: "rangee" }, [
          el("button", { class: "btn", type: "button", onclick: () => ctx.openPlan(s.plan_id) }, ["Rouvrir"]),
          el("button", { class: "btn", type: "button", onclick: () => { S.A = s; ctx.showTab("comparer"); } }, ["Choisir comme A"]),
          el("button", { class: "btn", type: "button", onclick: () => { S.B = s; ctx.showTab("comparer"); } }, ["Choisir comme B"]),
        ]),
      ]);
    }),
  );
}
