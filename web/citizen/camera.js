// Caméra directe de la page citoyen : flux vidéo de la caméra arrière, capture par un grand bouton rond, aperçu,
// « Reprendre ». Le flux est arrêté après capture, en arrière-plan et à la fermeture (caméra et batterie libérées).
// Repli sur le champ natif <input capture> seulement si la caméra est inaccessible (refus, absente, sans HTTPS).
const $ = (s) => document.querySelector(s);

export function installerCamera({ surPhoto, surReprendre }) {
  const zone = $("#camera");
  const video = $("#camera-video");
  const repli = $("#photo-repli");
  const etat = $("#camera-etat");
  const reessayer = $("#camera-reessayer");
  const reprendre = $("#reprendre");
  let flux = null;
  let actif = false;          // mode caméra choisi (sinon repli)
  let enAttente = false;      // une photo capturée attend l'envoi : ne pas relancer le flux

  const arreter = () => {
    for (const piste of flux?.getTracks() || []) piste.stop();
    flux = null;
    video.srcObject = null;
  };
  const montrerRepli = (message) => {
    actif = false;
    arreter();
    zone.hidden = true;
    repli.hidden = false;
    etat.hidden = !message;
    etat.textContent = message || "";
  };

  async function demarrer() {
    reessayer.hidden = true;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      return montrerRepli("Caméra directe indisponible sur cette page (connexion non sécurisée) : utilisez le bouton ci-dessous pour prendre la photo.");
    }
    try {
      flux = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      actif = true;
      enAttente = false;
      video.srcObject = flux;
      await video.play().catch(() => {});
      zone.hidden = false;
      repli.hidden = true;
      etat.hidden = true;
      reprendre.hidden = true;
    } catch (err) {
      if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
        montrerRepli("La caméra est déjà utilisée par une autre application. Fermez-la, puis réessayez.");
        reessayer.hidden = false;
      } else if (err?.name === "NotAllowedError" || err?.name === "SecurityError") {
        montrerRepli("Accès à la caméra refusé. Autorisez la caméra pour ce site dans les réglages du navigateur, ou prenez la photo avec le bouton ci-dessous.");
      } else {
        montrerRepli("Aucune caméra disponible : prenez la photo avec le bouton ci-dessous.");
      }
    }
  }

  async function capturer() {
    if (!flux || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
    arreter();                       // la caméra est libérée dès la capture
    zone.hidden = true;
    enAttente = true;
    reprendre.hidden = false;
    if (blob) await surPhoto(blob);  // réduction à 1024 px / JPEG 0,8 par la page (compress)
  }

  $("#capturer").addEventListener("click", capturer);
  reessayer.addEventListener("click", demarrer);
  reprendre.addEventListener("click", () => { surReprendre(); demarrer(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) arreter();
    else if (actif && !enAttente && !flux) demarrer();
  });
  window.addEventListener("pagehide", arreter);

  repli.hidden = true;               // caméra d'abord ; le repli n'apparaît qu'en cas d'échec
  demarrer();
  return {
    /** Après un envoi : reprendre la caméra pour la photo suivante (si elle est utilisée). */
    apresEnvoi() { reprendre.hidden = true; if (actif) demarrer(); else { enAttente = false; } },
  };
}
