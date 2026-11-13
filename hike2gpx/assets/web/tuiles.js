// Les calques d'un lot installé, lus par la page elle-même : le serveur sert
// les tuiles vectorielles de calques.mbtiles telles quelles (/calques/<case>/<x>/<y>),
// la page les décode et les garde en mémoire. C'est ce que fait le téléphone
// (Mvt.kt, Calques.kt) : le décodage en Python coûtait 1 à 2,5 s par
// déplacement, quand V8 compile ces boucles comme le fait Android.
//
// Les objets rendus ont la forme de lot.lire_calque côté Python : une ligne
// {…attributs, pts: [[lat, lon], …]}, recoupée aux bords de sa tuile (sans la
// marge, pour ne rien dessiner deux fois), un point {…attributs, lat, lon}.

// ------------------------------------------------------------------ MVT

// Le peu de protobuf qu'il faut pour lire une tuile MVT (spécification 2.1),
// jumeau de Mvt.kt : une tuile, ses couches, les objets et leurs attributs.
const MVT_POINT = 1;

function mvtLecteur(octets, debut = 0, fin = octets.length) {
  const l = {
    position: debut,
    reste: () => l.position < fin,
    varint() {
      let resultat = 0, facteur = 1;
      for (let i = 0; i < 10; i++) {
        if (l.position >= fin) throw new Error("varint tronqué");
        const octet = octets[l.position++];
        resultat += (octet & 0x7f) * facteur;
        if (!(octet & 0x80)) return resultat;
        facteur *= 128;
      }
      throw new Error("varint trop long");
    },
    tag() {
      const tag = l.varint();
      return [Math.floor(tag / 8), tag % 8];
    },
    sous() {
      const longueur = l.varint();
      if (l.position + longueur > fin) throw new Error("message tronqué");
      const sous = mvtLecteur(octets, l.position, l.position + longueur);
      l.position += longueur;
      return sous;
    },
    paquets() {
      const s = l.sous(), valeurs = [];
      while (s.reste()) valeurs.push(s.varint());
      return valeurs;
    },
    sauter(fil) {
      if (fil === 0) l.varint();
      else if (fil === 1) l.position += 8;
      else if (fil === 2) l.position += l.varint();
      else if (fil === 5) l.position += 4;
      else throw new Error(`fil protobuf inconnu : ${fil}`);
      if (l.position > fin) throw new Error("message tronqué");
    },
    fin,
  };
  return l;
}

// Une chaîne UTF-8 du message courant.
function mvtChaine(octets, l) {
  const s = l.sous();
  return MVT_TEXTE.decode(octets.subarray(s.position, s.fin));
}
const MVT_TEXTE = new TextDecoder();

function mvtZigzag(n) {
  return n % 2 ? -(n + 1) / 2 : n / 2;
}

function mvtValeur(octets, l) {
  const [champ, fil] = l.tag();
  const vue = new DataView(octets.buffer, octets.byteOffset + l.position);
  if (champ === 1 && fil === 2) return mvtChaine(octets, l);
  if (champ === 2 && fil === 5) { const v = vue.getFloat32(0, true); l.position += 4; return v; }
  if (champ === 3 && fil === 1) { const v = vue.getFloat64(0, true); l.position += 8; return v; }
  if ((champ === 4 || champ === 5) && fil === 0) return l.varint();
  if (champ === 6 && fil === 0) return mvtZigzag(l.varint());
  if (champ === 7 && fil === 0) return l.varint() !== 0;
  l.sauter(fil);
  return "";
}

// Les commandes MVT (MoveTo 1, LineTo 2, ClosePath 7) en lignes de points
// [x, y] de la tuile ; pour un point, chaque MoveTo est un objet distinct.
function mvtGeometrie(type, commandes) {
  const lignes = [];
  let courante = null, x = 0, y = 0, i = 0;
  while (i < commandes.length) {
    const commande = commandes[i++], id = commande & 7, compte = commande >>> 3;
    if (id === 1) {
      for (let k = 0; k < compte; k++) {
        if (i + 1 >= commandes.length) return lignes;
        x += mvtZigzag(commandes[i++]);
        y += mvtZigzag(commandes[i++]);
        if (type === MVT_POINT) { lignes.push([[x, y]]); courante = null; }
        else { courante = [[x, y]]; lignes.push(courante); }
      }
    } else if (id === 2) {
      if (!courante) { courante = []; lignes.push(courante); }
      for (let k = 0; k < compte; k++) {
        if (i + 1 >= commandes.length) return lignes;
        x += mvtZigzag(commandes[i++]);
        y += mvtZigzag(commandes[i++]);
        courante.push([x, y]);
      }
    } else if (id === 7) {
      courante = null;
    }
  }
  return lignes;
}

// Les couches d'une tuile : {nom: [{type, lignes, attributs}]}.
function mvtDecoder(octets) {
  const tuile = mvtLecteur(octets), couches = {};
  while (tuile.reste()) {
    const [champ, fil] = tuile.tag();
    if (champ !== 3 || fil !== 2) { tuile.sauter(fil); continue; }
    const l = tuile.sous();
    let nom = "";
    const cles = [], valeurs = [], bruts = [];
    while (l.reste()) {
      const [c, f] = l.tag();
      if (c === 1 && f === 2) nom = mvtChaine(octets, l);
      else if (c === 2 && f === 2) { const s = l.sous(); bruts.push([s.position, s.fin]); }
      else if (c === 3 && f === 2) cles.push(mvtChaine(octets, l));
      else if (c === 4 && f === 2) { const s = l.sous(); valeurs.push(mvtValeur(octets, s)); }
      else l.sauter(f);
    }
    const objets = [];
    for (const [debut, fin] of bruts) {
      const o = mvtLecteur(octets, debut, fin);
      let type = 0, balises = [], commandes = [];
      while (o.reste()) {
        const [c, f] = o.tag();
        if (c === 2 && f === 2) balises = o.paquets();
        else if (c === 3 && f === 0) type = o.varint();
        else if (c === 4 && f === 2) commandes = o.paquets();
        else o.sauter(f);
      }
      if (!type) continue;
      const attributs = {};
      for (let i = 0; i + 1 < balises.length; i += 2) {
        if (balises[i] < cles.length && balises[i + 1] < valeurs.length) attributs[cles[balises[i]]] = valeurs[balises[i + 1]];
      }
      objets.push({ type, lignes: mvtGeometrie(type, commandes), attributs });
    }
    couches[nom] = objets;
  }
  return couches;
}

// ------------------------------------------------------------------ tuiles du lot

const TUILE_ZOOM = 14, TUILE_ETENDUE = 4096, TUILE_RAYON = 6378137;

function mercatorY(lat) {
  return TUILE_RAYON * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
}

// Les bornes d'une tuile XYZ du zoom 14 (lot.bornes_tuile).
function bornesTuile(x, y) {
  const n = 2 ** TUILE_ZOOM;
  const lat = (v) => Math.atan(Math.sinh(Math.PI * (1 - 2 * v / n))) * 180 / Math.PI;
  return { s: lat(y + 1), w: x / n * 360 - 180, n: lat(y), e: (x + 1) / n * 360 - 180 };
}

// Une ligne en unités de tuile, recoupée au carré [0, ETENDUE] (Liang-Barsky,
// segment par segment) : les morceaux qui restent dans la tuile, sans la marge.
function recouper(ligne) {
  const E = TUILE_ETENDUE;
  if (ligne.every(([x, y]) => x >= 0 && x <= E && y >= 0 && y <= E)) return [ligne];
  const morceaux = [];
  let courant = null;
  for (let i = 1; i < ligne.length; i++) {
    const [x0, y0] = ligne[i - 1], [x1, y1] = ligne[i];
    const dx = x1 - x0, dy = y1 - y0;
    let t0 = 0, t1 = 1, dehors = false;
    for (const [p, q] of [[-dx, x0], [dx, E - x0], [-dy, y0], [dy, E - y0]]) {
      if (p === 0) { if (q < 0) { dehors = true; break; } continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) { dehors = true; break; } if (r > t0) t0 = r; }
      else { if (r < t0) { dehors = true; break; } if (r < t1) t1 = r; }
    }
    if (dehors) { courant = null; continue; }
    const a = [x0 + t0 * dx, y0 + t0 * dy], b = [x0 + t1 * dx, y0 + t1 * dy];
    // Le morceau continue tant que le segment part d'où finissait le précédent.
    if (!courant || t0 > 0) { courant = [a]; morceaux.push(courant); }
    courant.push(b);
    if (t1 < 1) courant = null;
  }
  return morceaux.filter((m) => m.length > 1);
}

// Les objets d'une tuile du lot, au format de lot.lire_calque : {couche: [objet]}.
function objetsDeTuile(octets, x, y) {
  const { s, w, n, e } = bornesTuile(x, y);
  const my0 = mercatorY(s), my1 = mercatorY(n);
  const latlon = ([px, py]) => {
    const my = my1 - py / TUILE_ETENDUE * (my1 - my0);
    return [Math.atan(Math.sinh(my / TUILE_RAYON)) * 180 / Math.PI, w + px / TUILE_ETENDUE * (e - w)];
  };
  const objets = {};
  for (const [nom, couche] of Object.entries(mvtDecoder(octets))) {
    const liste = objets[nom] = [];
    for (const objet of couche) {
      if (objet.type === MVT_POINT) {
        for (const [p] of objet.lignes) {
          const [lat, lon] = latlon(p);
          liste.push({ ...objet.attributs, lat, lon });
        }
        continue;
      }
      for (const ligne of objet.lignes) {
        for (const morceau of recouper(ligne)) liste.push({ ...objet.attributs, pts: morceau.map(latlon) });
      }
    }
  }
  return objets;
}

// Les tuiles décodées, gardées comme le faisait le cache du serveur : un
// déplacement ne lit que les tuiles neuves du bord de la vue.
const TUILES_MAX = 512;
const tuilesDecodees = new Map();

function tuileDuLot(lot, x, y) {
  const cle = `${lot.case}/${lot.date}/${x}/${y}`;
  let promesse = tuilesDecodees.get(cle);
  if (promesse) {
    tuilesDecodees.delete(cle);          // la plus récente en dernier : la plus ancienne part la première
    tuilesDecodees.set(cle, promesse);
    return promesse;
  }
  promesse = fetch(`/calques/${lot.case}/${x}/${y}?v=${lot.date}`).then(async (reponse) => {
    if (reponse.status === 204) return {};
    if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`);
    return objetsDeTuile(new Uint8Array(await reponse.arrayBuffer()), x, y);
  });
  promesse.catch(() => tuilesDecodees.delete(cle));     // une tuile en échec se redemandera
  tuilesDecodees.set(cle, promesse);
  while (tuilesDecodees.size > TUILES_MAX) tuilesDecodees.delete(tuilesDecodees.keys().next().value);
  return promesse;
}

// Le calque de la vue à partir de la réponse du serveur ({lot, couches,
// tuiles, bornes}) : les mêmes clés que lot.lire_calque, un franchissement ou
// une jonction vus une seule fois d'une tuile à l'autre.
async function lireCalqueDuLot(reponse) {
  const resultat = Object.fromEntries([...new Set(Object.values(reponse.couches))].map((c) => [c, []]));
  const vus = new Set();
  const tuiles = await Promise.all(reponse.tuiles.map(([x, y]) => tuileDuLot(reponse.lot, x, y)));
  for (const objets of tuiles) {
    for (const [nom, cle] of Object.entries(reponse.couches)) {
      for (const objet of objets[nom] || []) {
        if ("lat" in objet && objet.cle !== undefined) {
          if (vus.has(objet.cle)) continue;
          vus.add(objet.cle);
        }
        resultat[cle].push(objet);
      }
    }
  }
  return { ...resultat, bornes: reponse.bornes };
}
