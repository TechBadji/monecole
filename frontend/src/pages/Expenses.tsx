import { useState, type FormEvent } from "react";

import { api, money } from "../api";
import { useAuth } from "../auth";
import { useResource } from "../hooks";
import type { Expense, ExpenseCategory, Paginated, SchoolYear } from "../types";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Brouillon",
  PENDING: "À valider",
  APPROVED: "Validée",
  REJECTED: "Rejetée",
};

const CHANNEL_LABELS: Record<string, string> = {
  CASH: "Espèces",
  MOBILE_MONEY: "Mobile money",
  TRANSFER: "Virement",
  CHECK: "Chèque",
};

export default function Expenses() {
  const { profile, can } = useAuth();
  const currency = profile?.school?.currency ?? "XOF";
  const isAdmin = profile?.role === "ADMIN";

  const { data: categories } = useResource<Paginated<ExpenseCategory>>(
    "/expense-categories/?page_size=100",
  );
  const { data: years } = useResource<Paginated<SchoolYear>>("/school-years/");
  const { data, error, loading, reload } = useResource<Paginated<Expense>>(
    "/expenses/?page_size=100",
  );

  const currentYear = years?.results.find((year) => year.is_current);
  const [form, setForm] = useState({
    operation_date: new Date().toISOString().slice(0, 10),
    label: "",
    amount: "",
    transfer_fee: "",
    category: "",
    channel: "CASH",
    invoice_number: "",
  });
  const [status, setStatus] = useState<{ kind: "error" | "success"; text: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!currentYear) return;
    setBusy(true);
    setStatus(null);
    try {
      const created = await api.post<Expense>("/expenses/", {
        year: currentYear.id,
        operation_date: form.operation_date,
        label: form.label,
        amount: Number(form.amount) || 0,
        transfer_fee: Number(form.transfer_fee) || 0,
        category: Number(form.category),
        channel: form.channel,
        invoice_number: form.invoice_number,
      });
      setStatus({
        kind: "success",
        text:
          created.status === "PENDING"
            ? "Dépense enregistrée — elle dépasse le seuil et attend la validation d'un administrateur."
            : "Dépense enregistrée.",
      });
      setForm({ ...form, label: "", amount: "", transfer_fee: "", invoice_number: "" });
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Enregistrement impossible.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: number) {
    try {
      await api.post(`/expenses/${id}/approve/`);
      reload();
    } catch (caught) {
      setStatus({
        kind: "error",
        text: caught instanceof Error ? caught.message : "Validation impossible.",
      });
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dépenses</h1>
          <p>
            Seules les dépenses validées entrent au bilan. Montants en {currency}.
          </p>
        </div>
      </div>

      {status && <div className={`alert ${status.kind}`}>{status.text}</div>}

      {can("expense", "add") && (
        <form className="card" onSubmit={onSubmit}>
          <div className="card-title">Nouvelle dépense</div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <div className="field">
              <label htmlFor="date">Date d'opération</label>
              <input
                id="date"
                type="date"
                value={form.operation_date}
                onChange={(event) =>
                  setForm({ ...form, operation_date: event.target.value })
                }
                required
              />
            </div>
            <div className="field" style={{ minWidth: 220 }}>
              <label htmlFor="label">Intitulé</label>
              <input
                id="label"
                value={form.label}
                onChange={(event) => setForm({ ...form, label: event.target.value })}
                required
              />
            </div>
            <div className="field" style={{ minWidth: 220 }}>
              <label htmlFor="category">Rubrique</label>
              <select
                id="category"
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
                required
              >
                <option value="">Choisir…</option>
                {categories?.results.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="amount">Montant</label>
              <input
                id="amount"
                type="number"
                min={0}
                value={form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="fee">Frais de transfert</label>
              <input
                id="fee"
                type="number"
                min={0}
                value={form.transfer_fee}
                onChange={(event) =>
                  setForm({ ...form, transfer_fee: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="channel">Canal</label>
              <select
                id="channel"
                value={form.channel}
                onChange={(event) => setForm({ ...form, channel: event.target.value })}
              >
                {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" disabled={busy || !currentYear}>
              {busy ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        </form>
      )}

      {error && <div className="alert error">{error}</div>}
      {loading && <div className="spinner">Chargement…</div>}

      {!loading && data && (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Intitulé</th>
                <th>Rubrique</th>
                <th>Canal</th>
                <th className="num">Montant</th>
                <th className="num">Frais</th>
                <th>Statut</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {data.results.map((expense) => (
                <tr key={expense.id}>
                  <td>{new Date(expense.operation_date).toLocaleDateString("fr-FR")}</td>
                  <td>{expense.label}</td>
                  <td>{expense.category_label}</td>
                  <td>{CHANNEL_LABELS[expense.channel] ?? expense.channel}</td>
                  <td className="num">{money(expense.amount)}</td>
                  <td className="num">
                    {expense.transfer_fee ? money(expense.transfer_fee) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        expense.status === "APPROVED"
                          ? "paid"
                          : expense.status === "PENDING"
                            ? "partial"
                            : ""
                      }`}
                    >
                      {STATUS_LABELS[expense.status] ?? expense.status}
                    </span>
                  </td>
                  {isAdmin && (
                    <td>
                      {expense.status === "PENDING" && (
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => approve(expense.id)}
                        >
                          Valider
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {data.results.length === 0 && (
                <tr>
                  <td colSpan={isAdmin ? 8 : 7} className="empty">
                    Aucune dépense enregistrée.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
