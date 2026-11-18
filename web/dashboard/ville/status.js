// Statut honnête d'un plan : jamais de vert si des points restent non desservis sans explication.
const pct = (v) => `${Math.round(Number(v) * 100)} %`;

export function planStatus(plan, stale = null) {
  if (!plan) {
    return stale
      ? { niveau: "ko", titre: "Recalcul échoué — aucun plan valide", details: [stale.message] }
      : { niveau: "vide", titre: "Aucun plan calculé", details: [] };
  }
  const ch = plan.checks || {};
  const n = (plan.consolidation_points || []).length;
  const unserved = ch.unserved_count ?? (plan.unserved || []).length;
  const postponed = ch.postponed_count ?? (plan.postponed || []).length;
  const details = [...(ch.messages || []).map((m) => String(m).replace(/^\[global\] /, ""))];
  const secours = plan.mode === "secours" ? " (mode secours)" : "";
  let st;
  if (!n || ch.network_available === false || !(plan.routes || []).length) {
    st = { niveau: "ko", titre: `Plan irréalisable${secours}`, details: details.length ? details : ["Aucune tournée possible."] };
  } else if (!(ch.capacity_ok !== false && ch.budget_ok !== false && ch.vehicles_ok !== false && ch.network_ok !== false)) {
    st = { niveau: "ko", titre: `Plan irréalisable : contrôle en échec${secours}`, details };
  } else if (ch.ok && !postponed && !unserved) {
    st = { niveau: "ok", titre: `Plan réalisable — ${n}/${n} points desservis${secours}`, details };
  } else if (ch.ok && !postponed) {
    // Contrôle du serveur réussi (dans sa tolérance) mais des points restent non desservis : jamais de vert.
    st = { niveau: "partiel", titre: `Plan réalisable — ${n - unserved}/${n} points desservis, ${unserved} non desservi(s)${secours}`, details };
  } else if (ch.ok && postponed) {
    st = { niveau: "partiel", titre: `Plan partiellement réalisable — ${postponed} arrêt(s) reporté(s)${secours}`, details };
  } else {
    st = { niveau: "partiel", titre: `Plan partiellement réalisable — ${unserved} point(s) non desservis (${pct(ch.unserved_ratio ?? unserved / n)})${secours}`, details };
  }
  if (stale) {
    return { niveau: "ko", titre: "Plan précédent affiché — recalcul échoué", details: [stale.message, `Plan affiché : ${st.titre}`] };
  }
  return st;
}
