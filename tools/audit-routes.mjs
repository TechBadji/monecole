/**
 * Parcourt toutes les routes de l'application et signale celles qui rendent une
 * page vide ou lèvent une erreur.
 *
 * Écrit après qu'un écran blanc soit passé en production : la compilation et la
 * suite de tests étaient au vert, et l'écran ne s'affichait pas. Seul un
 * parcours réel des routes, dans un navigateur, l'aurait attrapé.
 *
 * Une seule session Chrome pour l'ensemble : relancer le navigateur par route
 * masquerait précisément les pannes liées à l'état conservé d'un écran à
 * l'autre.
 *
 * Prérequis : `npm run dev` et le serveur Django en marche.
 *
 *   TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
 *     -H 'Content-Type: application/json' \
 *     -d '{"email":"...","password":"..."}' | jq -r .access)
 *   node tools/audit-routes.mjs "$TOKEN"
 *
 * Le jeu de routes est surchargeable, pour éprouver un rôle particulier :
 *
 *   ROUTES='[["/","Accueil"],["/eleves","Élèves"]]' node tools/audit-routes.mjs "$TOKEN"
 *
 * Sort en code 1 si une route rend une page vide ou déclenche la barrière
 * d'erreur — utilisable tel quel dans une chaîne d'intégration.
 */

import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const token = process.argv[2] ?? "";
const PORT = 9334;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const ROUTES = JSON.parse(process.env.ROUTES || "null") ?? [
  ["/", "Tableau de bord"],
  ["/eleves", "Élèves"],
  ["/encaissements", "Encaissements"],
  ["/arrieres", "Arriérés"],
  ["/notes", "Saisie des notes"],
  ["/bulletins", "Bulletins"],
  ["/compositions", "Compositions"],
  ["/assiduite", "Assiduité"],
  ["/depenses", "Dépenses"],
  ["/bilan", "Rapport bilan"],
  ["/encais", "Encaissements (synthèse)"],
  ["/enseignants", "Enseignants"],
  ["/paie", "Bulletins de paie"],
  ["/matieres", "Matières et barèmes"],
  ["/import", "Import de données"],
  ["/parametres", "Paramètres"],
  ["/journal", "Journal d'audit"],
  ["/compte", "Mon compte"],
  ["/aide", "Questions fréquentes"],
  ["/route-inexistante", "Route inconnue (doit rediriger)"],
];

let nextId = 1;
function call(socket, method, params = {}) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      socket.removeEventListener("message", onMessage);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    };
    socket.addEventListener("message", onMessage);
    setTimeout(() => reject(new Error(`timeout ${method}`)), 30000);
  });
}

const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  "--headless=new",
  "--no-first-run",
  "--user-data-dir=/tmp/monecole-audit-profile",
  "--window-size=1440,900",
  "about:blank",
], { stdio: "ignore" });

await sleep(1500);
const targets = await (await fetch(`http://localhost:${PORT}/json`)).json();
const page = targets.find((t) => t.type === "page");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve) => socket.addEventListener("open", resolve));

let problems = [];
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.method === "Runtime.exceptionThrown") {
    problems.push(message.params.exceptionDetails.exception?.description ?? message.params.exceptionDetails.text);
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    problems.push(message.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
  }
});

await call(socket, "Runtime.enable");
await call(socket, "Page.enable");
await call(socket, "Emulation.setDeviceMetricsOverride", {
  width: 1440, height: 900, deviceScaleFactor: 1, mobile: false,
});
if (token) {
  await call(socket, "Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("monecole.access", ${JSON.stringify(token)});`,
  });
}

const rows = [];
for (const [route, label] of ROUTES) {
  problems = [];
  await call(socket, "Page.navigate", { url: `http://localhost:5173${route}` });
  await sleep(2600);

  const probe = await call(socket, "Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => {
      const root = document.getElementById("root");
      const html = root ? root.innerHTML : "";
      const heading = document.querySelector("h1");
      return {
        length: html.length,
        heading: heading ? heading.innerText.trim().slice(0, 46) : "",
        boundary: !!document.querySelector(".route-error"),
        // Le texte réellement lisible, et non la taille du HTML : un écran
        // d'état vide légitime — « aucun élève rattaché » — tient en peu de
        // balises et serait signalé à tort sur un seuil de caractères.
        text: (document.body.innerText || "").trim().length,
        path: location.pathname,
      };
    })()`,
  });
  const r = probe.result.value;
  rows.push({ route, label, ...r, problems: [...new Set(problems)] });
}

socket.close();
chrome.kill();

const pad = (s, n) => String(s).padEnd(n);
console.log(pad("Route", 24) + pad("Texte", 8) + pad("Titre affiché", 38) + "État");
console.log("-".repeat(88));

let failed = 0;
for (const r of rows) {
  // Une page est vide si rien ne s'y lit : ni titre, ni texte. Un écran qui
  // annonce « aucune donnée » a fait son travail.
  const blank = !r.heading && r.text < 40;
  const bad = blank || r.boundary;
  if (bad) failed += 1;
  const state = r.boundary ? "BARRIÈRE D'ERREUR" : blank ? "PAGE VIDE" : "ok";
  const arrow = r.path !== r.route ? ` → ${r.path}` : "";
  console.log(pad(r.route + arrow, 24) + pad(r.text, 8) + pad((r.heading || "—").replace(/\n/g, " "), 38) + state);
  for (const p of r.problems.slice(0, 2)) {
    console.log("    ⚠ " + p.split("\n")[0].slice(0, 110));
  }
}
console.log("-".repeat(88));
console.log(`${rows.length - failed}/${rows.length} routes rendent correctement.`);
process.exit(failed ? 1 : 0);
