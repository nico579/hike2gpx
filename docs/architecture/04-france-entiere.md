# Préparation de la France métropolitaine sur le serveur

## Taille des unités

Le format final de routage suit la grille native de BRouter : une RD5 couvre 5° × 5°. Le rectangle englobant du contour Geofabrik traverse 12 cases, dont **9 touchent réellement** la France métropolitaine et la Corse. Chaque RD5 publiée devra contenir **tous** les chemins de sa case française ; la RD5 produite aujourd'hui pour une petite zone porte le même nom, mais ne contient que cette zone et ne peut pas servir de tuile nationale.

La stratégie de distribution et la preuve de découpage des RD5 en sous-cases de 1° sont dans [Mailles calculées et téléchargées](05-mailles-telechargeables.md). Pour une RD5 réellement complète, il faut aussi l'OSM des portions étrangères de sa case ; l'extrait Geofabrik France ne suffit pas aux frontières.

La collecte IGN et OSM utilise des tuiles de 0,05°. Le rectangle du contour Geofabrik en contient 69 290 ; 36 340 sont entièrement dans le contour. Les tuiles côtières et frontalières partiellement couvertes s'ajoutent à ce dernier nombre. Les franchissements et le calque officiel peuvent rester découpés en zones de téléchargement plus petites que 5°.

## Première mesure dans la VM

Sur Garéoult, `[43.30, 6.00, 43.35, 6.05]`, la requête atteint quatre tuiles de 0,05°. Après correction du Java de la VM, le dossier de données neuf occupe 20,7 Mo ; le paquet publié occupe 2,6 Mo, dont 2,3 Mo de chemins officiels et 124 Ko de RD5 partielle. La première collecte IGN et OSM a pris 2 min 09 s ; la fabrication sur données déjà en cache, 6,35 s. Ces chiffres ne représentent pas une densité nationale moyenne et ne prédisent pas la taille d'une RD5 complète.

La VM VirtualBox se trouve déjà sur le disque D: du PC. Son VDI dynamique et sa partition ext4 ont été agrandis de 25 à 100 Go ; après redémarrage, 77 Go étaient libres dans la VM. La copie de sécurité temporaire du VDI a été retirée après vérification du système et du paquet témoin. Le service de test systemd sur le port 8796 a repassé `vm_smoke.py --prepared --route`.

## Préparation nationale

1. Télécharger et indexer localement l'[extrait OSM France de Geofabrik](https://download.geofabrik.de/europe/france.html), puis mesurer la place du PBF temporaire et de l'index. L'outil `deploy/linux/france_osm.py` vérifie qu'il reste au moins 40 Gio avant de lancer l'import. Le fichier France de Geofabrik couvre la métropole ; les territoires d'outre-mer demanderont d'autres extraits.
2. Préparer une source locale des tronçons [BD TOPO de l'IGN](https://geoservices.ign.fr/bdtopo) pour l'ensemble du territoire. Les 36 340 tuiles entièrement couvertes rendraient les appels WFS actuels beaucoup trop nombreux pour cette tâche nationale. Le [catalogue IGN](https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/telechargement/) donne 13 archives régionales de l'édition 2026-09, totalisant 21,10 Gio compressés ; elles seront traitées l'une après l'autre. Le service WFS reste adapté aux zones ponctuelles.
3. Fabriquer les 9 RD5 complètes par blocs de données compatibles avec la mémoire disponible, puis publier atomiquement chaque RD5. Vérifier les raccords aux limites des blocs et des cases BRouter. Les paquets de calque et de franchissements pourront suivre des zones plus petites, mais référenceront la même RD5 complète.
4. Mesurer sur plusieurs régions la taille des RD5, les durées et l'espace temporaire maximal avant de planifier les renouvellements. Le job s'arrête si l'espace libre devient insuffisant ; les fichiers intermédiaires RD5 sont supprimés après succès, les paquets remplacés après 24 heures, et l'ancien extrait OSM après publication de son remplaçant.

Le calcul national n'est pas encore achevé. L'indexation OSM nationale, trop lente pour ce premier essai, a été arrêtée ; son PBF source a été conservé et l'index temporaire effacé. Le GeoPackage régional PACA a été extrait et vérifié. La fabrication d'une RD5 complète à partir des sources locales reste à coder et à mesurer.
