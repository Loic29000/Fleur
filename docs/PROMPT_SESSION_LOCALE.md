Tu travailles sur mon PC Windows, dans le dossier `C:\Users\loich\Desktop\HUD Poker`. Je joue au poker en ligne sur **Winamax**, principalement en **cash game**. On a commencé un HUD façon **PokerTracker 4** appelé **Fleur**, en Python. Ta mission : le récupérer, le valider sur mes vraies mains, le corriger, puis développer la suite. Réponds-moi en français.

## 1. Récupérer le projet

Le code est sur GitHub : dépôt `loic29000/fleur`, branche `claude/poker-hud-winamax-1njcrx`.

1. Clone cette branche dans le dossier courant. Si le dossier contient déjà des fichiers, clone dans un sous-dossier `fleur`. Continue à travailler sur cette branche, commite au fur et à mesure et pousse-la.
2. Vérifie que Python 3.11 ou plus récent est installé. Sinon, propose-moi de l'installer (par exemple `winget install Python.Python.3.12`) et attends mon accord.
3. Dans un environnement virtuel `.venv`, lance `pip install -r requirements-dev.txt`, puis `python -m pytest`. Les 14 tests doivent passer.

Si le dépôt est inaccessible, préviens-moi avant de recréer quoi que ce soit. L'architecture est décrite plus bas.

## 2. Ce qui existe déjà

Paquet `fleur/` :

- `parser.py` : lit les historiques Winamax. Une main commence par `Winamax Poker - CashGame - HandId: #...`. Le module extrait les sièges, le bouton, les blindes, les actions par street (`raises X to Y`, `and is all-in`), le board, `collected`, les cartes montrées, le `Total pot | Rake`, et les lignes non reconnues (`hand.unknown_lines`). Il est tolérant aux symboles monétaires, aux virgules, au BOM et aux pseudos avec espaces.
- `stats.py` : produit des compteurs par main et par joueur (opportunités et réalisations), puis des stats PT4 :
  - préflop : VPIP, PFR, 3-bet, fold au 3-bet, 4-bet, RFI, limp, cold call, squeeze, ATS (vol), fold et 3-bet face au vol ;
  - postflop : c-bet flop et turn, fold et relance face au c-bet, donk, check-raise, AF, AFq ;
  - abattage et résultats : WTSD, W$SD, WWSF, BB/100 et gains.

  Il attribue aussi les positions (BTN/SB/BB/CO/HJ/…) et calcule le gain net, avec remboursement automatique des mises non suivies.
- `db.py` : base SQLite (`hands`, `player_hands` avec une colonne par compteur, `files` pour les positions de lecture). Les doublons sont ignorés et les agrégats se font par `SUM`.
- `watcher.py` : relit le dossier d'historiques toutes les secondes et ne lit que les octets nouveaux. Une main n'est traitée qu'une fois complète (`*** SUMMARY ***` et ligne vide, ou fichier stable depuis 2 s). Il détecte tout seul `Documents\Winamax Poker\accounts\<pseudo>\history` et ignore les fichiers `summary`.
- `diagnostics.py` : contrôle chaque main. Il note les lignes inconnues, les joueurs absents des sièges, les mains sans big blind et surtout la **cohérence des gains** : la somme des gains doit valoir −rake et le pot recalculé doit égaler « Total pot ».
  - Les problèmes sont écrits dans `%APPDATA%\Fleur\diagnostic\` (`mains_illisibles.txt`, `lignes_inconnues.txt`, `incoherences.txt`, `fenetres.txt`).
  - Le journal est `%APPDATA%\Fleur\fleur.log`.
  - `make_report()` crée un zip avec tout ça.
- `config.py` : `%APPDATA%\Fleur\config.json`. On y règle les lignes du panneau (`hud_lines`), les stats du popup, les seuils de couleur, `show_hero`, `hero_at_bottom`, la police et l'opacité.
- `hud/win32.py` : fonctions Win32 via ctypes pour lister les fenêtres, trouver celle dont le titre contient le nom de la table, lire sa zone cliente et rattacher le panneau à la table (`GWLP_HWNDPARENT`) pour qu'il reste au-dessus d'elle et se réduise avec elle.
- `hud/layouts.py` : positions relatives des panneaux par format de table (2 à 10 joueurs). Le siège visuel 0 est en bas, là où Winamax place le héros, puis on tourne dans le sens horaire. Les positions sont sauvegardées dans `layouts.json`.
- `hud/overlay.py` : PySide6.
  - Un panneau sans bordure par adversaire. Il suit la fenêtre toutes les 150 ms et gère la mise à l'échelle Windows (125 %, 150 %).
  - On le déplace à la souris et la position est mémorisée. Un double-clic ouvre un popup détaillé avec les échantillons.
  - Les couleurs dépendent de seuils. Une table est retirée quand sa fenêtre disparaît.
- `hud/tray.py` : icône dans la barre des tâches. Elle affiche l'état et permet de masquer ou afficher le HUD, recharger la config, réinitialiser les positions, ouvrir les dossiers, créer un rapport de diagnostic et quitter. Des notifications signalent les problèmes.
- `cli.py` : `python -m fleur [hud|import|stats [pseudo]|stats --list|config|windows|diagnostic]`, plus `--history <dossier>`.
- Fichiers annexes : `lancer_hud.bat`, `lancer_hud_silencieux.bat` (pythonw), `build_exe.bat` (PyInstaller).
- Tests : `tests/` avec 3 mains de démonstration dans `tests/fixtures/cash_6max.txt`. **Ces mains ont été écrites à la main d'après le format supposé. Le code n'a jamais tourné sur de vraies mains ni sous Windows.**

## 3. Étape 1 : valider sur mes vraies mains (priorité absolue)

1. Lance `python -m fleur config` pour vérifier que mon dossier d'historiques est trouvé. Sinon, cherche-le et règle `history_dirs`.
2. Lance `python -m fleur import`, puis examine `%APPDATA%\Fleur\diagnostic\`.
3. Pour chaque type de problème : lis les vraies lignes, corrige `parser.py` et/ou `stats.py`, réimporte avec une base neuve (supprime `fleur.db`) et recommence jusqu'à **zéro main illisible, zéro incohérence et zéro ligne inconnue utile**. Points à vérifier en particulier :
   - format exact de l'en-tête et de `Table:` ;
   - sémantique de `raises X to Y` ;
   - présence ou non de `Uncalled bet` ;
   - `collected` qui inclut ou non la mise non suivie ;
   - side pots ;
   - joueurs assis sans jouer, blindes mortes, straddle ;
   - Omaha (4 ou 5 cartes) ;
   - tables 2, 5 et 6 joueurs ;
   - accents et encodage.
4. Contrôle par sondage : prends 3 ou 4 mains au hasard et recalcule à la main les compteurs d'un joueur (VPIP, PFR, 3-bet, c-bet, gains) pour les comparer à `python -m fleur stats <pseudo>`.
5. Ajoute 5 à 10 vraies mains représentatives **anonymisées** (pseudos remplacés) dans `tests/fixtures/` avec les tests correspondants. Ne commite jamais mes historiques bruts ni mon pseudo.

## 4. Étape 2 : valider le HUD en direct (avec moi)

1. Lance `lancer_hud.bat` et demande-moi d'ouvrir une table Winamax et de jouer quelques mains.
2. Lance `python -m fleur windows` pour voir le vrai titre des fenêtres de table. Ajuste `find_table_window` si le nom de table n'y figure pas tel quel, en t'appuyant aussi sur la classe ou le processus de la fenêtre si besoin.
3. Vérifie avec moi :
   - les panneaux sont sur les bons sièges et il n'y a pas de décalage d'un siège : le héros est-il vraiment en bas, les sièges sont-ils numérotés dans le sens horaire ?
   - ils suivent la fenêtre quand je la déplace ou la redimensionne, et se cachent quand je la réduis ;
   - ils restent corrects à 125 % ou 150 % d'échelle et en multi-tables ;
   - le HUD reste léger, sans scintillement ni ralentissement.

   Corrige les positions par défaut de `layouts.py` d'après une capture d'écran que je te fournirai.
4. Vérifie que l'icône et les notifications marchent, et que `build_exe.bat` produit un `Fleur.exe` qui fonctionne.

## 5. Étape 3 : nouvelles fonctions (dans cet ordre, une à la fois, avec tests)

1. **Notes et étiquettes sur les joueurs** : clic droit sur un panneau → étiquette (fish, reg, nit, LAG, maniaque, perso) avec une couleur, plus une note libre. Le tout est stocké en base (table `player_notes`) et affiché sur le panneau (pastille de couleur, indicateur de note). On peut éditer dans une petite fenêtre.
2. **Mains montrées à l'abattage** : dans le popup, les 5 à 10 dernières mains montrées par le joueur, avec ses cartes, le board, sa ligne d'action résumée (ex. « 3-bet préflop, c-bet flop, call turn ») et le résultat.
3. **Filtres** : stats calculées selon le format de table (même nombre de joueurs max, ou tête-à-tête à part) et selon la limite (même big blind), avec une option pour tout cumuler. À régler dans la config et le menu de l'icône. Pense à indexer les colonnes nécessaires (`max_seats`, `bb`) et à joindre `hands`.
4. **Classement automatique** : une icône ou un badge de profil (fish, nit, TAG, LAG, maniaque) calculé à partir de VPIP, PFR, AF et du nombre de mains, affiché seulement au-delà d'un seuil de mains configurable.
5. **Stats par position** dans le popup : RFI, 3-bet et fold face au vol par position (UTG, HJ, CO, BTN, SB, BB). Il faudra ajouter la position dans `player_hands`.
6. **Tableau de bord du héros** (fenêtre séparée ou page HTML locale) : courbe de gains (en € et en big blinds, avec et sans abattage), BB/100 par position et par limite, résultats par session.
7. **Détection de fuites** : compare mes stats à des fourchettes de référence de cash game 6-max et produit une liste d'alertes priorisées (ex. « fold au 3-bet trop élevé : 68 % contre 45–55 % »).

## Contraintes

- Le HUD lit uniquement les fichiers d'historique : pas de lecture d'écran, pas d'injection dans le client Winamax, **aucune aide à la décision en temps réel** (pas de conseil d'action, pas de solveur). Ça doit rester conforme aux règles Winamax.
- Le HUD ne doit jamais planter à cause d'une main bizarre : il journalise et passe à la suite.
- Garde la configuration rétrocompatible : de nouvelles clés avec des valeurs par défaut.
- Après chaque étape : tests verts, commit, push, et un court résumé pour moi de ce qui marche, de ce qui reste et de ce que je dois tester.
