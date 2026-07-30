import { useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../api";

type Scanned = {
  duplicate: boolean;
  detail?: string;
  direction_label?: string;
  is_late?: boolean;
  student: {
    matricule: string;
    name: string;
    classroom: string;
    parent_phone: string;
  };
  event: { occurred_at: string; direction: string };
};

/**
 * Poste de badgeage au portail.
 *
 * La lecture caméra passe par `BarcodeDetector`, présent sur Chrome et Android
 * mais pas sur iOS. La saisie manuelle du matricule n'est donc pas un repli
 * dégradé : c'est le mode de secours de plein droit, et il reste toujours
 * accessible — au portail, une carte cornée ou un téléphone incompatible ne
 * doivent jamais bloquer la file.
 */
export default function Badge() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const lastScanRef = useRef<{ payload: string; at: number } | null>(null);

  const [scanning, setScanning] = useState(false);
  const [supported, setSupported] = useState(false);
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<Scanned | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Scanned[]>([]);

  useEffect(() => {
    setSupported("BarcodeDetector" in window);
    return () => stopCamera();
  }, []);

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setScanning(false);
  }

  async function startCamera() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setScanning(true);
      void loop();
    } catch {
      setError(
        "Accès à la caméra refusé. Utilisez la saisie du matricule ci-dessous.",
      );
    }
  }

  async function loop() {
    const Detector = (window as unknown as { BarcodeDetector?: new (o: object) => {
      detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>;
    } }).BarcodeDetector;
    if (!Detector) return;

    const detector = new Detector({ formats: ["qr_code"] });

    const tick = async () => {
      if (!streamRef.current || !videoRef.current) return;
      try {
        const codes = await detector.detect(videoRef.current);
        if (codes.length) {
          const payload = codes[0].rawValue;
          const previous = lastScanRef.current;
          // Le flux vidéo relit le même code plusieurs fois par seconde : sans
          // ce garde, une carte présentée une fois déclencherait dix appels.
          if (!previous || previous.payload !== payload || Date.now() - previous.at > 4000) {
            lastScanRef.current = { payload, at: Date.now() };
            await send(payload);
          }
        }
      } catch {
        /* image non exploitable — on réessaie à la frame suivante */
      }
      if (streamRef.current) requestAnimationFrame(() => void tick());
    };

    void tick();
  }

  async function send(payload: string, isManual = false) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<Scanned>(
        "/scan/badge/",
        isManual ? { matricule: payload } : { payload },
      );
      setLast(result);
      if (!result.duplicate) setHistory((current) => [result, ...current].slice(0, 12));
      if (isManual) setManual("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Badgeage impossible.");
      setLast(null);
    } finally {
      setBusy(false);
    }
  }

  function onManualSubmit(event: FormEvent) {
    event.preventDefault();
    if (manual.trim()) void send(manual.trim(), true);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Badgeage</h1>
          <p>
            Présentez la carte de l'élève devant la caméra, ou saisissez son
            matricule. Le sens — entrée ou sortie — est déduit du dernier passage.
          </p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="grid-2">
        <div className="card">
          <div className="card-title">Lecture de la carte</div>

          {!supported && (
            <div className="alert warning">
              Ce navigateur ne sait pas lire les QR codes. Utilisez la saisie du
              matricule — elle enregistre exactement le même passage.
            </div>
          )}

          <div className={`scanner ${scanning ? "active" : ""}`}>
            <video ref={videoRef} muted playsInline />
            {!scanning && <div className="scanner-idle">Caméra éteinte</div>}
            {scanning && <div className="scanner-frame" aria-hidden="true" />}
          </div>

          <div className="page-actions" style={{ marginTop: "var(--space-3)" }}>
            {!scanning ? (
              <button type="button" onClick={startCamera} disabled={!supported}>
                Activer la caméra
              </button>
            ) : (
              <button type="button" className="secondary" onClick={stopCamera}>
                Arrêter la caméra
              </button>
            )}
          </div>

          <form onSubmit={onManualSubmit} style={{ marginTop: "var(--space-4)" }}>
            <div className="field">
              <label htmlFor="matricule">Matricule</label>
              <input
                id="matricule"
                value={manual}
                placeholder="M0042"
                autoComplete="off"
                onChange={(event) => setManual(event.target.value.toUpperCase())}
              />
            </div>
            <button
              type="submit"
              className="secondary"
              disabled={busy || !manual.trim()}
              style={{ marginTop: "var(--space-2)", width: "100%" }}
            >
              {busy ? "Enregistrement…" : "Enregistrer le passage"}
            </button>
          </form>
        </div>

        <div>
          {last && (
            <div
              className={`card badge-result ${
                last.duplicate ? "duplicate" : last.is_late ? "late" : "ok"
              }`}
            >
              <div className="badge-status">
                {last.duplicate
                  ? "Déjà scanné"
                  : `${last.direction_label} enregistrée`}
                {last.is_late && !last.duplicate && " — en retard"}
              </div>
              <div className="badge-name">{last.student.name}</div>
              <div className="badge-meta">
                {last.student.matricule} · {last.student.classroom}
              </div>
              {last.duplicate && <p className="muted">{last.detail}</p>}
              {last.student.parent_phone && (
                <div className="badge-meta">Parent : {last.student.parent_phone}</div>
              )}
            </div>
          )}

          {history.length > 0 && (
            <div className="card">
              <div className="card-title">Derniers passages</div>
              <div className="table-wrap">
                <table className="table-dense">
                  <thead>
                    <tr>
                      <th>Heure</th>
                      <th>Élève</th>
                      <th>Classe</th>
                      <th>Sens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((entry, index) => (
                      <tr key={`${entry.student.matricule}-${index}`}>
                        <td>
                          {new Date(entry.event.occurred_at).toLocaleTimeString("fr-FR", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td>{entry.student.name}</td>
                        <td>{entry.student.classroom}</td>
                        <td>
                          <span
                            className={`badge ${
                              entry.event.direction === "IN" ? "paid" : ""
                            }`}
                          >
                            {entry.direction_label}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
