"""Le pare-feu de Windows et le partage au téléphone.

Windows bloque ce qui entre tant qu'aucune règle ne l'autorise : le téléphone
voit le PC (le ping passe) mais pas son partage (essai du 2026-11-05, Wi-Fi
classé « Public », aucune règle). Comme les applications qui partagent sur le
réseau local (LocalSend, Syncthing…), hike2gpx crée sa règle lui-même, au
premier partage, après une seule demande d'autorisation administrateur (la
fenêtre UAC de Windows) :

  - entrante, pour le seul programme lancé (sys.executable : hike2gpx.exe, ou
    python.exe depuis les sources), sur les seuls ports du partage ;
  - depuis le réseau local seulement (RemoteAddress LocalSubnet), sur tous les
    profils : un réseau « Public » de la maison n'empêche plus rien, et le
    type de réseau reste le choix de l'utilisateur, pas celui d'une appli.

Le partage garde ses propres protections (partage.py) : fermé par défaut,
jeton renouvelé à chaque ouverture, adresses privées seulement. La règle est
lue sans droits ; elle n'est recréée que si elle manque ou vise un autre
programme (un nouveau dossier après une mise à jour). Ailleurs que sous
Windows, rien à faire.
"""
from __future__ import annotations

import base64
import logging
import subprocess
import sys

from . import partage

journal = logging.getLogger(__name__)
NOM = "hike2gpx, partage au téléphone"
PORTS = f"{partage.PORT}-{partage.PORT + partage.PLAGE - 1}"
ATTENTE_S = 120             # le temps de répondre à la fenêtre UAC


def programme() -> str:
    return sys.executable


def _powershell(script: str) -> list:
    """powershell.exe avec le script encodé : aucun guillemet à échapper sur la ligne de commande."""
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]


def _texte(valeur: str) -> str:
    """Une chaîne PowerShell entre apostrophes."""
    return "'" + valeur.replace("'", "''") + "'"


def script_lire(prog: str) -> str:
    """Les règles entrantes du programme, une par ligne : nom|actif|action|profils.
    Lues par l'objet COM du pare-feu (HNetCfg.FwPolicy2), que Windows laisse lire
    sans droits, au contraire de Get-NetFirewallRule (« Accès refusé », essai du
    2026-11-05) ; ses valeurs ne dépendent pas de la langue : action 1 autorise,
    0 bloque ; profils en bits, 2 privé, 4 public, 0x7FFFFFFF tous."""
    # UTF-8 en sortie : sinon la console rend « téléphone » en « t‚l‚phone »
    # (page de code OEM) et la règle ne serait jamais reconnue.
    return ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
            "(New-Object -ComObject HNetCfg.FwPolicy2).Rules | "
            f"Where-Object {{ $_.Direction -eq 1 -and $_.ApplicationName -eq {_texte(prog)} }} | "
            "ForEach-Object { \"$($_.Name)|$($_.Enabled)|$($_.Action)|$($_.Profiles)\" }")


def script_creer(prog: str) -> str:
    """Retire les blocages entrants du programme, puis pose la règle du partage.
    Sous Windows, un blocage l'emporte toujours sur une autorisation : la fenêtre
    « Autoriser l'accès » de Windows, cochée par défaut sur le seul réseau privé,
    crée un blocage pour le réseau public (essai du 2026-11-05), qui rendrait la
    règle sans effet sur un Wi-Fi classé « Public ». Seuls les blocages de ce
    programme sont retirés."""
    return (f"$ErrorActionPreference = 'Stop'; "
            f"Get-NetFirewallApplicationFilter -Program {_texte(prog)} | Get-NetFirewallRule | "
            "Where-Object { $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' } | Remove-NetFirewallRule; "
            f"Remove-NetFirewallRule -DisplayName {_texte(NOM)} -ErrorAction SilentlyContinue; "
            f"New-NetFirewallRule -DisplayName {_texte(NOM)} -Direction Inbound -Program {_texte(prog)} "
            f"-Protocol TCP -LocalPort {PORTS} -RemoteAddress LocalSubnet -Profile Any -Action Allow | Out-Null")


PUBLIC = 4


def regle_a_jour(sortie: str) -> bool:
    """La règle du partage active, qui autorise le profil public (et donc tous),
    et aucun blocage actif du programme, qui l'emporterait sur elle."""
    autorise, bloque = False, False
    for ligne in sortie.splitlines():
        champs = ligne.strip().rsplit("|", 3)
        if len(champs) != 4 or champs[1] != "True":
            continue
        nom, _, action, profils = champs
        try:
            profils = int(profils)
        except ValueError:
            continue
        if action == "0":
            bloque = True
        elif action == "1" and nom == NOM and profils & PUBLIC:
            autorise = True
    return autorise and not bloque


def _executer(commande: list) -> str:
    resultat = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return resultat.stdout


def _elever(commande: list) -> int | None:
    """La commande lancée en administrateur (fenêtre UAC) ; son code de sortie, None si l'utilisateur refuse."""
    import ctypes
    from ctypes import wintypes

    class Infos(ctypes.Structure):           # SHELLEXECUTEINFOW
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    infos = Infos(cbSize=ctypes.sizeof(Infos), fMask=0x40,      # SEE_MASK_NOCLOSEPROCESS
                  lpVerb="runas", lpFile=commande[0], lpParameters=subprocess.list2cmdline(commande[1:]), nShow=0)
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(infos)):
        return None                                             # ERROR_CANCELLED : refusé
    try:
        ctypes.windll.kernel32.WaitForSingleObject(infos.hProcess, ATTENTE_S * 1000)
        code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(infos.hProcess, ctypes.byref(code))
        return code.value
    finally:
        ctypes.windll.kernel32.CloseHandle(infos.hProcess)


def commande_elevee(prog: str) -> list:
    """Le programme lui-même, relancé pour poser la règle : la fenêtre UAC nomme
    hike2gpx, avec son icône, et non « Windows PowerShell » (remarque de Nico du
    2026-11-05). Figé, l'exécutable ; depuis les sources, pythonw -m hike2gpx."""
    from . import bureau
    return [*bureau.commande_programme(), "firewall", "--program", prog]


def creer(prog: str) -> int:
    """La commande firewall, lancée en administrateur : retire les blocages du
    programme et pose la règle, dans une console cachée. Rend le code de sortie."""
    resultat = subprocess.run(_powershell(script_creer(prog)), capture_output=True, timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return resultat.returncode


def autoriser(executer=None, elever=None, plateforme: str | None = None, prog: str | None = None) -> str:
    """Vérifie, et crée au besoin, la règle du partage. Rend « inutile » hors de
    Windows, « ok » si elle était là, « creee », « refuse » si l'utilisateur a
    refusé la fenêtre UAC, ou « erreur »."""
    if (plateforme or sys.platform) != "win32":
        return "inutile"
    executer, elever, prog = executer or _executer, elever or _elever, prog or programme()
    try:
        if regle_a_jour(executer(_powershell(script_lire(prog)))):
            return "ok"
        code = elever(commande_elevee(prog))
        if code is None:
            journal.warning("Pare-feu : autorisation refusée, le téléphone ne joindra pas le partage")
            return "refuse"
        if code == 0 and regle_a_jour(executer(_powershell(script_lire(prog)))):
            journal.info("Pare-feu : règle « %s » créée pour %s", NOM, prog)
            return "creee"
        journal.warning("Pare-feu : création de la règle en échec (code %s)", code)
    except (OSError, subprocess.SubprocessError) as exc:
        journal.warning("Pare-feu : %s", exc)
    return "erreur"
