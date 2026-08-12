import { useEffect, useMemo, useState } from "react";

import { money } from "../api";
import { useAuth } from "../auth";
import { StaleBanner } from "../components/OfflineBanners";
import { mutate, useOfflineResource } from "../offline/useOfflineResource";
import { useYear } from "../year";
import type { ClassRoom, Paginated, Register, RegisterRow, SchoolYear } from "../types";

type Draft = Record<number, RegisterRow>;

/** Fins de mois de l'exercice, d'octobre à septembre. */
function periodOptions(year: SchoolYear | null | undefined) {
  if (!year) return [];
  const start = new Date(year.start_date);
  return Array.from({ length: 12 }, (_, index) => {
    // Jour 0 du mois suivant = dernier jour du mois voulu.
    const date = new Date(start.getFullYear(), start.getMonth() + index + 1, 0);
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
      date.getDate(),
    ).padStart(2, "0")}`;
    return {
      value: iso,
      label: date.toLocaleDateString("fr-FR", { month: "long", year: "numeric" }),
    };
  });
}

export default function PaymentRegister() {
  const { profile, can } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";
  const editable = can("monthlypayment", "add");

  const classes = useOfflineResource<Paginated<ClassRoom>>("/classes/");

  const [classroom, setClassroom] = useState<number | null>(null);
  const [period, setPeriod] = useState<string>("");
  const [draft, setDraft] = useState<Draft>({});
  const [status, setStatus] = useState<
    { kind: "error" | "success" | "queued"; text: string } | null
  >(null);
  const [saving, setSaving] = useState(false);

  // Le sélecteur global commande : l'écran de saisie doit viser la même
  // année que le reste de l'application, faute de quoi un encaissement
  // partirait dans l'année courante pendant qu'on consulte 2024.
  const { selected: currentYear } = useYear();
  const periods = useMemo(() => periodOptions(currentYear), [currentYear]);

  useEffect(() => {
    if (classroom === null && classes.data?.results.length) {
      setClassroom(classes.data.results[0].id);
    }
  }, [classes.data, classroom]);

  useEffect(() => {
    if (!period && periods.length) setPeriod(periods[0].value);
  }, [periods, period]);

  const path =
    classroom && period
      ? `/monthly-payments/register/?classroom=${classroom}&period=${period}`
      : null;
  const {
    data: register,
    loading,
    reload,
    stale,
    cachedAt,
  } = useOfflineResource<Register>(path);

  // Le brouillon local repart de l'état serveur à chaque changement de classe ou
  // de mois, pour qu'une saisie non enregistrée ne se reporte pas ailleurs.
  useEffect(() => {
    if (!register) return;
    setDraft(Object.fromEntries(register.rows.map((row) => [row.student, { ...row }])));
    setStatus(null);
  }, [register]);

  const rows = register?.rows ?? [];

  function update(studentId: number, field: keyof RegisterRow, value: string) {
    setDraft((current) => ({
      ...current,
      [studentId]: { ...current[studentId], [field]: Number(value) || 0 },
    }));
  }

  /** Pré-remplit la colonne mensualité au tarif de la classe. */
  function fillExpectedTuition() {
    const expected = register?.expected_tuition;
    if (!expected) return;
    setDraft((current) =>
      Object.fromEntries(
        Object.entries(current).map(([id, row]) => [id, { ...row, tuition: expected }]),
      ),
    );
  }

  const totals = Object.values(draft).reduce(
    (accumulator, row) => ({
      tuition: accumulator.tuition + row.tuition,
      canteen: accumulator.canteen + row.canteen,
      reinforcement: accumulator.reinforcement + row.reinforcement,
      uniform: accumulator.uniform + row.uniform,
    }),
    { tuition: 0, canteen: 0, reinforcement: 0, uniform: 0 },
  );
  const grandTotal =
    totals.tuition + totals.canteen + totals.reinforcement + totals.uniform;

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      // Seules les lignes portant un montant partent au serveur : envoyer des zéros
      // créerait des encaissements vides pour les élèves qui n'ont rien réglé.
      const entries = Object.values(draft)
        .filter(
          (row) => row.tuition || row.canteen || row.reinforcement || row.uniform,
        )
        .map((row) => ({
          student: row.student,
          tuition: row.tuition,
          canteen: row.canteen,
          reinforcement: row.reinforcement,
          uniform: row.uniform,
          payment_date: period,
        }));

      if (entries.length === 0) {
        setStatus({ kind: "error", text: "Aucun montant saisi." });
        return;
      }

      const className =
        classes.data?.results.find((c) => c.id === classroom)?.name ?? "classe";
      const periodLabel =
        periods.find((p) => p.value === period)?.label ?? period;

      const outcome = await mutate(
        "/monthly-payments/bulk/",
        { period, entries },
        { label: `Encaissements ${className} — ${periodLabel} (${entries.length})` },
      );

      if (outcome.queued) {
        // Hors ligne : la saisie est conservée localement. On le dit explicitement
        // plutôt que d'afficher un succès qui laisserait croire à un enregistrement.
        setStatus({
          kind: "queued",
          text:
            `${entries.length} encaissement(s) conservé(s) sur cet appareil. ` +
            `L'envoi se fera automatiquement au retour du réseau.`,
        });
      } else {
        const result = outcome.response as { saved: number; total: number };
        setStatus({
          kind: "success",
          text: `${result.saved} encaissement(s) enregistré(s) — ${money(result.total)} ${currency}.`,
        });
        reload();
      }
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Encaissements</h1>
          <p>
            Saisie d'une classe entière en une fois. Les montants déjà enregistrés
            sont pré-remplis et peuvent être corrigés.
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="field">
          <label htmlFor="classroom">Classe</label>
          <select
            id="classroom"
            value={classroom ?? ""}
            onChange={(event) => setClassroom(Number(event.target.value))}
          >
            {classes.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.student_count})
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="period">Mois</label>
          <select
            id="period"
            value={period}
            onChange={(event) => setPeriod(event.target.value)}
          >
            {periods.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        {editable && register?.expected_tuition && (
          <button type="button" className="secondary" onClick={fillExpectedTuition}>
            Remplir au tarif ({money(register.expected_tuition)})
          </button>
        )}

        {editable && (
          <button type="button" onClick={save} disabled={saving || rows.length === 0}>
            {saving ? "Enregistrement…" : "Enregistrer"}
          </button>
        )}
      </div>

      <StaleBanner
        freshness={{ stale, cachedAt }}
        label="Les montants déjà enregistrés"
      />

      {status && (
        <div className={`alert ${status.kind === "queued" ? "warning" : status.kind}`}>
          {status.text}
        </div>
      )}

      {loading && <div className="spinner">Chargement…</div>}

      {!loading && rows.length === 0 && (
        <div className="card empty">Aucun élève actif dans cette classe.</div>
      )}

      {!loading && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table-dense">
            <thead>
              <tr>
                <th className="sticky-col">Élève</th>
                <th className="num">Mensualité</th>
                <th className="num">Cantine</th>
                <th className="num">Renforcement</th>
                <th className="num">Uniforme</th>
                <th className="num">Total</th>
                <th>État</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const current = draft[row.student] ?? row;
                const lineTotal =
                  current.tuition + current.canteen + current.reinforcement + current.uniform;
                return (
                  <tr key={row.student}>
                    <td className="sticky-col">{row.name}</td>
                    {(["tuition", "canteen", "reinforcement", "uniform"] as const).map(
                      (field) => (
                        <td key={field} className="num">
                          {editable ? (
                            <input
                              className="cell"
                              type="number"
                              min={0}
                              step={500}
                              value={current[field] || ""}
                              placeholder="0"
                              onChange={(event) =>
                                update(row.student, field, event.target.value)
                              }
                            />
                          ) : (
                            money(current[field])
                          )}
                        </td>
                      ),
                    )}
                    <td className="num">{money(lineTotal)}</td>
                    <td>
                      {row.recorded ? (
                        <span className="badge paid">Enregistré</span>
                      ) : (
                        <span className="badge unpaid">À saisir</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              <tr className="total">
                <td className="sticky-col">Total — {rows.length} élèves</td>
                <td className="num">{money(totals.tuition)}</td>
                <td className="num">{money(totals.canteen)}</td>
                <td className="num">{money(totals.reinforcement)}</td>
                <td className="num">{money(totals.uniform)}</td>
                <td className="num">{money(grandTotal)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
