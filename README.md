# Fleur — HUD de poker pour Winamax

Fleur affiche les statistiques de tes adversaires directement sur les tables
Winamax, comme PokerTracker 4. Il lit les **historiques de mains** que le client
Winamax écrit sur ton disque : aucune lecture d'écran, aucune interaction avec le
logiciel Winamax.

![aperçu](docs/hud_preview.png)

## Installation (Windows)

1. Installer [Python 3.11+](https://www.python.org/downloads/) (cocher *Add python.exe to PATH*).
2. Dans le dossier du projet :
   ```bat
   pip install -r requirements.txt
   ```
3. Dans les options du client Winamax, vérifier que l'enregistrement de
   l'historique des mains sur le disque est activé.

## Utilisation

```bat
python -m fleur              :: importe l'historique existant puis lance le HUD
python -m fleur import       :: importe seulement
python -m fleur stats        :: joueurs les plus rencontrés
python -m fleur stats Pseudo :: toutes les stats d'un joueur
python -m fleur stats --list :: liste des stats disponibles
python -m fleur config       :: emplacements de la config, de la base, des historiques
python -m fleur windows      :: titres des fenêtres ouvertes (diagnostic)
python -m fleur diagnostic   :: crée un rapport zip sur le bureau
```

Ou double-cliquer sur `lancer_hud.bat` (avec console) ou
`lancer_hud_silencieux.bat` (sans console, tout passe par l'icône).

### Icône dans la barre des tâches

Une fleur rose apparaît près de l'horloge. Clic droit :

- état (tables suivies, mains de la session, problèmes de lecture) ;
- **Masquer / Afficher le HUD** (ou double-clic sur l'icône) ;
- **Recharger la configuration** après avoir modifié `config.json` ;
- **Réinitialiser la position des panneaux** ;
- ouvrir le dossier de configuration ou celui des historiques ;
- **Créer un rapport de diagnostic** ;
- quitter.

### Diagnostic

Fleur contrôle chaque main lue : lignes non reconnues, joueurs inconnus, et
surtout **cohérence des gains** (la somme des gains et pertes doit égaler le
rake, et le pot recalculé doit égaler le « Total pot » de Winamax). Tout écart
est consigné dans `%APPDATA%\Fleur\diagnostic\` avec la main concernée, ainsi
que les titres de fenêtres vus quand une table est introuvable. Une
notification prévient en cas de problème.

Le rapport (`fleur_diagnostic_<date>.zip`, sur le bureau) contient le journal,
ces fichiers, la configuration et la liste des fenêtres ouvertes. Les mains
mal lues qu'il contient incluent les pseudos de la table.

Le dossier d'historiques est détecté automatiquement
(`%APPDATA%\winamax\documents\accounts\<pseudo>\history` pour le client actuel,
`Documents\Winamax Poker\accounts\<pseudo>\history` pour les anciens). Sinon :
`python -m fleur --history "C:\chemin\vers\history"`.

Seules les mains de cash game (tables classiques et ESCAPE) sont importées.
Les mains de tournoi (jetons) sont ignorées sauf si `include_tournaments`
vaut `true` dans la configuration.

### Sur la table

- Un panneau par adversaire, qui suit la fenêtre de la table et se met à jour à chaque main.
- **Glisser** un panneau pour le déplacer : la position est mémorisée pour toutes
  les tables du même format (6-max, 9-max…).
- **Double-clic** : popup avec toutes les stats et les échantillons (ex. `3/12`).
- **Clic droit** : étiquette (fish, reg, nit, LAG, maniaque) ou « Étiquette perso et
  note… » pour choisir un texte, une couleur et écrire une note libre. Le panneau
  affiche une pastille de couleur et ✎ quand une note existe (survol = la note).
  Notes et étiquettes sont stockées en base (table `player_notes`) ; la liste des
  étiquettes se règle dans `player_tags`.
- Le popup liste aussi les dernières mains montrées à l'abattage (`shown_hands_count`, 8 par défaut) :
  cartes, board, ligne d'action résumée et résultat.
- Les couleurs s'activent à partir de 10 mains (`min_hands_for_colors`).

### Analyse après coup

**FleurAnalyse.exe** (`dist\FleurAnalyse\FleurAnalyse.exe`, construit par `build_exe.bat`) :
fenêtre Windows qui regroupe le tableau de bord du héros (toutes les stats, courbes,
fuites, résultats par position, limite et format) et toute l'analyse ci-dessous. Elle
importe les nouvelles mains et se met à jour toute seule ; depuis le HUD, l'entrée
« Analyse et tableau de bord du héros » du menu de l'icône l'ouvre directement.

**Application d'analyse** (menu de l'icône → « Analyse : revue de mains, ranges,
sessions… », ou `python -m fleur analyse`) : un petit serveur local
(`127.0.0.1`, jeton aléatoire par session) ouvre dans le navigateur :

- **Revue de mains** : liste filtrable (position, gagnées/perdues, abattage, taille
  du pot, limite, main de départ, tri par gros pots ou grosses pertes) et rejoueur
  street par street (flèches ← →), export en texte (brut ou anonymisé) et en image.
- **Ranges** : grille 13×13 des mains de départ, colorée selon les BB/100, la
  fréquence jouée ou relancée, par position et par limite.
- **All-in EV** : courbe de gains réels et à la régulière (équité au moment du
  tapis quand toutes les cartes sont montrées avant la river).
- **Sessions** : durée, mains par heure, résultats par table, par heure de la
  journée et par jour.
- **Stats perso** : éditeur de stats par formules sur les compteurs
  (`+ - * /`, parenthèses), testables sur ses propres mains, enregistrées dans
  `custom_stats` et utilisables dans `hud_lines` et `popup_stats`.
- **Équité** : calculateur pour réviser des mains, **refusé tant qu'une table
  Winamax est ouverte**.
- **Outils** : sauvegarde de la base dans `Documents\Fleur\sauvegardes` (aussi
  dans le menu de l'icône et avec `python -m fleur sauvegarde`).

Le popup du HUD montre aussi les stats par street (mise, fold et relance face à une
mise au flop, turn et river), le fold selon la taille de mise et la part d'overbets.

- `python -m fleur dashboard` (ou menu de l'icône → « Tableau de bord du héros ») :
  page HTML locale avec la courbe de gains en € et en big blinds (avec et sans
  abattage), BB/100 par position, par limite et par format, résultats par session
  et liste des fuites possibles.
- `python -m fleur fuites` : la même liste de fuites dans la console, comparée à des
  fourchettes indicatives de cash game 6-max et triée par importance.
- `python -m fleur stats <pseudo> --seats 6 --bb 0.02` : stats filtrées.

Dans le HUD : badge de profil automatique (fish, nit, TAG, LAG, maniaque) à partir
de 50 mains (`profile_min_hands`), RFI / 3-bet / fold face au vol par position dans
le popup, et filtre des stats par format de table et par limite (menu de l'icône
→ « Filtre des stats », ou `stats_filter` dans la config).

Fleur n'analyse que les historiques déjà écrits : aucun conseil n'est donné pendant
une main.

### Panneau par défaut

```
Pseudo
VPIP / PFR / 3Bet / AF / (mains)
F3B  / ATS / FvS  / CB / FCB
WTSD / W$SD / WWSF / BB/100
```

## Stats disponibles

| Clé | Stat | Clé | Stat |
|---|---|---|---|
| `vpip` | VPIP | `cbet` | C-bet flop |
| `pfr` | PFR | `fcbet` | Fold au c-bet flop |
| `3bet` | 3-bet | `rcbet` | Relance du c-bet flop |
| `f3bet` | Fold au 3-bet | `cbet_t` / `fcbet_t` | C-bet / fold c-bet turn |
| `4bet` | 4-bet | `donk` | Donk bet flop |
| `rfi` | Raise first in | `xr` | Check-raise flop |
| `limp` | Limp | `af` / `afq` | Agression (facteur / fréquence) |
| `cc` | Cold call | `wtsd` | Went to showdown |
| `sqz` | Squeeze | `wsd` | W$SD |
| `steal` | Attempt to steal | `wwsf` | Won when saw flop |
| `fsteal` | Fold vs steal (blindes) | `bb100` | BB/100 |
| `3bsteal` | 3-bet vs steal | `hands` / `net` | Mains / gains |

## Configuration

`%APPDATA%\Fleur\config.json` (créé au premier lancement) :

- `hud_lines` : les stats de chaque ligne du panneau ;
- `popup_stats` : les stats du popup ;
- `colors` : seuils de couleur par stat ;
- `show_hero` : afficher son propre panneau ;
- `hero_at_bottom` : le héros est en bas de la table (réglage par défaut de Winamax) ;
- `font_size`, `opacity`, `min_hands_for_colors`, `history_dirs`.

Les positions des panneaux sont dans `%APPDATA%\Fleur\layouts.json`.

## Exécutable

```bat
pip install -r requirements-dev.txt
build_exe.bat
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Règlement Winamax

Un HUD alimenté par ses propres historiques est en principe autorisé chez Winamax,
contrairement aux outils d'aide à la décision en temps réel (solveurs, conseils).
Vérifie les conditions générales en vigueur avant de jouer en argent réel.
