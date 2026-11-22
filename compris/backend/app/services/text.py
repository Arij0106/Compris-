"""Utilitaires texte (nettoyage, phrases, mots vides FR/EN)."""
import re
import unicodedata


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_RAW_STOPWORDS = """
au aux avec ce ces cet cette dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me meme mes moi mon
ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous c d j l a m n s t y
ete etre est sont sera serait suis es sommes etes avoir ai as avons avez ont avait fait faire peut peuvent doit dont ou si ni car
sans sous chez vers ainsi donc alors aussi plus moins comme entre tout tous toute toutes tres bien cela ceci celui celle ca
the of and to in is are be as on at by for with from that this it or an was were been has have had not but if then than so such
which who whom what when where how can could should would will may might do does did their there these those
universite faculte institut departement ecole academie ministere annee universitaire semestre session examen cours module
enseignant professeur docteur etudiant devoir exercice exercices td tp page pages premier premiere deuxieme troisieme quatrieme
partie chapitre titre date courriel email bibliographie sommaire table matieres remerciements licence master doctorat version
copyright auteur droits reserves introduction conclusion resume
في من على الى إلى عن مع هذا هذه ذلك التي الذي ان أن كان
"""
STOPWORDS = {strip_accents(w) for w in _RAW_STOPWORDS.split()}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_SENT_RE = re.compile(r"(?<=[\.\!\?؟])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(clean(text)) if s.strip()]
