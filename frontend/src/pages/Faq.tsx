import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

/**
 * Questions fréquentes.
 *
 * Chaque réponse décrit ce que l'application **fait**, vérifiable à l'écran. Ni
 * tarif, ni délai d'assistance, ni engagement de service : le produit n'en a
 * pas, et une FAQ qui en promet se retourne contre l'école le jour où elle
 * appelle.
 *
 * Les réponses qui touchent au calcul renvoient à la règle exacte plutôt qu'à
 * une formule vague : une directrice qui compare avec son classeur a besoin du
 * chiffre, pas d'une intention.
 */
type Entry = { question: string; answer: ReactNode; keywords?: string };
type Section = { title: string; blurb: string; entries: Entry[] };

const SECTIONS: Section[] = [
  {
    title: "Prise en main",
    blurb: "Les premiers gestes, de la reprise des données à la première rentrée.",
    entries: [
      {
        question: "Comment reprendre mes données existantes ?",
        keywords: "import excel csv migration reprise classeur",
        answer: (
          <>
            <p>
              Depuis <strong>Administration → Import de données</strong>. Deux formats
              sont acceptés :
            </p>
            <ul>
              <li>
                votre <strong>classeur de gestion Excel</strong>, avec ses onglets par
                classe — l'application y retrouve les élèves, les inscriptions et les
                mensualités déjà réglées ;
              </li>
              <li>
                un <strong>tableau simple</strong> (CSV ou Excel) d'élèves ou
                d'enseignants. Les modèles de fichier sont téléchargeables sur la page,
                avec les colonnes attendues.
              </li>
            </ul>
            <p>
              Un import se lance d'abord <strong>à blanc</strong> : vous voyez ce qui
              serait créé, les montants totaux et les lignes douteuses, sans rien
              écrire. C'est seulement au second passage que les données entrent.
            </p>
          </>
        ),
      },
      {
        question: "D'où vient le matricule d'un élève ?",
        keywords: "matricule numéro identifiant MXXXX",
        answer: (
          <p>
            Il est attribué automatiquement, au format <code>M0001</code>, et
            l'élève le garde pour tout son cursus. Il est propre à votre
            établissement : deux écoles peuvent avoir un <code>M0042</code> sans
            conflit. Une reprise de données ne renumérote jamais un élève déjà
            inscrit.
          </p>
        ),
      },
      {
        question: "Puis-je avoir plusieurs classes pour un même niveau ?",
        keywords: "classes sections CI-A CI-B niveau parallèle",
        answer: (
          <>
            <p>
              Oui. Dans <strong>Paramètres → Classes et sections</strong>, choisissez
              le niveau et le nombre de classes : elles sont créées sous la forme
              <code> CI-A</code>, <code>CI-B</code>, <code>CI-C</code>, et se rangent
              dans l'ordre pédagogique.
            </p>
            <p>
              Si une classe portait le nom nu du niveau — « CI » — elle est renommée
              « CI-A » plutôt que doublée. Ses élèves, tarifs et notes la suivent.
            </p>
          </>
        ),
      },
    ],
  },
  {
    title: "Encaissements et arriérés",
    blurb: "Le guichet, les paiements et ce que l'école attend encore.",
    entries: [
      {
        question: "Comment encaisser rapidement au guichet ?",
        keywords: "encaissement paiement saisie classe rapide guichet",
        answer: (
          <p>
            <strong>Scolarité → Encaissements</strong> affiche la classe entière pour
            un mois donné, avec les montants déjà réglés pré-remplis. Le bouton
            « Remplir au tarif » pose la mensualité de la classe sur toutes les
            lignes vides, et un seul enregistrement valide la classe. La saisie est
            conçue pour tenir en moins de trente secondes par élève, parent devant
            le bureau.
          </p>
        ),
      },
      {
        question: "Que se passe-t-il si le réseau coupe pendant une saisie ?",
        keywords: "hors ligne offline coupure réseau internet synchronisation",
        answer: (
          <>
            <p>
              Rien n'est perdu. Les encaissements saisis hors ligne sont mis en file
              sur l'appareil et remontent d'eux-mêmes au retour de la connexion. Un
              bandeau indique les écritures en attente.
            </p>
            <p>
              Les montants affichés pendant une coupure portent leur horodatage :
              vous savez de quand ils datent, ce qui évite de décider sur des chiffres
              périmés.
            </p>
          </>
        ),
      },
      {
        question: "Un parent a payé plus que le montant dû. Que fait l'application ?",
        keywords: "trop-perçu remboursement excédent surplus",
        answer: (
          <p>
            Le <strong>trop-perçu</strong> est affiché comme tel dans la situation de
            l'élève, et non ramené à un solde nul. C'est volontaire : l'école doit un
            remboursement ou un report, et « Reste à payer : 0 » le lui ferait
            manquer. Le cas se produit surtout quand une réduction est accordée après
            des versements au tarif plein.
          </p>
        ),
      },
      {
        question: "Comment accorder une bourse sociale ?",
        keywords: "bourse réduction remise sociale gratuité pourcentage",
        answer: (
          <p>
            Une bourse s'exprime en pourcentage et s'applique à l'élève ou à la
            famille. Elle réduit les mensualités dues, et le manque à gagner apparaît
            dans les états financiers et le tableau de bord — une bourse de 100 %
            n'est pas un impayé, c'est une recette que l'école a choisi de ne pas
            percevoir.
          </p>
        ),
      },
      {
        question: "Comment voir la situation financière d'un élève ?",
        keywords: "situation solde historique années dette élève",
        answer: (
          <p>
            Dans <strong>Scolarité → Élèves</strong>, le bouton « Situation » déplie
            le détail sous la ligne de l'élève : inscription, chaque mensualité, ce
            qui est réglé et ce qui reste. Des onglets donnent accès aux années
            précédentes — utile avant une réinscription.
          </p>
        ),
      },
    ],
  },
  {
    title: "Notes et bulletins",
    blurb: "Le calcul des moyennes, et pourquoi il tombe juste.",
    entries: [
      {
        question: "Comment la moyenne est-elle calculée ?",
        keywords: "moyenne calcul barème coefficient sur 10 sur 20",
        answer: (
          <>
            <p>
              <strong>
                Somme des notes ÷ somme des barèmes × 10.
              </strong>{" "}
              La moyenne est sur 10.
            </p>
            <p>
              Il n'y a <strong>pas de coefficient multiplicateur</strong> : c'est le
              barème qui fait le poids. Une matière notée sur 20 pèse cinq fois une
              matière notée sur 4, parce qu'elle apporte cinq fois plus de points.
            </p>
            <p className="muted">
              Cette règle a été établie en rejouant vingt bulletins papier réels :
              tous retrouvent la moyenne imprimée au centième.
            </p>
          </>
        ),
      },
      {
        question: "Le barème d'une matière change selon l'épreuve. C'est possible ?",
        keywords: "barème variable composition contrôle épreuve sur",
        answer: (
          <p>
            Oui, et c'est prévu. Chaque matière porte un <strong>barème de
            référence</strong> pour sa classe, que l'administration ajuste à la
            création d'une composition. Une conjugaison notée sur 4 au premier
            contrôle et sur 12 à la troisième composition ne pose aucun problème.
          </p>
        ),
      },
      {
        question: "Une absence compte-t-elle comme un zéro ?",
        keywords: "absence absent zéro moyenne malade",
        answer: (
          <p>
            Non. Une note absente sort du calcul : son barème est retiré du
            dénominateur. Compter une absence comme un zéro pénaliserait un élève
            malade exactement comme un élève ayant rendu copie blanche.
          </p>
        ),
      },
      {
        question: "Comment configurer les matières d'une classe ?",
        keywords: "matières barèmes catalogue configurer classe",
        answer: (
          <p>
            Dans <strong>Administration → Matières et barèmes</strong>, choisissez la
            classe puis « Appliquer le catalogue du niveau ». Trente-deux matières
            relevées sur des bulletins réels sont proposées avec leurs barèmes, du CI
            au CM2. Les matières déjà réglées ne sont pas retouchées.
          </p>
        ),
      },
      {
        question: "Qui saisit les notes, et quand deviennent-elles définitives ?",
        keywords: "saisie notes enseignant validation bulletin verrou",
        answer: (
          <p>
            L'enseignant saisit les notes de ses matières, une par une ou par lot, et
            déclare sa feuille <strong>validée</strong> quand il a terminé. Sans ce
            jalon, l'administration ne saurait pas distinguer une note manquante
            d'une note pas encore saisie, et éditerait des bulletins incomplets. Les
            bulletins s'éditent ensuite à l'unité ou pour la classe entière.
          </p>
        ),
      },
      {
        question: "Deux élèves ont la même moyenne. Comment sont-ils classés ?",
        keywords: "rang classement ex aequo égalité",
        answer: (
          <p>
            Ils partagent le même rang, et le suivant reprend au numéro qui suit le
            nombre d'élèves déjà classés — la convention scolaire. Un élève sans
            aucune note n'est pas classé dernier : il n'est pas classé.
          </p>
        ),
      },
    ],
  },
  {
    title: "Comptes, rôles et sécurité",
    blurb: "Qui accède à quoi, et comment reprendre la main.",
    entries: [
      {
        question: "J'ai oublié mon mot de passe.",
        keywords: "mot de passe oublié réinitialisation email lien",
        answer: (
          <>
            <p>
              Depuis l'écran de connexion, « Mot de passe oublié ? ». Un lien est
              envoyé à l'adresse de votre compte. Il est valable{" "}
              <strong>deux heures</strong> et ne sert qu'une fois.
            </p>
            <p>
              S'il n'arrive pas, regardez dans les indésirables, puis demandez à
              l'administration de votre établissement de vérifier l'adresse
              enregistrée. Un administrateur peut aussi vous fixer un mot de passe
              provisoire.
            </p>
          </>
        ),
      },
      {
        question: "Que fait exactement « Se souvenir de moi » ?",
        keywords: "se souvenir session durée connexion poste partagé",
        answer: (
          <p>
            Cochée, la session dure <strong>30 jours</strong> sur cet appareil.
            Décochée, elle se ferme avec le navigateur. Sur le poste partagé d'un
            secrétariat, laissez-la décochée : la personne suivante ouvrira le même
            navigateur.
          </p>
        ),
      },
      {
        question: "Comment savoir où mon compte est connecté ?",
        keywords: "sessions appareils connectés déconnecter sécurité vol",
        answer: (
          <p>
            Dans <strong>Mon compte → Appareils connectés</strong>. Chaque session
            indique l'appareil, l'adresse et la dernière activité. Si vous n'en
            reconnaissez pas une, déconnectez-la puis changez votre mot de passe —
            ce qui ferme d'office tous les autres appareils.
          </p>
        ),
      },
      {
        question: "Un enseignant peut-il voir les finances de l'école ?",
        keywords: "rôle permission accès enseignant comptable secrétaire parent",
        answer: (
          <>
            <p>
              Non. Chaque rôle n'accède qu'à ce qui le concerne : l'enseignant aux
              notes de ses classes, le comptable aux encaissements et aux dépenses,
              le parent à ses propres enfants et à rien d'autre.
            </p>
            <p>
              Le contrôle est appliqué par le serveur à chaque appel, pas seulement
              par les menus : masquer un bouton ne protège rien.
            </p>
          </>
        ),
      },
      {
        question: "Mes données sont-elles isolées des autres écoles ?",
        keywords: "multi-école isolation données confidentialité tenant",
        answer: (
          <p>
            Oui. Chaque enregistrement est rattaché à son établissement, et toute
            lecture est filtrée à la source. Aucune donnée ne franchit la frontière
            d'une école, y compris par erreur de programmation — le cloisonnement est
            porté par le modèle, pas par les écrans.
          </p>
        ),
      },
      {
        question: "Qui a saisi ce paiement, et quand ?",
        keywords: "audit journal traçabilité qui modification historique",
        answer: (
          <p>
            <strong>Administration → Journal d'audit</strong>. Toute opération
            financière — création, modification, suppression — y laisse une trace
            avec son auteur, la date et ce qui a changé. Le journal est en lecture
            seule : il ne peut être ni corrigé ni effacé.
          </p>
        ),
      },
    ],
  },
  {
    title: "Comptabilité et exercice",
    blurb: "Les deux calendriers, et ce qu'ils ne doivent pas mélanger.",
    entries: [
      {
        question: "Pourquoi deux calendriers différents ?",
        keywords: "exercice année scolaire pédagogique octobre septembre juin calendrier",
        answer: (
          <>
            <p>
              Parce que l'école en tient deux, et les confondre fausse tous les
              totaux :
            </p>
            <ul>
              <li>
                l'<strong>exercice financier</strong> court d'octobre à septembre,
                sur douze mois. Il porte les dépenses, les salaires et le bilan ;
              </li>
              <li>
                l'<strong>année pédagogique</strong> court d'octobre à juin, sur neuf
                mois. Elle porte les mensualités des élèves.
              </li>
            </ul>
          </>
        ),
      },
      {
        question: "Les montants comportent-ils des centimes ?",
        keywords: "franc CFA XOF décimale arrondi centime montant",
        answer: (
          <p>
            Non. Le franc CFA n'a pas de décimale, et les montants sont des entiers
            de bout en bout. Aucun arrondi ne peut se glisser dans un bilan.
          </p>
        ),
      },
      {
        question: "Quels moyens de paiement sont pris en charge ?",
        keywords: "wave mobile money espèces paiement moyen",
        answer: (
          <p>
            Les espèces et <strong>Wave</strong>. Un paiement Wave est confirmé par
            l'opérateur lui-même, et un même encaissement peut être réglé en
            plusieurs fois.
          </p>
        ),
      },
    ],
  },
  {
    title: "En cas de problème",
    blurb: "Ce qu'on peut régler soi-même avant d'appeler.",
    entries: [
      {
        question: "Un écran reste blanc ou ne se charge pas.",
        keywords: "écran blanc page vide bug erreur cache recharger",
        answer: (
          <>
            <p>
              C'est presque toujours une version de l'application restée en mémoire
              dans le navigateur après une mise à jour. L'écran affiche alors un
              bouton <strong>« Vider le cache et recharger »</strong> : il suffit.
            </p>
            <p>
              Si aucun message n'apparaît, rechargez en forçant —{" "}
              <kbd>Ctrl</kbd> <kbd>Maj</kbd> <kbd>R</kbd> sous Windows,{" "}
              <kbd>⌘</kbd> <kbd>Maj</kbd> <kbd>R</kbd> sur Mac.
            </p>
          </>
        ),
      },
      {
        question: "Les parents reçoivent-ils des SMS ?",
        keywords: "sms notification parent message rappel",
        answer: (
          <p>
            Oui, quand l'école l'active : rappels d'échéance, confirmations de
            paiement et, si la badgeuse est installée, arrivées et départs. Chaque
            envoi est consigné avec son état.
          </p>
        ),
      },
      {
        question: "La badgeuse à l'entrée est-elle déjà opérationnelle ?",
        keywords: "badgeuse pointeuse qr code entrée sortie présence matériel",
        answer: (
          <p>
            L'application est prête à la recevoir : chaque élève dispose d'un QR code
            imprimable, et le contrat d'échange est décrit pour l'équipementier. Le
            matériel lui-même n'est pas encore choisi, et le mode
            d'authentification du boîtier reste à arrêter avant toute commande.
          </p>
        ),
      },
    ],
  },
];

export default function Faq({ embedded = false }: { embedded?: boolean }) {
  const [query, setQuery] = useState("");

  const needle = query.trim().toLowerCase();
  const sections = useMemo(() => {
    if (!needle) return SECTIONS;
    return SECTIONS.map((section) => ({
      ...section,
      entries: section.entries.filter((entry) =>
        `${entry.question} ${entry.keywords ?? ""}`.toLowerCase().includes(needle),
      ),
    })).filter((section) => section.entries.length > 0);
  }, [needle]);

  const total = sections.reduce((sum, section) => sum + section.entries.length, 0);

  return (
    <div className={embedded ? "faq" : "faq faq-standalone"}>
      <div className="page-head">
        <div>
          <h1>Questions fréquentes</h1>
          <p>
            Ce que fait l'application, et comment. Une question qui n'y figure pas
            se pose à l'administration de votre établissement.
          </p>
        </div>
      </div>

      <div className="field faq-search">
        <label htmlFor="faq-search">Rechercher</label>
        <input
          id="faq-search"
          type="search"
          value={query}
          placeholder="bourse, absence, mot de passe, hors ligne…"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {needle && (
        <p className="muted faq-count">
          {total === 0
            ? "Aucune question ne correspond."
            : `${total} question${total > 1 ? "s" : ""} sur « ${query.trim()} ».`}
        </p>
      )}

      {sections.map((section) => (
        <section key={section.title} className="faq-section">
          <h2>{section.title}</h2>
          <p className="muted">{section.blurb}</p>

          {section.entries.map((entry) => (
            /* `<details>` natif : il s'ouvre sans JavaScript, se cherche avec la
               recherche du navigateur et s'imprime déplié. Un accordéon maison
               aurait coûté trois de ces qualités. */
            <details key={entry.question} className="faq-item" open={Boolean(needle)}>
              <summary>{entry.question}</summary>
              <div className="faq-answer">{entry.answer}</div>
            </details>
          ))}
        </section>
      ))}

      {!embedded && (
        <p className="faq-back">
          <Link to="/" className="quiet-link">
            Revenir à la connexion
          </Link>
        </p>
      )}
    </div>
  );
}
