"""La règle du pare-feu de Windows pour le partage au téléphone (pare_feu.py),
éprouvée sans Windows : PowerShell et la fenêtre UAC sont remplacés."""
import base64

from hike2gpx import pare_feu
from hike2gpx.application import Application

PROG = r"D:\hike2gpx-windows-x86_64\hike2gpx.exe"
NOTRE = f"{pare_feu.NOM}|True|1|2147483647"          # la règle du partage, tous profils


def script(commande):
    """Le script PowerShell d'une commande (-EncodedCommand, UTF-16)."""
    return base64.b64decode(commande[-1]).decode("utf-16-le")


class Windows:
    """Un pare-feu simulé : les règles du programme (nom|actif|action|profils),
    telles que les lit l'objet COM, et les élévations demandées."""

    def __init__(self, regles=(), reponse_uac=0):
        self.regles = list(regles)
        self.reponse_uac = reponse_uac
        self.elevations = []

    def executer(self, commande):
        lecture = script(commande)
        assert "HNetCfg.FwPolicy2" in lecture and f"-eq '{PROG}'" in lecture
        return "\n".join(self.regles)

    def elever(self, commande):
        # Le programme lui-même, relancé en administrateur (la fenêtre UAC nomme hike2gpx) :
        # on garde le script que sa commande firewall appliquera.
        assert commande[-3:] == ["firewall", "--program", PROG], commande
        self.elevations.append(pare_feu.script_creer(commande[-1]))
        if self.reponse_uac == 0:
            self.regles = [r for r in self.regles if r.split("|")[2] != "0" and not r.startswith(pare_feu.NOM)] + [NOTRE]
        return self.reponse_uac


def autoriser(w):
    return pare_feu.autoriser(w.executer, w.elever, plateforme="win32", prog=PROG)


def test_rien_a_faire_hors_de_windows():
    w = Windows()
    assert pare_feu.autoriser(w.executer, w.elever, plateforme="linux", prog=PROG) == "inutile"
    assert w.elevations == []


def test_la_regle_en_place_ne_demande_rien():
    w = Windows([NOTRE, "hike2gpx.exe|True|1|2"])
    assert autoriser(w) == "ok" and w.elevations == []


def test_la_regle_manquante_se_cree_apres_une_demande_uac():
    w = Windows()
    assert autoriser(w) == "creee"
    [creation] = w.elevations
    assert "New-NetFirewallRule" in creation and f"-Program '{PROG}'" in creation
    assert "-LocalPort 8799-8808" in creation and "-RemoteAddress LocalSubnet" in creation
    assert "-Direction Inbound" in creation and "-Action Allow" in creation and "-Profile Any" in creation


def test_le_blocage_laisse_par_la_fenetre_de_windows_est_retire():
    # Ce qu'a créé la fenêtre « Autoriser l'accès » sur le PC de Nico : privé
    # autorisé, public bloqué. Le blocage l'emporte : la règle seule ne suffit pas.
    w = Windows([NOTRE, "hike2gpx.exe|True|1|2", "hike2gpx.exe|True|0|4"])
    assert autoriser(w) == "creee"
    assert "-Action -eq 'Block'" in w.elevations[0].replace("$_.Action -eq 'Block'", "-Action -eq 'Block'")
    assert "Remove-NetFirewallRule" in w.elevations[0]
    assert autoriser(w) == "ok", "plus de blocage : rien à redemander"


def test_une_regle_incomplete_est_remplacee():
    # Le seul profil privé (le réglage fait à la main le 2026-11-05), désactivée, ou d'un autre nom :
    for regles in ([f"{pare_feu.NOM}|True|1|2"], [f"{pare_feu.NOM}|False|1|2147483647"], ["autre|True|1|2147483647"]):
        w = Windows(regles)
        assert autoriser(w) == "creee", regles


def test_refus_ou_echec_de_la_demande():
    assert autoriser(Windows(reponse_uac=None)) == "refuse"
    assert autoriser(Windows(reponse_uac=1)) == "erreur"


def test_une_apostrophe_dans_le_chemin_est_echappee():
    assert "-Program 'C:\\Jean''s\\hike2gpx.exe'" in pare_feu.script_creer("C:\\Jean's\\hike2gpx.exe")
    assert "-eq 'C:\\Jean''s\\hike2gpx.exe'" in pare_feu.script_lire("C:\\Jean's\\hike2gpx.exe")


def test_l_application_ne_verifie_qu_une_fois_par_seance(tmp_path, monkeypatch):
    a = Application(tmp_path)
    appels = []
    a.autoriser_pare_feu = lambda: appels.append(1) or "creee"
    monkeypatch.setattr(a.partage, "ouvrir", lambda: {"ouvert": True})
    assert a.partager({"ouvrir": True}) == {"ouvert": True, "pare_feu": "creee"}
    assert a.partager({"ouvrir": True})["pare_feu"] == "creee"
    assert appels == [1], "la règle en place : PowerShell n'est plus relancé"
    a._pare_feu = None
    a.autoriser_pare_feu = lambda: appels.append(2) or "refuse"
    assert a.partager({"ouvrir": True})["pare_feu"] == "refuse"
    a.partager({"ouvrir": True})
    assert appels == [1, 2, 2], "refusée : redemandée au partage suivant"


def test_la_relance_en_administrateur_est_hike2gpx_et_non_powershell(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", PROG)
    assert pare_feu.commande_elevee(PROG) == [PROG, "firewall", "--program", PROG]
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    commande = pare_feu.commande_elevee(PROG)
    assert commande[1:] == ["-m", "hike2gpx", "firewall", "--program", PROG], "depuis les sources"


def test_la_commande_firewall_pose_la_regle(monkeypatch):
    from hike2gpx import __main__ as principal
    appels = []
    monkeypatch.setattr(pare_feu, "creer", lambda prog: appels.append(prog) or 0)
    assert principal.main(["firewall", "--program", PROG]) == 0
    assert appels == [PROG]
